from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path

import numpy as np
import pytest

from vocal_app.audio.pitch import PitchDetector
from vocal_app.core.notes import (cents_between_hz, cents_between_midi, hz_to_midi,
    midi_to_hz, midi_to_note, nearest_note, note_to_midi, parse_exercise, parse_guide_pattern, transpose_note)
from vocal_app.core.tracking import PitchFrame, SegmentTracker
from vocal_app.core.evaluation import evaluate, analyze_matched_segment, global_score, grade_tuning, grade_stability
from vocal_app.core.training import FixedTimeline, note_duration_ms, progressed_transpose


@pytest.mark.parametrize('note,midi', [('A4',69),('C4',60),('c#4',61),('D♭4',61),('B#3',60),('Cb4',59),('Fb4',64),('E#4',65),('C-1',0)])
def test_note_names_and_enharmonic_octaves(note, midi):
    assert note_to_midi(note) == midi
    assert hz_to_midi(midi_to_hz(midi)) == pytest.approx(midi)


def test_cents_transposition_rounding_and_invalid_notes():
    assert midi_to_hz(69) == 440
    assert cents_between_hz(880, 440) == pytest.approx(1200)
    assert cents_between_midi(69.25, 69) == 25
    assert transpose_note('B3', 1) == 'C4'
    assert transpose_note('C4', -1) == 'B3'
    assert nearest_note(60.5).midi == 61
    assert midi_to_note(0) == 'C-1'
    for invalid in ('H4', 'C', 'C##4', '4', ''):
        with pytest.raises(ValueError):
            note_to_midi(invalid)
    for hz in (0, -1, math.nan, math.inf):
        with pytest.raises(ValueError):
            hz_to_midi(hz)


@pytest.mark.parametrize('sample_rate',[44100,48000])
@pytest.mark.parametrize('frequency',[65.5,82.4069,110,220,440,987.7666,1190])
def test_synthetic_pitch_across_vocal_range(sample_rate, frequency):
    x = .2 * np.sin(2*np.pi*frequency*np.arange(4096)/sample_rate + .314)
    frame = PitchDetector(sample_rate).detect(x, t=123)
    assert frame is not None
    assert abs(cents_between_hz(frame.hz,frequency)) < 2
    assert frame.clarity > .98
    assert frame.t == 123


@pytest.mark.parametrize('frequency',[82.4069,146.8324,220,440])
def test_pitch_with_stronger_harmonics_and_noise(frequency):
    t = np.arange(4096)/48000
    x = .08*np.sin(2*np.pi*frequency*t)+.2*np.sin(4*np.pi*frequency*t)+.1*np.sin(6*np.pi*frequency*t)
    x += np.random.default_rng(90).normal(0,.002,len(t))
    frame = PitchDetector().detect(x)
    assert frame is not None
    assert abs(cents_between_hz(frame.hz,frequency)) < 4


def test_noise_silence_dc_and_low_rms_rejected():
    detector = PitchDetector()
    for x in (np.zeros(4096), np.ones(4096)*.1, np.random.default_rng(3).normal(0,.1,4096),
              .001*np.sin(2*np.pi*220*np.arange(4096)/48000), np.full(4096,np.nan)):
        assert detector.detect(x) is None
    for frequency in (40,55,1500,2000):
        assert detector.detect(.2*np.sin(2*np.pi*frequency*np.arange(4096)/48000)) is None


def make_frame(t, midi, **kwargs):
    return PitchFrame(t, midi_to_hz(midi), midi, kwargs.get('clarity',.99), kwargs.get('rms',.2))


def sustained_segment(midi, end=600):
    tracker = SegmentTracker(parse_exercise('A3'))
    for t in range(0,end+1,20):
        tracker.feed(make_frame(t,midi))
    return tracker.finish()[0]


def test_acquisition_rejects_attack_and_isolated_excursion():
    tracker = SegmentTracker(parse_exercise('A3'))
    for t,midi in [(0,69),(20,48),(40,57),(60,57),(80,57),(100,57),(120,70),(140,57),(160,57),(180,57)]:
        tracker.feed(make_frame(t,midi))
    result = tracker.finish()
    assert len(result) == 1
    assert result[0].start_t == 40
    assert result[0].nominal_start_t == 0
    assert result[0].center_midi == 57
    assert tracker.outlier_count == 3
    assert tracker.finish() == result  # idempotent finish


def test_gating_silence_and_long_pause():
    tracker = SegmentTracker(parse_exercise('A3 A3'))
    tracker.feed(make_frame(0,57,clarity=.5))
    assert tracker.current is None
    for t in range(20,221,20):
        tracker.feed(make_frame(t,57))
    tracker.feed(None, t=400)
    assert tracker.current is None
    for t in range(420,661,20):
        tracker.feed(make_frame(t,57))
    assert len(tracker.finish()) == 2


def test_tuning_does_not_conflate_instability_and_systematic_bias():
    expected = parse_exercise('A3')[0]
    centered = sustained_segment(57)
    centered.samples = [replace(f,midi=57+(.4 if i%2 else -.4)) for i,f in enumerate(centered.samples)]
    centered_result = analyze_matched_segment(centered, expected)
    assert abs(centered_result.bias) <= 40.00001
    # Use a symmetrical even-length core for a precisely centered vibrato.
    centered.samples = centered.samples[:-1]
    centered.end_t = 580
    centered.duration_ms = 580
    centered_result = analyze_matched_segment(centered, expected)
    assert centered_result.bias == pytest.approx(0)
    assert centered_result.sigma == pytest.approx(40)
    assert grade_tuning(centered_result).label == 'Excelente'
    biased_result = analyze_matched_segment(sustained_segment(57.55), expected)
    assert biased_result.bias == pytest.approx(55)
    assert grade_tuning(biased_result).label == 'Desvio perceptível'
    assert grade_stability(biased_result).label == 'Muito estável'


def test_missing_low_confidence_and_zero_notes_score():
    expected = parse_exercise('A3 B3')
    report = evaluate(expected,[sustained_segment(57)])
    assert report.global_score.score == 50
    assert report.global_score.coverage == .5
    assert report.rows[1] is None
    perfect = analyze_matched_segment(sustained_segment(57), expected[0])
    assert global_score([perfect]).score == 100
    assert global_score([perfect,None,None,None]).score == 25
    assert global_score([]).score == 0
    assert global_score([analyze_matched_segment(sustained_segment(57,120),expected[0])]).score == 0


def test_timeline_guide_lead_ghosts_and_review_contract():
    expected = parse_exercise('A3 A3 B3')
    timeline = FixedTimeline(expected,500,parse_guide_pattern(['A3',None,'B3']))
    assert timeline.lead_ms == 100
    assert timeline.end_t == 1600
    assert timeline.target_index_at(99) == -1
    assert timeline.target_index_at(100) == 0
    assert timeline.target_index_at(600) == 1
    assert timeline.target_index_at(1600) == -1
    assert timeline.guide_start_t(1) == 500
    assert timeline.hidden_during_live(600)
    assert timeline.windows()[1].label == 'A3'  # Written target is retained.
    assert note_duration_ms(80,2) == 375


@pytest.mark.parametrize('action,finished,expected',[('retry',True,2),('close',True,2),('complete',False,2),('complete',True,3)])
def test_only_completion_progresses(action,finished,expected):
    assert progressed_transpose(2,'ascending',action,finished) == expected
    assert progressed_transpose(8,'ascending','complete',True) == 8
    assert progressed_transpose(-8,'descending','complete',True) == -8


REFERENCE = json.loads((Path(__file__).parent/'fixtures'/'js_tracker_reference.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('scenario',REFERENCE['scenarios'],ids=lambda s:s['name'])
def test_regression_against_actual_javascript(scenario):
    expected = parse_exercise(scenario['expected'])
    tracker = SegmentTracker(expected,scenario['note_ms'])
    for event in scenario['events']:
        if event['midi'] is None:
            tracker.no_pitch(event['t'])
        else:
            tracker.ingest(make_frame(event['t'],event['midi']))
    segments = tracker.finish()
    reference = scenario['output']
    assert tracker.outlier_count == reference['outliers']
    assert len(segments) == len(reference['segments'])
    for actual, js in zip(segments,reference['segments']):
        for py_key,js_key in [('start_t','startT'),('end_t','endT'),('nominal_start_t','nominalStartT'),('duration_ms','durationMs'),('center_midi','centerMidi')]:
            assert getattr(actual,py_key) == pytest.approx(js[js_key],abs=1e-9)
        assert [f.t for f in actual.samples] == [f['t'] for f in js['samples']]
    report = evaluate(expected,segments)
    assert report.alignment.assignments == reference['alignment']['assignments']
    assert report.alignment.extras == reference['alignment']['extras']
    assert report.alignment.cost == pytest.approx(reference['alignment']['cost'])
    assert report.global_score.score == reference['global']['score']
    assert report.global_score.coverage == reference['global']['coverage']
    for actual,js in zip(report.rows,reference['rows']):
        if js is None:
            assert actual is None
            continue
        for metric in ('bias','mae','p90','sigma','rmse'):
            assert getattr(actual,metric) == pytest.approx(js[metric],abs=1e-9)
        assert actual.analyzed_duration_ms == js['analyzedDurationMs']
        assert actual.confidence.rank == js['confidence']['rank']
        assert actual.tuning.label == js['tuning']['label']
        assert actual.stability.label == js['stability']['label']
        assert [f.t for f in actual.core_samples] == [f['t'] for f in js['coreSamples']]
