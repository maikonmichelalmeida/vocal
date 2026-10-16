"""Exercise navigation and complete Qt training flows, without a microphone."""
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
import time
from types import SimpleNamespace
import numpy as np
import pytest

from vocal_app.core.catalog import load_catalog
from vocal_app.core.settings import SettingsStore, TrainingSettings
from vocal_app.core.notes import midi_to_hz
from vocal_app.core.tracking import PitchFrame
from vocal_app.ui.main_window import MainWindow
from vocal_app.ui.training_dialog import TrainingDialog
from vocal_app.ui.widgets import PitchPlot


class FakeGuide:
    def __init__(self):
        self.calls = []
        self.last_error = ""
        self.ready = True
    def prepare(self, *args):
        self.calls.append(("prepare", args))
        future = Future()
        future.set_result(True)
        return future
    def note_on(self, *args, **kwargs): self.calls.append(("note", args))
    def click(self, **kwargs): self.calls.append(("click", kwargs))
    def stop(self): self.calls.append(("stop",))
    def close(self): self.calls.append(("close",))


class FakeCapture:
    def __init__(self):
        self.elapsed_ms = 0
        self.last_error = ""
        self.dropped_analysis_blocks = 0
        self.events = []
        self.stopped = False
    def start(self): return self
    def drain_frames(self):
        result, self.events = self.events, []
        return result
    def stop(self): self.stopped = True


@pytest.fixture
def window(qtbot, tmp_path):
    win = MainWindow(store=SettingsStore(tmp_path / "settings.json"))
    qtbot.addWidget(win)
    win.show()
    yield win
    win.close()


def dialog(qtbot, exercise_id=4, **kwargs):
    exercise = load_catalog().by_id[exercise_id]
    win = TrainingDialog(exercise, TrainingSettings(), "acoustic_guitar_nylon",
                         capture_factory=FakeCapture, guide_factory=FakeGuide, auto_start=False, **kwargs)
    qtbot.addWidget(win)
    win.show()
    return win


def test_navigation_all_exercises_and_sessions(window):
    assert window.exercise_select.count() == 39
    assert window.session_select.count() == 9
    for exercise in window.catalog.exercises:
        window.show_exercise(exercise.id)
        assert window.title.text() == exercise.name
        assert window.demo.player.source().toLocalFile().endswith(exercise.audio.replace("/", "/").split("/")[-1])
        assert bool(window.tab_view.item) == bool(exercise.image)
    for key, ids in window.catalog.sessions.items():
        window.session_select.setCurrentIndex(window.session_select.findData(key))
        window.choose_session()
        assert window.exercise.id == ids[0]
        window.move(-1)
        assert window.exercise.id == ids[-1]
        window.move(1)
        assert window.exercise.id == ids[0]


def test_preferences_per_exercise_and_progress_only_complete(window, tmp_path):
    window.show_exercise(4)
    window.transpose.setValue(3)
    window.bpm.setValue(144)
    window.guided.setChecked(False)
    window.show_exercise(5)
    assert window.transpose.value() == 0
    window.show_exercise(4)
    assert window.transpose.value() == 3
    assert window.bpm.value() == 144
    assert not window.guided.isChecked()
    store = SettingsStore(window.store.path)
    assert store.training(window.exercise).transpose == 3
    window.complete_training(100)
    assert window.transpose.value() == 4


@pytest.mark.parametrize("action,finished,expected", [("retry",True,3),("close",True,3),("complete",False,3),("complete",True,4)])
def test_settings_actions(action, finished, expected):
    assert TrainingSettings(transpose=3).after_action(action, finished, score=100).transpose == expected
    assert TrainingSettings(transpose=8).after_action("complete", True, score=100).transpose == 9
    assert TrainingSettings(transpose=-8, direction_up=False).after_action("complete", True, score=100).transpose == -9


def test_complete_synthetic_training_report_and_retry(qtbot):
    win = dialog(qtbot)
    win.guide = FakeGuide()
    win.capture = FakeCapture()
    win.state = "LISTENING"
    for target in win.timeline.windows():
        for t in np.arange(target.start_t + 50, target.end_t - 30, 20):
            frame = PitchFrame(float(t), midi_to_hz(target.midi), target.midi, .99, .2)
            win.capture.events.append(SimpleNamespace(t=float(t), frame=frame, rms=.2))
    win.capture.elapsed_ms = win.timeline.end_t + 1
    win.tick_listening()
    qtbot.waitUntil(lambda: win.future.done(), timeout=3000)
    win.tick()
    assert win.state == "DONE"
    assert win.report.global_score.score == 100
    assert win.table.rowCount() == 5
    assert win.complete_button.isEnabled()
    assert all(win.table.item(i,2).text() != "Não identificada" for i in range(5))
    win.retry()
    assert win.settings.transpose == 0
    assert win.state == "PREPARING"
    assert not win.complete_button.isEnabled()
    win.reject()


def test_silence_scores_zero_and_complete_emits_once(qtbot):
    win = dialog(qtbot)
    emissions = []
    win.completed.connect(lambda score: emissions.append(score))
    win.complete()
    assert not emissions
    win.guide, win.capture = FakeGuide(), FakeCapture()
    win.state = "LISTENING"
    win.capture.elapsed_ms = win.timeline.end_t + 1
    win.tick_listening()
    qtbot.waitUntil(lambda: win.future.done())
    win.tick()
    assert win.report.global_score.score == 0
    win.complete()
    win.complete()
    assert emissions == [0]


def test_breathing_needs_no_bank_or_microphone(qtbot):
    win = dialog(qtbot, 1)
    win.prepare()
    win.timer.stop()
    assert win.state == "COUNTDOWN"
    assert not any(call[0] == "prepare" for call in win.guide.calls)
    win.phase_started = time.perf_counter() - 2
    win.tick()
    assert win.state == "BREATHING"
    assert win.capture is None
    win.phase_started = time.perf_counter() - 31
    win.tick()
    assert win.state == "DONE"
    assert win.report is None
    assert win.complete_button.isEnabled()
    win.reject()


def test_missing_bank_is_explicit_and_can_train_unaccompanied(qtbot):
    win = dialog(qtbot)
    win.guide = FakeGuide()
    win.state = "PREPARING"
    win.future = Future()
    win.future.set_exception(RuntimeError("SoundFont ausente"))
    win.tick()
    assert win.state == "AUDIO_ERROR"
    assert "SoundFont ausente" in win.status.text()
    win.continue_unaccompanied()
    assert win.allow_unaccompanied
    assert win.state == "COUNTDOWN"
    win.reject()


def test_ghost_trace_hidden_only_live(qtbot):
    plot = PitchPlot()
    qtbot.addWidget(plot)
    frames = [PitchFrame(t, 220, 57, .99, .2, hidden_during_live=ghost)
              for t,ghost in [(10,False),(30,False),(50,True),(70,True),(90,False)]]
    plot.update_frames(frames, 100)
    _, y = plot.voice.getData()
    assert np.isfinite(y).sum() == 3
    plot.update_frames(frames, 100, review=True)
    _, y = plot.voice.getData()
    assert np.isfinite(y).sum() == 5


def test_breathing_preview_does_not_prepare_bank(window, monkeypatch):
    from vocal_app.ui import main_window
    monkeypatch.setattr(main_window, "GuidePlayer", FakeGuide)
    window.show_exercise(1)
    window.start_preview()
    window.preview_timer.stop()
    window._preview_tick()
    assert not any(call[0] == "prepare" for call in window.preview.calls)
    assert any(call[0] == "click" for call in window.preview.calls)
    window.stop_preview()


def test_level_selection_persisted_and_used_by_preview(window, monkeypatch):
    from vocal_app.ui import main_window
    monkeypatch.setattr(main_window, "GuidePlayer", FakeGuide)
    window.show_exercise(13)
    window.guide_level.setCurrentIndex(window.guide_level.findData("total"))
    window.start_preview()
    window.preview_timer.stop()
    window._preview_tick()
    window.preview_started = time.perf_counter() - window.settings().note_duration_ms / 1000 * 2.5
    window._preview_tick()
    assert len([call for call in window.preview.calls if call[0] == "note"]) == 1
    window.stop_preview()
    window.show_exercise(4)
    assert window.guide_level.currentData() == "integral"
    window.show_exercise(13)
    assert window.guide_level.currentData() == "total"


def test_ghost_level_applies_to_sound_and_trace_but_not_evaluation(qtbot):
    win = TrainingDialog(load_catalog().by_id[13], TrainingSettings(guide_level="total"),
                         "acoustic_guitar_nylon", capture_factory=FakeCapture, guide_factory=FakeGuide, auto_start=False)
    qtbot.addWidget(win)
    win.guide, win.capture = FakeGuide(), FakeCapture()
    win.state = "LISTENING"
    for target in win.timeline.windows():
        for t in np.arange(target.start_t + 50, target.end_t - 30, 20):
            frame = PitchFrame(float(t), midi_to_hz(target.midi), target.midi, .99, .2)
            win.capture.events.append(SimpleNamespace(t=float(t), frame=frame, rms=.2))
        win.capture.elapsed_ms = target.start_t + 100
        win.tick_listening()
    assert len([c for c in win.guide.calls if c[0] == "note"]) == 1
    assert all(f.hidden_during_live for f in win.frames if f.t >= win.timeline.target_start_t(1))
    assert "oculta" in win.live.text()
    from vocal_app.core.evaluation import evaluate
    win.render_report(evaluate(win.expected, win.tracker.finish()))
    assert win.report.global_score.score == 100
    assert np.isfinite(win.plot.voice.getData()[1]).sum() == len(win.frames)
    win.reject()


@pytest.mark.parametrize("size", [(800,500), (1100,650), (1280,800)])
def test_live_and_report_layout_fit_without_outer_scrolling(qtbot, size):
    from PySide6.QtWidgets import QScrollArea
    from vocal_app.core.evaluation import evaluate
    win = dialog(qtbot, 13)
    win.resize(*size)
    qtbot.wait(30)
    assert not win.findChildren(QScrollArea)
    assert win.plot.height() > win.height() * .58
    assert win.header.height() < win.height() * .2
    assert win.plot.mapTo(win, win.plot.rect().bottomRight()).y() < win.height()
    assert win.close_button.mapTo(win, win.close_button.rect().bottomRight()).y() < win.height()
    win.render_report(evaluate(win.expected, []))
    qtbot.wait(30)
    assert win.pages.currentWidget() is win.report_page
    assert win.plot.width() < win.table.width() * .6
    assert win.plot.height() <= 240
    assert win.table.height() > win.height() * .5
    assert win.table.horizontalScrollBar().maximum() == 0
    assert win.table.verticalScrollBar().maximum() == 0  # all nine notes fit
    win.reject()


def test_plot_fits_complete_sequence_and_voice_with_padding(qtbot):
    from vocal_app.core.notes import parse_exercise
    plot = PitchPlot()
    qtbot.addWidget(plot)
    expected = parse_exercise("C3 G3 C4 G3 C3")
    plot.configure(expected, 3000)
    frames = [PitchFrame(t, midi_to_hz(m), m, .99, .2) for t,m in [(100,43),(1000,75),(10000,60),(14000,50)]]
    for review in (False, True):
        plot.update_frames(frames, 15000, review)
        (left,right),(bottom,top) = plot.viewRange()
        assert left < 0 < right and right > 15.6
        assert bottom < 43 and top > 75
        assert np.isfinite(plot.voice.getData()[1]).sum() == 4  # includes frames older than 8s
