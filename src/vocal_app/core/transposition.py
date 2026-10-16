"""Score-dependent transposition within the detector's supported pitch range."""
import math

from .notes import hz_to_midi, midi_to_note, note_to_midi
from .tracking import DEFAULT_CONFIG

MIN_TRAINING_MIDI = max(0, math.ceil(hz_to_midi(DEFAULT_CONFIG.min_hz)))
MAX_TRAINING_MIDI = min(127, math.floor(hz_to_midi(DEFAULT_CONFIG.max_hz)))
TRAINING_RANGE_LABEL = f"{midi_to_note(MIN_TRAINING_MIDI)}–{midi_to_note(MAX_TRAINING_MIDI)}"


def transpose_limits(exercise) -> tuple[int, int]:
    if exercise.mode == "breathing":
        return 0, 0
    pitches = [note_to_midi(note) for note in (*exercise.vocal_notes, *exercise.guide_notes) if note]
    lower = MIN_TRAINING_MIDI - min(pitches)
    upper = MAX_TRAINING_MIDI - max(pitches)
    if lower > upper:
        raise ValueError(f"A distância entre a nota mais grave e a mais aguda excede a faixa {TRAINING_RANGE_LABEL}. "
                         "Reduza a extensão do exercício; transpor todas as notas não resolve essa diferença.")
    return lower, upper


def clamp_transpose(exercise, transpose: int) -> int:
    lower, upper = transpose_limits(exercise)
    return max(lower, min(upper, int(transpose)))
