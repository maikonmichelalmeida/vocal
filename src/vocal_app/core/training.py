"""Fixed musical clock from the audited web revision, independent of Qt/audio.

The web trainer advances on time, not on pitch success. The instrument precedes
the written target by 20% of a note. Silent guide positions retain their written
targets and hide live corrective traces until review.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math
from bisect import bisect_right
from itertools import accumulate

from .notes import ExpectedNote

GUIDE_LEAD_RATIO = .20
PRE_SING_GUIDE_DURATION_MS = 420
QUICK_COUNT_IN_MS = 300


def note_duration_ms(bpm: float, subdivision: int) -> int:
    if not math.isfinite(bpm) or not 40 <= bpm <= 180 or subdivision not in (1, 2, 3, 4):
        raise ValueError("Andamento deve estar entre 40 e 180; subdivisão entre 1 e 4.")
    return max(80, min(4000, math.floor(60000 / (bpm * subdivision) + .5)))


@dataclass(frozen=True, slots=True)
class TargetWindow:
    index: int
    start_t: float
    end_t: float
    midi: int
    label: str
    ghost: bool


class FixedTimeline:
    def __init__(self, expected: Sequence[ExpectedNote | None], note_ms: float,
                 guide_pattern: Sequence[ExpectedNote | None] | None = None,
                 guided: bool = True, durations_ms: Sequence[float] | None = None):
        if not math.isfinite(note_ms) or note_ms <= 0:
            raise ValueError("Duração da nota deve ser positiva e finita.")
        self.positions = list(expected)
        self.expected = [note for note in expected if note is not None]
        self.note_positions = [i for i, note in enumerate(expected) if note is not None]
        self.position_indices = {position: index for index, position in enumerate(self.note_positions)}
        self.guide_pattern = list(expected) if guide_pattern is None else list(guide_pattern)
        if len(self.guide_pattern) != len(self.positions):
            raise ValueError("Guia e sequência vocal devem ter o mesmo número de posições.")
        self.guided = guided
        self.note_ms = note_ms
        self.durations_ms = tuple(durations_ms) if durations_ms else (note_ms,) * len(self.positions)
        if len(self.durations_ms) != len(self.positions) or any(not math.isfinite(d) or d <= 0 for d in self.durations_ms):
            raise ValueError("Informe uma duração positiva e finita por nota.")
        self.boundaries = tuple(accumulate(self.durations_ms, initial=0))
        self.lead_ms = (self.durations_ms[0] if self.durations_ms else note_ms) * GUIDE_LEAD_RATIO
        self.end_t = self.lead_ms + self.boundaries[-1]
        self.rest_starts = tuple(self.lead_ms + self.boundaries[i] for i, note in enumerate(self.positions) if note is None)

    def rests_between(self, start: float, end: float):
        return self.rest_starts[bisect_right(self.rest_starts, start):bisect_right(self.rest_starts, end)]

    def target_index_at(self, t: float) -> int:
        return self.position_indices.get(self.position_index_at(t), -1)

    def position_index_at(self, t: float) -> int:
        if t < self.lead_ms or t >= self.end_t or not self.expected:
            return -1
        return min(len(self.positions) - 1, bisect_right(self.boundaries, t - self.lead_ms) - 1)

    def target_start_t(self, index: int) -> float:
        position = self.note_positions[index] if index < len(self.expected) else len(self.positions)
        return self.lead_ms + self.boundaries[position]

    def guide_start_t(self, index: int) -> float:
        return self.boundaries[index]

    def guide_index_at(self, t: float) -> int:
        if t < 0 or t >= self.end_t or not self.expected:
            return -1
        return min(len(self.positions) - 1, bisect_right(self.boundaries, t) - 1)

    def hidden_during_live(self, t: float) -> bool:
        index = self.position_index_at(t)
        return index >= 0 and self.positions[index] is not None and self.guide_pattern[index] is None

    def is_rest(self, t: float) -> bool:
        index = self.position_index_at(t)
        return index >= 0 and self.positions[index] is None

    @property
    def note_durations_ms(self):
        return tuple(self.durations_ms[i] for i in self.note_positions)

    def windows(self) -> list[TargetWindow]:
        return [TargetWindow(i, self.lead_ms + self.boundaries[pos], self.lead_ms + self.boundaries[pos + 1], note.midi,
                             note.label, self.guide_pattern[pos] is None) for i, (pos, note) in enumerate(zip(self.note_positions, self.expected))]


def progressed_transpose(transpose: int, direction: str, action: str, finished: bool, exercise=None, *, score: float = 0) -> int:
    """Advance a completed attempt only at 75/100 or better, within score bounds."""
    from .transposition import clamp_transpose
    if exercise is not None:
        transpose = clamp_transpose(exercise, transpose)
    if action != "complete" or not finished or not 75 <= score <= 100:
        return transpose
    if direction not in ("ascending", "descending", "asc", "desc", "up", "down"):
        raise ValueError("Direção de progressão inválida.")
    delta = 1 if direction in ("ascending", "asc", "up") else -1
    return clamp_transpose(exercise, transpose + delta) if exercise is not None else transpose + delta
