"""Equal-tempered note conversions used by the original Vocal Trainer."""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from collections.abc import Sequence

SHARP_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


@dataclass(frozen=True, slots=True)
class ExpectedNote:
    index: int
    label: str
    midi: int


@dataclass(frozen=True, slots=True)
class NearestNote:
    midi: int
    name: str
    cents: float


def normalize_note(token: str) -> str:
    return token.strip().replace("♯", "#").replace("♭", "b")


def note_to_midi(note: str) -> int:
    match = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d+)", normalize_note(note))
    if not match:
        raise ValueError(f'Nota inválida: "{note}"')
    letter, accidental, octave = match.groups()
    # Arithmetic also preserves octave crossings: B#3=C4, Cb4=B3.
    return 12 * (int(octave) + 1) + _NATURAL[letter.upper()] + {"": 0, "#": 1, "b": -1}[accidental]


def midi_to_hz(midi: float) -> float:
    if not math.isfinite(midi):
        raise ValueError("MIDI deve ser finito.")
    return 440.0 * 2 ** ((midi - 69) / 12)


def hz_to_midi(hz: float) -> float:
    if not math.isfinite(hz) or hz <= 0:
        raise ValueError("Frequência deve ser positiva e finita.")
    return 69 + 12 * math.log2(hz / 440)


def nearest_note(midi_float: float) -> NearestNote:
    if not math.isfinite(midi_float):
        raise ValueError("MIDI deve ser finito.")
    midi = math.floor(midi_float + 0.5)  # JavaScript Math.round, not bankers' rounding
    return NearestNote(midi, f"{SHARP_NAMES[midi % 12]}{midi // 12 - 1}", (midi_float - midi) * 100)


def midi_to_note(midi: float) -> str:
    return nearest_note(midi).name


def cents_between_midi(midi: float, reference_midi: float) -> float:
    return (midi - reference_midi) * 100


def cents_between_hz(hz: float, reference_hz: float) -> float:
    return cents_between_midi(hz_to_midi(hz), hz_to_midi(reference_hz))


def transpose_note(note: str, semitones: int) -> str:
    if not isinstance(semitones, int):
        raise ValueError("A transposição deve ser um número inteiro de semitons.")
    return midi_to_note(note_to_midi(note) + semitones)


def parse_exercise(text: str | Sequence[str]) -> list[ExpectedNote]:
    tokens = text.replace(",", " ").split() if isinstance(text, str) else list(text)
    if not tokens:
        raise ValueError("Digite pelo menos uma nota no exercício.")
    return [ExpectedNote(i, normalize_note(token), note_to_midi(token)) for i, token in enumerate(tokens)]


def parse_guide_pattern(notes: Sequence[str | None]) -> list[ExpectedNote | None]:
    return [None if token in (None, "", "—") else ExpectedNote(i, normalize_note(token), note_to_midi(token))
            for i, token in enumerate(notes)]


def parse_score(notes: Sequence[str | None], transpose: int = 0) -> list[ExpectedNote | None]:
    """Preserve rest slots while numbering only the notes that will be evaluated."""
    positions = []
    index = 0
    for token in notes:
        if token is None:
            positions.append(None)
        else:
            label = transpose_note(token, transpose)
            positions.append(ExpectedNote(index, label, note_to_midi(label)))
            index += 1
    return positions


# Explicit musical names make these usable by integrations without JS naming.
note_name_to_midi = note_to_midi
hz_to_midi_float = hz_to_midi
midi_float_to_nearest_note = nearest_note
