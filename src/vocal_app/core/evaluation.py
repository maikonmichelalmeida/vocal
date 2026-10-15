"""Sequence alignment and pedagogical metrics faithfully ported from app.js.

Bias determines tuning; standard deviation independently measures instability.
Missing and low-confidence positions contribute zero to the global score.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math
from statistics import median

from .notes import ExpectedNote, cents_between_midi
from .tracking import DEFAULT_CONFIG, PitchFrame, Segment, TrackerConfig, percentile


@dataclass(frozen=True, slots=True)
class Grade:
    label: str
    class_name: str
    rank: int = 0


@dataclass(frozen=True, slots=True)
class Alignment:
    assignments: list[int | None]
    extras: list[int]
    cost: float


@dataclass(frozen=True, slots=True)
class NoteEvaluation:
    expected: ExpectedNote
    segment: Segment
    core_samples: list[PitchFrame]
    sample_count: int
    analyzed_duration_ms: float
    bias: float
    mae: float
    p90: float
    sigma: float
    rmse: float
    confidence: Grade

    @property
    def tuning(self) -> Grade:
        return grade_tuning(self)

    @property
    def stability(self) -> Grade:
        return grade_stability(self)


@dataclass(frozen=True, slots=True)
class GlobalScore:
    score: int
    label: str
    coverage: float
    mean_bias: float
    mean_stability: float
    reliable_count: int
    total_count: int


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    rows: list[NoteEvaluation | None]
    alignment: Alignment
    global_score: GlobalScore
    worst_index: int


def align_segments(expected: Sequence[ExpectedNote], detected: Sequence[Segment]) -> Alignment:
    n, m = len(expected), len(detected)
    dp = [[math.inf] * (m + 1) for _ in range(n + 1)]
    prev: list[list[tuple[str, int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0

    def relax(ni: int, nj: int, cost: float, step: tuple[str, int, int]) -> None:
        if cost < dp[ni][nj]:
            dp[ni][nj], prev[ni][nj] = cost, step

    # Loop and relaxation order intentionally match JS, including tie breaking.
    for i in range(n + 1):
        for j in range(m + 1):
            base = dp[i][j]
            if not math.isfinite(base):
                continue
            if i < n and j < m:
                cost = min(abs(cents_between_midi(detected[j].center_midi, expected[i].midi)) / 100, 5)
                relax(i + 1, j + 1, base + cost, ("match", i, j))
            if i < n:
                relax(i + 1, j, base + 3.5, ("missing", i, j))
            if j < m:
                relax(i, j + 1, base + 1.2, ("extra", i, j))
    assignments: list[int | None] = [None] * n
    extras: list[int] = []
    i, j = n, m
    while i > 0 or j > 0:
        step = prev[i][j]
        if step is None:
            break
        kind, si, sj = step
        if kind == "match":
            assignments[si] = sj
            i, j = i - 1, j - 1
        elif kind == "missing":
            i -= 1
        else:
            extras.append(sj)
            j -= 1
    return Alignment(assignments, list(reversed(extras)), dp[n][m])


def stable_core_samples(segment: Segment, config: TrackerConfig = DEFAULT_CONFIG) -> list[PitchFrame]:
    samples = segment.samples
    if len(samples) <= config.min_core_samples:
        return list(samples)
    trim = config.evaluation_edge_trim_ms
    if segment.duration_ms < 300:
        trim = 35
    if segment.duration_ms < 210:
        trim = 15
    core = [s for s in samples if segment.start_t + trim <= s.t <= segment.end_t - trim]
    if len(core) < config.min_core_samples:
        core = list(samples)
    midi_cents = [s.midi * 100 for s in core]
    center = median(midi_cents)
    mad = median(abs(v - center) for v in midi_cents)
    limit = min(90, max(30, 3 * 1.4826 * mad))
    filtered = [s for s in core if abs(s.midi * 100 - center) <= limit]
    return filtered if len(filtered) >= config.min_core_samples else core


def confidence_for(sample_count: int, analyzed_duration_ms: float, config: TrackerConfig = DEFAULT_CONFIG) -> Grade:
    if sample_count < config.min_core_samples or analyzed_duration_ms < config.low_confidence_ms:
        return Grade("Baixa", "confidence-low", 0)
    if analyzed_duration_ms < config.high_confidence_ms:
        return Grade("Média", "confidence-medium", 1)
    return Grade("Alta", "confidence-high", 2)


def analyze_matched_segment(segment: Segment, expected: ExpectedNote,
                            config: TrackerConfig = DEFAULT_CONFIG) -> NoteEvaluation:
    core = stable_core_samples(segment, config)
    cents = [cents_between_midi(s.midi, expected.midi) for s in core]
    absolute = [abs(c) for c in cents]
    bias = median(cents) if cents else math.nan
    mae = sum(absolute) / len(absolute) if absolute else math.nan
    average = sum(cents) / len(cents) if cents else math.nan
    sigma = math.sqrt(sum((c - average) ** 2 for c in cents) / len(cents)) if len(cents) >= 2 else 0
    rmse = math.sqrt(sum(c * c for c in cents) / len(cents)) if cents else math.nan
    duration = core[-1].t - core[0].t + config.analysis_every_ms if len(core) > 1 else 0
    return NoteEvaluation(expected, segment, core, len(core), duration, bias, mae,
                          percentile(absolute, .9), sigma, rmse, confidence_for(len(core), duration, config))


def grade_tuning(result: NoteEvaluation | None) -> Grade:
    if result is None:
        return Grade("Não detectada", "grade-missing", -1)
    if result.confidence.rank == 0:
        return Grade("Baixa confiança", "grade-uncertain", 0)
    error = abs(result.bias)
    for limit, label, cls, rank in (
        (18, "Excelente", "grade-excellent", 1), (35, "Boa", "grade-good", 2),
        (50, "Atenção", "grade-attention", 3), (70, "Desvio perceptível", "grade-deviation", 4),
    ):
        if error <= limit:
            return Grade(label, cls, rank)
    return Grade("Erro claro", "grade-problem", 5)


def grade_stability(result: NoteEvaluation | None) -> Grade:
    if result is None or result.confidence.rank == 0:
        return Grade("—", "stability-neutral")
    if result.sigma <= 12:
        return Grade("Muito estável", "stability-good")
    if result.sigma <= 25:
        return Grade("Estável", "stability-good")
    if result.sigma <= 40:
        return Grade("Variável", "stability-variable")
    return Grade("Instável", "stability-variable")


def global_grade(score: int) -> str:
    return "Excelente" if score >= 90 else "Boa" if score >= 75 else "Atenção" if score >= 60 else "Refazer"


def global_score(rows: Sequence[NoteEvaluation | None], total: int | None = None) -> GlobalScore:
    total = len(rows) if total is None else total
    if total < len(rows):
        raise ValueError("Total esperado não pode ser menor que as posições avaliadas.")
    reliable = [r for r in rows if r is not None and r.confidence.rank > 0]
    coverage = len(reliable) / total if total else 0
    mean_bias = sum(abs(r.bias) for r in reliable) / len(reliable) if reliable else 100
    mean_stability = sum(r.sigma for r in reliable) / len(reliable) if reliable else 60
    intonation = sum(max(0, 100 - abs(r.bias) * 1.25) for r in reliable) / total if total else 0
    stability = sum(max(0, 100 - r.sigma * 1.8) for r in reliable) / total if total else 0
    score = math.floor(intonation * .70 + stability * .15 + coverage * 100 * .15 + .5)
    return GlobalScore(score, global_grade(score), coverage, mean_bias, mean_stability, len(reliable), total)


def evaluate(expected: Sequence[ExpectedNote], segments: Sequence[Segment],
             config: TrackerConfig = DEFAULT_CONFIG) -> EvaluationReport:
    alignment = align_segments(expected, segments)
    rows = [None if j is None else analyze_matched_segment(segments[j], expected[i], config)
            for i, j in enumerate(alignment.assignments)]
    reliable = [(i, abs(row.bias)) for i, row in enumerate(rows) if row is not None and row.confidence.rank > 0]
    worst = max(reliable, key=lambda pair: pair[1])[0] if reliable else -1
    return EvaluationReport(rows, alignment, global_score(rows, len(expected)), worst)
