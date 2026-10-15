"""Local sampled instruments through FluidSynth; no synthetic instrument fallback."""
from __future__ import annotations

import ctypes as ct
from ctypes.util import find_library
from concurrent.futures import Future
import os
from pathlib import Path
from queue import Empty, Queue
from threading import Thread
from time import perf_counter

import numpy as np

INSTRUMENTS = {"acoustic_guitar_nylon": 24, "acoustic_guitar_steel": 25, "acoustic_grand_piano": 0}
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class AudioUnavailable(RuntimeError):
    pass


def default_soundfont():
    configured = os.environ.get("VOCAL_SOUNDFONT")
    return Path(configured).expanduser() if configured else PROJECT_ROOT / "soundfonts" / "GeneralUser-GS.sf2"


class _FluidSynth:
    """Small ctypes binding; every synth call stays on the playback worker."""
    def __init__(self, soundfont, sample_rate=48000, library_path=None):
        soundfont = Path(soundfont).expanduser().resolve()
        if not soundfont.is_file():
            raise AudioUnavailable(f"SoundFont ausente: {soundfont}. Escolha um arquivo .sf2 nas configurações. Os MP3 continuam disponíveis.")
        local = list((PROJECT_ROOT / "runtime" / "fluidsynth").rglob("libfluidsynth*.dll"))
        library = library_path or os.environ.get("VOCAL_FLUIDSYNTH") or (str(local[0]) if local else find_library("fluidsynth"))
        if not library:
            raise AudioUnavailable("FluidSynth nativo não encontrado. Consulte docs/audio.md ou configure VOCAL_FLUIDSYNTH.")
        self._dll_dir = None
        self.settings = self.synth = None
        try:
            if os.name == "nt" and Path(library).is_file():
                self._dll_dir = os.add_dll_directory(str(Path(library).resolve().parent))
            self.lib = ct.CDLL(str(library))
        except OSError as exc:
            if self._dll_dir:
                self._dll_dir.close()
            raise AudioUnavailable(f"Falha ao carregar FluidSynth ({library}): {exc}") from exc
        signatures = {
            "new_fluid_settings": (ct.c_void_p, []),
            "fluid_settings_setnum": (ct.c_int, [ct.c_void_p, ct.c_char_p, ct.c_double]),
            "new_fluid_synth": (ct.c_void_p, [ct.c_void_p]),
            "fluid_synth_sfload": (ct.c_int, [ct.c_void_p, ct.c_char_p, ct.c_int]),
            "fluid_synth_program_select": (ct.c_int, [ct.c_void_p, ct.c_int, ct.c_int, ct.c_int, ct.c_int]),
            "fluid_synth_noteon": (ct.c_int, [ct.c_void_p, ct.c_int, ct.c_int, ct.c_int]),
            "fluid_synth_noteoff": (ct.c_int, [ct.c_void_p, ct.c_int, ct.c_int]),
            "fluid_synth_all_sounds_off": (ct.c_int, [ct.c_void_p, ct.c_int]),
            "fluid_synth_write_float": (ct.c_int, [ct.c_void_p, ct.c_int, ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p, ct.c_int, ct.c_int]),
            "delete_fluid_synth": (None, [ct.c_void_p]),
            "delete_fluid_settings": (None, [ct.c_void_p]),
        }
        for name, (result, args) in signatures.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, args
        try:
            self.settings = self.lib.new_fluid_settings()
            if not self.settings:
                raise AudioUnavailable("FluidSynth não conseguiu criar configurações.")
            self.lib.fluid_settings_setnum(self.settings, b"synth.sample-rate", float(sample_rate))
            self.lib.fluid_settings_setnum(self.settings, b"synth.gain", 0.6)
            self.synth = self.lib.new_fluid_synth(self.settings)
            if not self.synth:
                raise AudioUnavailable("FluidSynth não conseguiu criar o sintetizador.")
            self.soundfont_id = self.lib.fluid_synth_sfload(self.synth, os.fsencode(soundfont), 1)
            if self.soundfont_id < 0:
                raise AudioUnavailable(f"SoundFont inválido ou incompatível: {soundfont}")
        except Exception:
            self.close()
            raise

    def select(self, instrument):
        if instrument not in INSTRUMENTS:
            raise ValueError(f"Instrumento desconhecido: {instrument}")
        result = self.lib.fluid_synth_program_select(self.synth, 0, self.soundfont_id, 0, INSTRUMENTS[instrument])
        if result < 0:
            raise AudioUnavailable(f"Banco não contém o instrumento GM {INSTRUMENTS[instrument]} ({instrument}).")

    def note_on(self, midi, velocity):
        self.lib.fluid_synth_noteon(self.synth, 0, midi, velocity)

    def note_off(self, midi):
        self.lib.fluid_synth_noteoff(self.synth, 0, midi)

    def stop(self):
        self.lib.fluid_synth_all_sounds_off(self.synth, 0)

    def render(self, count):
        output = np.empty((count, 2), dtype=np.float32)
        pointer = output.ctypes.data_as(ct.c_void_p)
        self.lib.fluid_synth_write_float(self.synth, count, pointer, 0, 2, pointer, 1, 2)
        return output

    def close(self):
        if self.synth:
            self.lib.delete_fluid_synth(self.synth)
            self.synth = None
        if self.settings:
            self.lib.delete_fluid_settings(self.settings)
            self.settings = None
        if self._dll_dir:
            self._dll_dir.close()
            self._dll_dir = None


def metronome_pcm(accent=False, sample_rate=48000):
    """65ms square click with the original attack/release; only metronome is synthesized."""
    t = np.arange(round(sample_rate * .065)) / sample_rate
    peak = .16 if accent else .09
    envelope = np.where(t < .005, .0001 * (peak / .0001) ** (t / .005),
                        peak * (.0001 / peak) ** ((t - .005) / .05))
    return (np.sign(np.sin(2 * np.pi * (1320 if accent else 880) * t)) * envelope).astype(np.float32)


class GuidePlayer:
    def __init__(self, sample_rate=48000, device=None, block_size=512):
        self.sample_rate, self.device, self.block_size = sample_rate, device, block_size
        self.last_error = ""
        self.ready = False
        self._commands = Queue()
        self._generation = 0
        self._closed = False
        self._thread = Thread(target=self._run, name="vocal-guide", daemon=True)
        self._thread.start()

    def prepare(self, soundfont_path=None, instrument="acoustic_guitar_nylon", library_path=None) -> Future:
        future = Future()
        if self._closed or not self._thread.is_alive():
            future.set_exception(AudioUnavailable(self.last_error or "Reprodutor encerrado."))
        else:
            self._commands.put(("prepare", (soundfont_path or default_soundfont(), instrument, library_path, future), self._generation))
        return future

    def note_on(self, midi, velocity=100, duration=None):
        if not 0 <= int(midi) <= 127:
            raise ValueError("Nota MIDI deve estar entre 0 e 127.")
        self._commands.put(("on", (int(midi), max(0, min(127, int(velocity))), duration), self._generation))

    def note_off(self, midi):
        self._commands.put(("off", (int(midi),), self._generation))

    def click(self, accent=False):
        self._commands.put(("click", (accent,), self._generation))

    def stop(self):
        self._generation += 1
        self._commands.put(("stop", (), self._generation))

    def close(self):
        if not self._closed:
            self._closed = True
            self.stop()
            self._commands.put(("close", (), self._generation))
            self._thread.join(timeout=2)

    def _run(self):
        synth = stream = None
        loaded_path = None
        deadlines = {}
        clicks = []

        def ensure_stream():
            nonlocal stream
            if stream is None:
                import sounddevice as sd
                stream = sd.OutputStream(samplerate=self.sample_rate, channels=2, dtype="float32",
                                         blocksize=self.block_size, device=self.device, latency="low")
                stream.start()

        try:
            while True:
                commands = []
                try:
                    commands.append(self._commands.get(timeout=.02 if stream is None else 0))
                except Empty:
                    pass
                while not self._commands.empty():
                    commands.append(self._commands.get_nowait())
                for command, args, generation in commands:
                    if generation != self._generation and command not in ("prepare", "close"):
                        continue
                    if command == "close":
                        return
                    try:
                        if command == "prepare":
                            path, instrument, library, future = args
                            if synth:
                                synth.stop()
                            deadlines.clear()
                            clicks.clear()
                            if synth is None or str(path) != loaded_path:
                                replacement = _FluidSynth(path, self.sample_rate, library)
                                if synth:
                                    synth.close()
                                synth = replacement
                                loaded_path = str(path)
                            synth.select(instrument)
                            ensure_stream()
                            self.ready = True
                            self.last_error = ""
                            future.set_result(True)
                        elif command == "on":
                            if synth is None or not self.ready:
                                raise AudioUnavailable("Prepare um SoundFont local antes de tocar o guia.")
                            midi, velocity, duration = args
                            synth.note_on(midi, velocity)
                            deadlines[midi] = perf_counter() + duration if duration is not None else float("inf")
                        elif command == "off":
                            if synth:
                                synth.note_off(args[0])
                            deadlines.pop(args[0], None)
                        elif command == "click":
                            ensure_stream()
                            clicks.append(metronome_pcm(args[0], self.sample_rate))
                        elif command == "stop":
                            if synth:
                                synth.stop()
                            deadlines.clear()
                            clicks.clear()
                    except Exception as exc:
                        self.last_error = str(exc)
                        if command == "prepare":
                            self.ready = False
                            if not args[-1].done():
                                args[-1].set_exception(exc)
                if stream is not None:
                    now = perf_counter()
                    for midi, deadline in tuple(deadlines.items()):
                        if deadline <= now:
                            synth.note_off(midi)
                            deadlines.pop(midi)
                    output = synth.render(self.block_size) if synth else np.zeros((self.block_size, 2), dtype=np.float32)
                    remaining_clicks = []
                    for click in clicks:
                        count = min(len(click), self.block_size)
                        output[:count] += click[:count, None]
                        if len(click) > count:
                            remaining_clicks.append(click[count:])
                    clicks = remaining_clicks
                    np.clip(output, -1.0, 1.0, out=output)
                    stream.write(output)
        except Exception as exc:
            self.last_error = f"Falha na saída de áudio: {exc}"
        finally:
            self.ready = False
            if stream:
                stream.abort()
                stream.close()
            if synth:
                synth.close()
            while not self._commands.empty():
                command, args, _ = self._commands.get_nowait()
                if command == "prepare" and not args[-1].done():
                    args[-1].set_exception(AudioUnavailable(self.last_error or "Reprodutor encerrado."))
