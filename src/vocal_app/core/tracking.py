"""Port of trainer/app.js SegmentTracker (source revision 41a5ec8).

Time is always milliseconds relative to capture start. PCM is owned by the
acquisition layer; segment start/end timestamps locate the corresponding audio.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
import math
from statistics import median

from .notes import ExpectedNote, NearestNote, nearest_note


@dataclass(frozen=True, slots=True)
class TrackerConfig:
    analysis_every_ms: float = 20
    min_clarity: float = 0.86
    min_rms: float = 0.008
    min_hz: float = 65
    max_hz: float = 1200
    leave_tolerance_cents: float = 75
    candidate_frames: int = 3
    candidate_spread_cents: float = 38
    min_new_region_distance_cents: float = 80
    new_region_membership_cents: float = 55
    max_unvoiced_gap_ms: float = 180
    min_segment_ms: float = 75
    initial_acquire_frames: int = 3
    initial_acquire_spread_cents: float = 30
    initial_acquire_max_deviation_cents: float = 45
    initial_acquire_membership_cents: float = 52
    initial_acquire_max_buffer_frames: int = 20
    initial_acquire_reset_gap_ms: float = 240
    repeated_same_note_gap_ms: float = 50
    repeated_same_note_timing_tolerance_ms: float = 35
    evaluation_edge_trim_ms: float = 38
    min_core_samples: int = 3
    low_confidence_ms: float = 180
    high_confidence_ms: float = 320


DEFAULT_CONFIG = TrackerConfig()


@dataclass(frozen=True, slots=True)
class PitchFrame:
    t: float
    hz: float
    midi: float
    clarity: float
    rms: float
    hidden_during_live: bool = False


@dataclass(frozen=True, slots=True)
class Transition:
    start_t: float
    end_t: float
    duration_ms: float
    kind: str = "pitch"


@dataclass(slots=True)
class Segment:
    start_t: float
    nominal_start_t: float
    last_t: float
    samples: list[PitchFrame]
    transition_from_previous: Transition | None = None
    detected_index: int = -1
    end_t: float = 0
    duration_ms: float = 0
    center_midi: float = math.nan
    nearest: NearestNote | None = None


@dataclass(slots=True)
class _Pending:
    start_t: float
    frames: list[PitchFrame] = field(default_factory=list)


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        return math.nan
    ordered = sorted(values)
    index = (len(ordered) - 1) * p
    lo, hi = math.floor(index), math.ceil(index)
    if lo == hi:
        return ordered[lo]
    weight = index - lo
    return ordered[lo] * (1 - weight) + ordered[hi] * weight


def robust_center_midi(samples: Sequence[PitchFrame]) -> float:
    return median(s.midi for s in samples) if samples else math.nan


def robust_spread_cents(samples: Sequence[PitchFrame]) -> float:
    values = [s.midi * 100 for s in samples]
    return percentile(values, .75) - percentile(values, .25) if samples else math.inf


class SegmentTracker:
    def __init__(self, expected: Sequence[ExpectedNote] = (), note_duration_ms: float = 1000,
                 config: TrackerConfig = DEFAULT_CONFIG, *, durations_ms: Sequence[float] = ()):
        self.expected = list(expected)
        self.note_duration_ms = note_duration_ms
        self.durations_ms = tuple(durations_ms)
        self.config = config
        self.reset()

    def reset(self) -> None:
        self.current: Segment | None = None
        self.pending_transition: _Pending | None = None
        self.segments: list[Segment] = []
        self.outlier_count = 0
        self.last_valid_t: float | None = None
        self.initial_frames: list[PitchFrame] = []
        self.initial_raw_start_t: float | None = None
        self.last_initial_t: float | None = None
        self.unvoiced_start_t: float | None = None
        self.state = "SILÊNCIO"

    def feed(self, frame: PitchFrame | None, t: float | None = None) -> None:
        """Gate detector output; absent/rejected frames must include a timestamp."""
        if frame is not None:
            t = frame.t
            c = self.config
            if (all(math.isfinite(v) for v in (frame.t, frame.hz, frame.midi, frame.clarity, frame.rms))
                    and c.min_hz <= frame.hz <= c.max_hz
                    and frame.clarity >= c.min_clarity and frame.rms >= c.min_rms):
                self.ingest(frame)
                return
        if t is None or not math.isfinite(t):
            raise ValueError("Um frame sem pitch requer um timestamp finito em ms.")
        self.no_pitch(t)

    process = feed

    def ingest(self, frame: PitchFrame) -> None:
        """Ingest an already validated pitch, matching the original JS contract."""
        self.last_valid_t = frame.t
        c = self.config
        if self.current is None:
            self._ingest_initial(frame)
            return
        if self.unvoiced_start_t is not None:
            gap = frame.t - self.unvoiced_start_t
            if self._next_expected_is_same_pitch() and gap >= c.repeated_same_note_gap_ms:
                split = self.unvoiced_start_t
                self._finalize_current(split)
                self._start_segment([frame], Transition(split, frame.t, max(0, gap), "rearticulation"), split)
                self.unvoiced_start_t = None
                self.pending_transition = None
                self.state = "NOVA ARTICULAÇÃO"
                return
            self.unvoiced_start_t = None
        center = robust_center_midi(self.current.samples)
        distance = abs((frame.midi - center) * 100)
        if (self.pending_transition is None and distance <= c.leave_tolerance_cents
                and self._next_expected_is_same_pitch() and self._same_pitch_boundary_reached(frame.t)):
            boundary = self.current.nominal_start_t + self._current_duration_ms()
            self._finalize_current(boundary)
            self._start_segment([frame], Transition(boundary, frame.t, max(0, frame.t - boundary), "same-note-timing"), boundary)
            self.state = "NOTA REPETIDA"
            return
        if self.pending_transition is None:
            if distance <= c.leave_tolerance_cents:
                self.current.samples.append(frame)
                self.current.last_t = frame.t
                self.state = "NOTA"
            else:
                self.pending_transition = _Pending(frame.t, [frame])
                self.state = "TRANSIÇÃO?"
            return
        self.pending_transition.frames.append(frame)
        center = robust_center_midi(self.current.samples)
        if abs((frame.midi - center) * 100) <= c.leave_tolerance_cents:
            self.outlier_count += len(self.pending_transition.frames) - 1
            self.pending_transition = None
            self.current.samples.append(frame)
            self.current.last_t = frame.t
            self.state = "NOTA"
            return
        if len(self.pending_transition.frames) < c.candidate_frames:
            self.state = "TRANSIÇÃO?"
            return
        if not self._confirm_transition():
            self.state = "TRANSIÇÃO"

    def _confirm_transition(self) -> bool:
        assert self.pending_transition is not None and self.current is not None
        c = self.config
        candidate = self.pending_transition.frames[-c.candidate_frames:]
        candidate_center = robust_center_midi(candidate)
        if (robust_spread_cents(candidate) > c.candidate_spread_cents
                or abs((candidate_center - robust_center_midi(self.current.samples)) * 100) < c.min_new_region_distance_cents):
            return False
        frames = self.pending_transition.frames
        start_index = len(frames) - 1
        for i in range(len(frames) - 1, -1, -1):
            if abs((frames[i].midi - candidate_center) * 100) <= c.new_region_membership_cents:
                start_index = i
            else:
                break
        stable = frames[start_index:]
        transition_start = self.pending_transition.start_t
        self._finalize_current(transition_start)
        self._start_segment(stable, Transition(transition_start, stable[0].t, max(0, stable[0].t - transition_start)))
        self.pending_transition = None
        self.state = "NOTA"
        return True

    def no_pitch(self, t: float) -> None:
        c = self.config
        if self.current is None or self.last_valid_t is None:
            if (self.initial_frames and self.last_initial_t is not None
                    and t - self.last_initial_t >= c.initial_acquire_reset_gap_ms):
                self._clear_initial()
            self.state = "ADQUIRINDO" if self.initial_frames else "SILÊNCIO"
            return
        if self.unvoiced_start_t is None:
            self.unvoiced_start_t = t
        if t - self.last_valid_t >= c.max_unvoiced_gap_ms:
            self._finalize_current(self.last_valid_t)
            self.current = None
            self.pending_transition = None
            self.unvoiced_start_t = None
            self._clear_initial()
            self.state = "SILÊNCIO"
        else:
            self.state = "SEM PITCH"

    def _clear_initial(self) -> None:
        self.initial_frames = []
        self.initial_raw_start_t = None
        self.last_initial_t = None

    def deliberate_rest(self, t: float) -> None:
        """Close a phrase at a written rest, even when shorter than the silence gate."""
        self._finalize_current(t)
        self.current = None
        self.pending_transition = None
        self.unvoiced_start_t = None
        self._clear_initial()
        self.state = "PAUSA"

    def _ingest_initial(self, frame: PitchFrame) -> None:
        c = self.config
        if not self.initial_frames:
            self.initial_raw_start_t = frame.t
        self.initial_frames.append(frame)
        self.last_initial_t = frame.t
        if len(self.initial_frames) > c.initial_acquire_max_buffer_frames:
            self.initial_frames.pop(0)
        if len(self.initial_frames) < c.initial_acquire_frames:
            self.state = "ADQUIRINDO"
            return
        candidate = self.initial_frames[-c.initial_acquire_frames:]
        center = robust_center_midi(candidate)
        if (robust_spread_cents(candidate) > c.initial_acquire_spread_cents
                or max(abs((s.midi - center) * 100) for s in candidate) > c.initial_acquire_max_deviation_cents):
            self.state = "ADQUIRINDO"
            return
        start = len(self.initial_frames) - c.initial_acquire_frames
        for i in range(start - 1, -1, -1):
            if abs((self.initial_frames[i].midi - center) * 100) <= c.initial_acquire_membership_cents:
                start = i
            else:
                break
        stable = self.initial_frames[start:]
        self.outlier_count += max(0, start)
        self._start_segment(stable, None, self.initial_raw_start_t if self.initial_raw_start_t is not None else stable[0].t)
        self._clear_initial()
        self.state = "NOTA"

    def _next_expected_is_same_pitch(self) -> bool:
        i = len(self.segments)
        return i + 1 < len(self.expected) and self.expected[i].midi == self.expected[i + 1].midi

    def _same_pitch_boundary_reached(self, t: float) -> bool:
        duration = self._current_duration_ms()
        return (self.current is not None and math.isfinite(duration)
                and t >= self.current.nominal_start_t + duration - self.config.repeated_same_note_timing_tolerance_ms)

    def _current_duration_ms(self) -> float:
        index = len(self.segments)
        return self.durations_ms[index] if index < len(self.durations_ms) else self.note_duration_ms

    def _start_segment(self, frames: Sequence[PitchFrame], transition: Transition | None,
                       nominal_start_t: float | None = None) -> None:
        self.current = Segment(frames[0].t, frames[0].t if nominal_start_t is None else nominal_start_t,
                               frames[-1].t, list(frames), transition)

    def _finalize_current(self, end_t: float) -> None:
        if self.current is None or not self.current.samples:
            return
        current = self.current
        current.detected_index = len(self.segments)
        current.end_t = max(end_t, current.start_t)
        current.duration_ms = current.end_t - current.start_t
        current.center_midi = robust_center_midi(current.samples)
        current.nearest = nearest_note(current.center_midi)
        self.segments.append(current)

    def finish(self) -> list[Segment]:
        if self.pending_transition and len(self.pending_transition.frames) >= self.config.candidate_frames:
            if not self._confirm_transition():
                self.outlier_count += len(self.pending_transition.frames)
        self.pending_transition = None
        if self.current is not None:
            self._finalize_current(self.last_valid_t if self.last_valid_t is not None else self.current.last_t)
            self.current = None
        return [s for s in self.segments if s.duration_ms >= self.config.min_segment_ms]

    flush = finish
