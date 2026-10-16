from types import SimpleNamespace

import numpy as np
import pytest
from PySide6.QtWidgets import QScrollArea

from vocal_app.core.custom_exercise import parse_custom_exercise, load_custom_exercise
from vocal_app.core.notes import parse_exercise, midi_to_hz
from vocal_app.core.training import FixedTimeline
from vocal_app.core.tracking import SegmentTracker, PitchFrame
from vocal_app.core.settings import TrainingSettings, SettingsStore
from vocal_app.core.evaluation import evaluate
from vocal_app.ui.main_window import MainWindow
from vocal_app.ui.training_dialog import TrainingDialog, GRADE_COLORS
from test_ui import FakeGuide, FakeCapture


def test_parse_notes_times_and_bom(tmp_path):
    path = tmp_path / "Meu treino.txt"
    path.write_text("B3 D4 G4 E4\n500 800 1000 250\n", encoding="utf-8-sig")
    ex = load_custom_exercise(path)
    assert ex.name == "Meu treino"
    assert ex.vocal_notes == ex.guide_notes == ("B3", "D4", "G4", "E4")
    assert ex.durations_ms == (500, 800, 1000, 250)
    assert ex.mode == "pitch" and not ex.audio and ex.image is None
    assert parse_custom_exercise("b3 D♭4 F♯4\n500 500 500").vocal_notes == ("B3", "C#4", "F#4")


@pytest.mark.parametrize("text", ["", "B3 D4", "B3 D4\n500", "B3\n0", "B3\n-2", "B3\nNaN",
                                      "B3\n500.5", "B3\n60001", "H3\n500", "B999\n500",
                                      "B3\n500\nextra", "B3\n\n500", "B3 " * 257 + "\n" + "500 " * 257,
                                      "B3 " * 11 + "\n" + "60000 " * 11])
def test_reject_invalid_scores(text):
    with pytest.raises(ValueError):
        parse_custom_exercise(text)


def test_reject_invalid_file_types_and_size(tmp_path):
    for filename, content in (("score.csv", b"B3\n500"), ("large.txt", b"x" * 65537), ("bad.txt", b"\xff\xff")):
        path = tmp_path / filename
        path.write_bytes(content)
        with pytest.raises(ValueError):
            load_custom_exercise(path)


def test_variable_clock_boundaries():
    notes = parse_exercise("B3 D4 G4 E4")
    timeline = FixedTimeline(notes, 999, durations_ms=(500, 800, 1000, 250))
    assert timeline.lead_ms == 100
    assert timeline.end_t == 2650
    assert [(w.start_t, w.end_t) for w in timeline.windows()] == [(100,600),(600,1400),(1400,2400),(2400,2650)]
    assert [timeline.target_index_at(t) for t in (99,100,599,600,1399,1400,2399,2400,2650)] == [-1,0,0,1,1,2,2,3,-1]
    assert [timeline.guide_index_at(t) for t in (0,499,500,1299,1300,2300)] == [0,0,1,1,2,3]
    with pytest.raises(ValueError):
        FixedTimeline(notes, 500, durations_ms=(500, 200))


def test_repeated_notes_follow_individual_durations():
    notes = parse_exercise("C4 C4 C4")
    tracker = SegmentTracker(notes, 999, durations_ms=(500,1000,300))
    for t in range(100, 1900, 20):
        tracker.ingest(PitchFrame(t, midi_to_hz(60), 60, .99, .2))
    segments = tracker.finish()
    assert len(segments) == 3
    assert [s.nominal_start_t for s in segments] == [100, 600, 1600]
    assert evaluate(notes, segments).global_score.score == 100


def test_custom_navigation_validation_preview_and_progress(qtbot, tmp_path, monkeypatch):
    from vocal_app.ui import main_window
    monkeypatch.setattr(main_window, "GuidePlayer", FakeGuide)
    win = MainWindow(SettingsStore(tmp_path / "settings.json"))
    qtbot.addWidget(win)
    win.show()
    win.session_select.setCurrentIndex(win.session_select.findData("I"))
    assert win.exercise is None and not win.start_button.isEnabled()
    path = tmp_path / "score.txt"
    path.write_text("B3 D4 G4 E4\n500 800 1000 250")
    assert win.load_custom_file(path)
    assert win.start_button.isEnabled() and win.bpm.isEnabled()
    win.bpm.setValue(60)
    assert win.custom_plot.timeline.durations_ms == (1000,1600,2000,500)
    assert "5.1 s" in win.objective.text()
    assert not win.demo.isVisible() and win.demo.player.source().isEmpty()
    win.start_preview()
    win.preview_timer.stop()
    win._preview_tick()
    start = win.preview_started
    monkeypatch.setattr(main_window.time, "perf_counter", lambda: start + 2.59)
    win._preview_tick()
    assert win.preview_index == 1
    monkeypatch.setattr(main_window.time, "perf_counter", lambda: start + 2.61)
    win._preview_tick()
    assert win.preview_index == 2
    win.stop_preview()
    win.complete_training(100)
    assert win.transpose.value() == 1
    assert win.exercise.durations_ms == (500,800,1000,250)
    assert win.bpm.value() == 60
    assert SettingsStore(win.store.path).training(win.exercise).bpm == 60
    path.write_text("B3 D4\n500")
    assert not win.load_custom_file(path)
    assert not win.start_button.isEnabled() and win.exercise is None
    win.start_training()
    assert win.dialog is None
    win.session_select.setCurrentIndex(0)
    assert win.exercise.id != 40 and win.demo.isVisible() and win.bpm.isEnabled()
    win.close()


@pytest.mark.parametrize("bpm", [60,120,180])
def test_custom_training_report_and_retry(qtbot, bpm):
    ex = parse_custom_exercise("B3 D4 G4 E4\n500 800 1000 600")
    win = TrainingDialog(ex, TrainingSettings(bpm=bpm), "acoustic_grand_piano", auto_start=False,
                         guide_factory=FakeGuide, capture_factory=FakeCapture)
    qtbot.addWidget(win)
    win.guide, win.capture = FakeGuide(), FakeCapture()
    win.state = "LISTENING"
    for target in win.timeline.windows():
        for t in np.arange(target.start_t + 50, target.end_t - 30, 20):
            frame = PitchFrame(float(t), midi_to_hz(target.midi), target.midi, .99, .2)
            win.capture.events.append(SimpleNamespace(t=float(t), frame=frame, rms=.2))
    win.capture.elapsed_ms = win.timeline.end_t + 1
    win.tick_listening()
    qtbot.waitUntil(lambda: win.future.done())
    win.tick()
    assert win.report.global_score.score == 100
    assert win.table.item(0, 0).background().color().name() == GRADE_COLORS["grade-excellent"][0]
    assert win.plot.viewRange()[0][1] > 3000 * 120 / bpm / 1000
    assert win.timeline.end_t == pytest.approx(3000 * 120 / bpm)
    assert win.plot.timeline.end_t == win.timeline.end_t
    assert len(win.plot.report_voice_traces) == 4 and win.plot.highlighted_index == -1
    win.retry()
    assert win.tracker.durations_ms == tuple(d * 120 / bpm for d in ex.durations_ms)
    assert win.plot.report_voice_traces == [] and win.plot.target.isVisible()
    win.reject()


@pytest.mark.parametrize("size", [(850,550),(1100,650),(1280,800)])
def test_preparation_entire_image_fits(qtbot, tmp_path, size):
    win = MainWindow(SettingsStore(tmp_path / "settings.json"))
    qtbot.addWidget(win)
    win.show_exercise(13)
    win.show()
    win.resize(*size)
    qtbot.wait(40)
    assert not win.findChildren(QScrollArea)
    rect = win.tab_view.mapFromScene(win.tab_view.item.sceneBoundingRect()).boundingRect()
    assert win.tab_view.viewport().rect().contains(rect)
    assert win.demo.isVisible() and win.demo.play.text() == "Tocar exemplo"
    assert win.demo.mapTo(win, win.demo.rect().topLeft()).y() < 110
    assert win.guide_level.mapTo(win, win.guide_level.rect().topLeft()).y() == win.guided.mapTo(win, win.guided.rect().topLeft()).y() or abs(win.guide_level.y() - win.guided.y()) < 15
    assert win.guide_level.width() < win.width() * .30
    win.close()
