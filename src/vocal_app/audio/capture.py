"""PortAudio capture: callback only copies PCM; pitch runs on a worker thread."""
from __future__ import annotations

from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import perf_counter
from typing import Any

import numpy as np


@dataclass(frozen=True)
class AudioChunk:
    start_sample: int
    sample_rate: int
    pcm: np.ndarray
    status: str = ""


@dataclass(frozen=True)
class AudioSegment:
    """Original mono samples, without filtering, normalization or resampling."""
    pcm: np.ndarray
    sample_rate: int
    start_ms: float
    end_ms: float
    label: str | None = None
    device: str | int | None = None
    dropped_analysis_blocks: int = 0


@dataclass(frozen=True)
class AnalysisEvent:
    t: float
    frame: Any | None
    rms: float


class CaptureEngine:
    def __init__(self, detector=None, sample_rate=48000, device=None,
                 window_size=4096, hop_ms=20, queue_blocks=256):
        self.sample_rate = int(sample_rate)
        self.device = device
        self.window_size = int(window_size)
        self.hop_size = max(1, round(sample_rate * hop_ms / 1000))
        if detector is None:
            from .pitch import PitchDetector
            detector = PitchDetector(sample_rate=self.sample_rate)
        self.detector = detector
        self._queue: Queue = Queue(maxsize=queue_blocks)
        self._events: Queue = Queue()
        self._halt = Event()
        self._thread = None
        self._stream = None
        self.chunks: list[AudioChunk] = []
        self.started_at = 0.0
        self._sample_count = 0
        self.dropped_analysis_blocks = 0
        self.last_error = ""
        self.running = False

    @property
    def elapsed_ms(self):
        return max(0.0, (perf_counter() - self.started_at) * 1000) if self.started_at else 0.0

    @staticmethod
    def devices():
        import sounddevice as sd
        return [dict(index=i, **dict(device)) for i, device in enumerate(sd.query_devices())]

    def diagnostics(self):
        try:
            devices = self.devices()
            return {"devices": devices, "input_devices": [d for d in devices if d["max_input_channels"] > 0],
                    "error": self.last_error, "dropped_analysis_blocks": self.dropped_analysis_blocks,
                    "capture_status": sorted({c.status for c in self.chunks if c.status})}
        except Exception as exc:
            return {"devices": [], "input_devices": [], "error": str(exc)}

    def start(self):
        import sounddevice as sd
        if self.running:
            return self
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("A captura anterior ainda está finalizando.")
        self.chunks.clear()
        self._sample_count = 0
        self.dropped_analysis_blocks = 0
        self.last_error = ""
        self._queue = Queue(maxsize=self._queue.maxsize)
        self._events = Queue()
        self._halt.clear()
        try:
            sd.check_input_settings(device=self.device, channels=1, dtype="float32", samplerate=self.sample_rate)
            self._stream = sd.InputStream(device=self.device, samplerate=self.sample_rate,
                                          channels=1, dtype="float32", blocksize=self.hop_size,
                                          callback=self._callback)
            self.started_at = perf_counter()
            self.running = True
            self._thread = Thread(target=self._process, name="vocal-pitch", daemon=True)
            self._thread.start()
            self._stream.start()
        except Exception as exc:
            self.last_error = f"Não foi possível abrir o microfone: {exc}"
            self.stop()
            raise RuntimeError(self.last_error) from exc
        return self

    def _callback(self, indata, frames, time_info, status):
        # Store every block before enqueueing analysis; backlog cannot erase PCM.
        pcm = np.array(indata[:, 0], dtype=np.float32, copy=True)
        pcm.flags.writeable = False
        chunk = AudioChunk(self._sample_count, self.sample_rate, pcm, str(status) if status else "")
        self._sample_count += len(pcm)
        self.chunks.append(chunk)
        try:
            self._queue.put_nowait(chunk)
        except Full:
            self.dropped_analysis_blocks += 1

    def _process(self):
        buffer = np.empty(0, dtype=np.float32)
        expected_sample = 0
        next_end = self.window_size
        while not self._halt.is_set() or not self._queue.empty():
            try:
                chunk = self._queue.get(timeout=0.05)
            except Empty:
                continue
            if chunk.start_sample != expected_sample:
                buffer = np.empty(0, dtype=np.float32)
                next_end = chunk.start_sample + self.window_size
                self._events.put(AnalysisEvent(chunk.start_sample * 1000 / self.sample_rate, None, 0.0))
            expected_sample = chunk.start_sample + len(chunk.pcm)
            buffer = np.concatenate((buffer, chunk.pcm))
            buffer_start = expected_sample - len(buffer)
            while next_end <= expected_sample:
                offset = next_end - buffer_start
                window = buffer[offset - self.window_size:offset]
                t = next_end * 1000 / self.sample_rate
                rms = float(np.sqrt(np.mean(np.square(window, dtype=np.float64))))
                try:
                    frame = self.detector.detect(window, t=t)
                except Exception as exc:
                    self.last_error = f"Falha no detector: {exc}"
                    frame = None
                self._events.put(AnalysisEvent(t, frame, rms))
                next_end += self.hop_size
            # Keep enough for the next overlapping window.
            buffer = buffer[-self.window_size:]

    def drain_frames(self) -> list[AnalysisEvent]:
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except Empty:
                return events

    def stop(self):
        self.running = False
        if self._stream is not None:
            try:
                self._stream.stop()
            except Exception as exc:
                self.last_error = f"Falha ao interromper captura: {exc}"
            finally:
                try:
                    self._stream.close()
                except Exception as exc:
                    self.last_error = f"Falha ao liberar microfone: {exc}"
                self._stream = None
        self._halt.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            if self._thread.is_alive():
                self.last_error = "O processamento de áudio demorou para finalizar."
            else:
                self._thread = None

    def segment(self, start_ms=0.0, end_ms=None, label=None) -> AudioSegment:
        # Snapshot the immutable blocks; no file or personal recording is saved.
        chunks = tuple(self.chunks)
        total = sum(len(c.pcm) for c in chunks)
        start = max(0, min(total, round(start_ms * self.sample_rate / 1000)))
        end = total if end_ms is None else max(start, min(total, round(end_ms * self.sample_rate / 1000)))
        pieces = [c.pcm[max(0, start - c.start_sample):min(len(c.pcm), end - c.start_sample)]
                  for c in chunks if c.start_sample < end and c.start_sample + len(c.pcm) > start]
        pcm = np.concatenate(pieces) if pieces else np.empty(0, dtype=np.float32)
        pcm.flags.writeable = False
        return AudioSegment(pcm, self.sample_rate, start * 1000 / self.sample_rate,
                            end * 1000 / self.sample_rate, label, self.device, self.dropped_analysis_blocks)
