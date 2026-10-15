import numpy as np
import pytest

from vocal_app.core.evaluation import evaluate
from vocal_app.core.notes import parse_exercise, midi_to_hz
from vocal_app.core.tracking import SegmentTracker, PitchFrame
from vocal_app.ui.widgets import PitchPlot


def report_for(biases):
    expected = parse_exercise("C3 E3 G3 B3 D4")
    tracker = SegmentTracker(expected, 1000)
    for i, (note, bias) in enumerate(zip(expected, biases)):
        for t in range(i * 1000 + 240, i * 1000 + 1160, 20):
            midi = note.midi + bias / 100
            tracker.ingest(PitchFrame(t, midi_to_hz(midi), midi, .99, .2))
    return expected, evaluate(expected, tracker.finish())


@pytest.mark.parametrize("biases,worst", [([0,25,42,60,80],4), ([0,-25,30,15,10],-1), ([0,25,-45,20,30],2)])
def test_report_highlights_match_grades_and_do_not_penalize_good_notes(qtbot, biases, worst):
    notes, report = report_for(biases)
    plot = PitchPlot()
    qtbot.addWidget(plot)
    plot.configure(notes, 1000)
    target_data = [values.copy() for values in plot.target.getData()]
    frames = sorted([f for row in report.rows if row for f in row.segment.samples], key=lambda f: f.t)
    plot.highlight_report(report, frames)
    assert plot.highlighted_index == worst
    assert len(plot.report_voice_traces) == len(notes)
    assert plot.target.isVisible()
    assert plot.target.opts["pen"].widthF() == 3
    assert plot.target.opts["pen"].color().name() == "#ff5267"
    for before, after in zip(target_data, plot.target.getData()):
        np.testing.assert_array_equal(before, after)
    for i, item in enumerate(plot.report_voice_traces):
        pen = item.opts["pen"]
        assert pen.widthF() > 3
        if abs(biases[i]) <= 35:
            assert pen.color().name() == "#77cea0"
        if i == worst:
            assert pen.color().name() == "#ff6679" and pen.widthF() == 6
        x, y = item.getData()
        assert x[0] == pytest.approx(.24 + i)
        assert np.allclose(y, notes[i].midi + biases[i] / 100)
    # Re-rendering must not accumulate old highlights or leak them into a new attempt.
    plot.highlight_report(report, frames)
    assert len(plot.report_voice_traces) == 5
    plot.configure(notes, 1000)
    assert not plot.report_voice_traces and plot.target.isVisible()


def test_missing_notes_stay_distinct_from_reliable_bad_tuning(qtbot):
    notes = parse_exercise("C3 E3")
    plot = PitchPlot()
    qtbot.addWidget(plot)
    plot.configure(notes, 500)
    plot.highlight_report(evaluate(notes, []), [])
    assert plot.highlighted_index == -1
    assert not plot.report_voice_traces  # Do not invent a performed line where there was silence.
    assert plot.target.isVisible()


def test_highlights_preserve_gaps_and_actual_voice_samples(qtbot):
    notes, report = report_for([0,25,42,60,80])
    frames = sorted([f for row in report.rows if row for f in row.segment.samples if not 500 <= f.t <= 700], key=lambda f: f.t)
    plot = PitchPlot()
    qtbot.addWidget(plot)
    plot.configure(notes, 1000)
    plot.highlight_report(report, frames)
    x, y = plot.report_voice_traces[0].getData()
    assert np.isnan(x).sum() == np.isnan(y).sum() == 1
    expected = [f for f in frames if report.rows[0].segment.start_t <= f.t < report.rows[0].segment.end_t]
    np.testing.assert_allclose(x[np.isfinite(x)], [f.t / 1000 for f in expected])
    np.testing.assert_allclose(y[np.isfinite(y)], [f.midi for f in expected])
