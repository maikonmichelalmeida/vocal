from dataclasses import replace
from functools import partial

import pytest
from PySide6.QtCore import Qt
from vocal_app.core.catalog import load_catalog
from vocal_app.core.evaluation import evaluate
from vocal_app.core.settings import SettingsStore, TrainingSettings
from vocal_app.ui.main_window import MainWindow
from vocal_app.ui.training_dialog import TrainingDialog
from test_ui import FakeCapture, FakeGuide


def finish_with_score(dialog, score):
    report = evaluate(dialog.expected, [])
    dialog.render_report(replace(report, global_score=replace(report.global_score, score=score)))


@pytest.mark.parametrize("score,step", [(74,0),(75,1),(100,1)])
@pytest.mark.parametrize("direction", [1,-1])
def test_space_starts_next_attempt_in_same_window_without_double_progression(qtbot,tmp_path,monkeypatch,score,step,direction):
    from vocal_app.ui import training_dialog
    monkeypatch.setattr(training_dialog,"TrainingDialog",partial(TrainingDialog,auto_start=False,capture_factory=FakeCapture,guide_factory=FakeGuide))
    win=MainWindow(SettingsStore(tmp_path/'settings.json'))
    qtbot.addWidget(win);win.show();win.show_exercise(13)
    win.transpose.setValue(10)
    win.direction.setCurrentIndex(0 if direction == 1 else 1)
    step *= direction
    win.activateWindow()
    qtbot.waitUntil(win.isActiveWindow)
    win.start_button.setFocus()
    qtbot.keyClick(win.start_button,Qt.Key.Key_Space)
    dialog=win.dialog
    finish_with_score(dialog,score)
    assert win.transpose.value()==10+step
    assert dialog.settings.transpose==10  # The displayed report still describes the completed take.
    assert dialog.next_button.text() == ("Próxima · Espaço" if step else "Repetir · Espaço")
    dialog.activateWindow();dialog.raise_()
    qtbot.waitUntil(dialog.isActiveWindow)
    dialog.complete_button.setFocus()  # Space must advance, not activate the focused close button.
    qtbot.keyClick(dialog.complete_button,Qt.Key.Key_Space)
    dialog.timer.stop()
    assert win.dialog is dialog
    assert dialog.state=='PREPARING'
    assert dialog.settings.transpose==10+step
    assert dialog.report is None and dialog.pages.currentWidget() is dialog.live_page
    assert not dialog.plot.report_voice_traces
    finish_with_score(dialog,score)
    assert win.transpose.value()==10+2*step
    dialog.close()
    assert win.transpose.value()==10+2*step
    win.close()


def test_space_never_cancels_running_training_and_repeat_keeps_tone(qtbot):
    dialog=TrainingDialog(load_catalog().by_id[13],TrainingSettings(transpose=5),"acoustic_grand_piano",
                          auto_start=False,capture_factory=FakeCapture,guide_factory=FakeGuide)
    qtbot.addWidget(dialog);dialog.show();dialog.activateWindow()
    qtbot.waitUntil(dialog.isActiveWindow)
    dialog.state='LISTENING'
    qtbot.keyClick(dialog,Qt.Key.Key_Space)
    assert dialog.state=='LISTENING'
    finish_with_score(dialog,100)
    assert dialog.next_settings.transpose==6
    dialog.retry_button.click();dialog.timer.stop()
    assert dialog.settings.transpose==5 and dialog.state=='PREPARING'
    dialog.close()
