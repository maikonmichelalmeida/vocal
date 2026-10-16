from types import SimpleNamespace
import time

import numpy as np
import pytest
from vocal_app.core.catalog import load_catalog
from vocal_app.core.custom_exercise import parse_custom_exercise
from vocal_app.core.notes import parse_score, midi_to_hz
from vocal_app.core.settings import TrainingSettings, SettingsStore
from vocal_app.core.training import FixedTimeline
from vocal_app.core.guide import apply_guide_level
from vocal_app.ui.main_window import MainWindow
from vocal_app.ui.training_dialog import TrainingDialog
from vocal_app.ui.widgets import PitchPlot
from vocal_app.core.tracking import PitchFrame
from test_ui import FakeGuide, FakeCapture


def test_rest_parser_and_clock_scale_with_bpm():
    ex = parse_custom_exercise("C3 P D3\n1000 500 1000")
    assert ex.vocal_notes == ex.guide_notes == ("C3",None,"D3")
    settings = TrainingSettings(bpm=120)
    timeline = FixedTimeline(parse_score(ex.vocal_notes), 500, durations_ms=settings.custom_durations_ms(ex))
    assert [(w.start_t,w.end_t,w.index) for w in timeline.windows()] == [(200,1200,0),(1700,2700,1)]
    assert timeline.target_index_at(1200) == -1 and timeline.is_rest(1500)
    assert not timeline.hidden_during_live(1500)  # A rest is not a ghost note.
    assert timeline.target_index_at(1700) == 1
    assert timeline.note_durations_ms == (1000,1000)
    assert TrainingSettings(bpm=60).custom_durations_ms(ex) == (2000,1000,2000)
    with pytest.raises(ValueError, match="pelo menos uma nota"):
        parse_custom_exercise("P P\n500 500")


def test_leading_trailing_and_consecutive_rests_preserve_note_guides():
    ex = parse_custom_exercise("P C3 P P D3 P\n100 1000 100 200 1000 300")
    positions = parse_score(ex.vocal_notes)
    timeline = FixedTimeline(positions,500,durations_ms=ex.durations_ms)
    assert timeline.is_rest(20) and timeline.is_rest(timeline.end_t - 1)
    guide = apply_guide_level(positions, "total", [0,2,3,5])
    assert guide[1].label == "C3" and sum(n is not None for n in guide) == 1


@pytest.mark.parametrize("exercise", [parse_custom_exercise("C3 P C3\n1000 50 1000"), load_catalog().by_id[27]])
def test_training_rest_does_not_become_a_missing_note_or_merge_repetitions(qtbot, exercise):
    win = TrainingDialog(exercise, TrainingSettings(bpm=exercise.bpm, subdivision=exercise.subdivision),
                         "acoustic_grand_piano", auto_start=False, capture_factory=FakeCapture, guide_factory=FakeGuide)
    qtbot.addWidget(win)
    win.capture,win.guide=FakeCapture(),FakeGuide()
    win.state="LISTENING"
    for t in np.arange(win.timeline.lead_ms + 40, win.timeline.end_t - 20, 20):
        index = win.timeline.target_index_at(t)
        midi = win.expected[index].midi if index >= 0 else 60
        frame = PitchFrame(float(t),midi_to_hz(midi),midi,.99,.2)
        win.capture.events.append(SimpleNamespace(t=float(t),frame=frame,rms=.2))
    win.capture.elapsed_ms=win.timeline.end_t+1
    win.tick_listening()
    qtbot.waitUntil(lambda:win.future.done())
    win.tick()
    assert win.report.global_score.score == 100
    assert win.table.rowCount() == (15 if exercise.id==27 else 2)
    assert not win.report.alignment.extras
    assert all(not win.timeline.is_rest(f.t) for f in win.frames)
    assert np.isnan(win.plot.voice.getData()[1]).any()
    win.reject()


def test_preview_is_silent_at_rest_and_resumes_transposed(qtbot,tmp_path,monkeypatch):
    from vocal_app.ui import main_window
    monkeypatch.setattr(main_window,"GuidePlayer",FakeGuide)
    win=MainWindow(SettingsStore(tmp_path/'settings.json'))
    qtbot.addWidget(win)
    win.session_select.setCurrentIndex(win.session_select.findData('I'))
    path=tmp_path/'rest.txt';path.write_text('C3 P D3\n1000 500 1000')
    assert win.load_custom_file(path)
    win.transpose.setValue(12)
    win.start_preview();win.preview_timer.stop();win._preview_tick()
    start=win.preview_started
    assert [c for c in win.preview.calls if c[0]=='note'][-1][1][0]==60
    monkeypatch.setattr(main_window.time,'perf_counter',lambda:start+1.2)
    win._preview_tick()
    assert len([c for c in win.preview.calls if c[0]=='note'])==1
    assert 'pausa' in win.status.text()
    monkeypatch.setattr(main_window.time,'perf_counter',lambda:start+1.6)
    win._preview_tick()
    assert [c for c in win.preview.calls if c[0]=='note'][-1][1][0]==62
    win.stop_preview();win.close()


def test_three_note_run_is_five_complete_phrases():
    ex=load_catalog().by_id[27]
    assert len([n for n in ex.vocal_notes if n])==15
    assert sum(n is None for n in ex.vocal_notes)==4
    assert ex.vocal_notes[:4]==('D#3','C#3','B2',None)
    settings=TrainingSettings(bpm=96,subdivision=2)
    durations=settings.custom_durations_ms(ex)
    assert durations[3]==durations[0]/2
    assert len(durations)==19


def test_graph_keeps_short_rest_blank(qtbot):
    ex=parse_custom_exercise('C3 P C3\n1000 50 1000')
    plot=PitchPlot();qtbot.addWidget(plot)
    plot.configure(parse_score(ex.vocal_notes),500,ex.durations_ms)
    frames=[PitchFrame(t,midi_to_hz(48),48,.99,.2) for t in (1190,1260)]
    plot.update_frames(frames,1300,review=True)
    assert np.isnan(plot.voice.getData()[1]).sum()==1
