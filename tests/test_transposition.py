from dataclasses import replace
import pytest

from vocal_app.core.catalog import load_catalog
from vocal_app.core.custom_exercise import parse_custom_exercise
from vocal_app.core.notes import note_to_midi, midi_to_hz
from vocal_app.core.settings import TrainingSettings, SettingsStore
from vocal_app.core.tracking import DEFAULT_CONFIG
from vocal_app.core.transposition import transpose_limits, MIN_TRAINING_MIDI, MAX_TRAINING_MIDI
from vocal_app.ui.main_window import MainWindow
from vocal_app.ui.training_dialog import TrainingDialog
from test_ui import FakeGuide


@pytest.mark.parametrize("exercise", load_catalog().exercises, ids=lambda ex: str(ex.id))
def test_every_catalog_exercise_uses_full_supported_range(exercise):
    lower, upper = transpose_limits(exercise)
    if exercise.mode == "breathing":
        assert (lower, upper) == (0,0)
        return
    pitches = [note_to_midi(n) for n in (*exercise.vocal_notes, *exercise.guide_notes) if n]
    assert min(pitches) + lower == MIN_TRAINING_MIDI == 36
    assert max(pitches) + upper == MAX_TRAINING_MIDI == 86
    for offset in (lower, upper):
        assert all(DEFAULT_CONFIG.min_hz <= midi_to_hz(m + offset) <= DEFAULT_CONFIG.max_hz for m in pitches)
    assert TrainingSettings(transpose=upper).after_action("complete", True, exercise, score=100).transpose == upper
    assert TrainingSettings(transpose=lower, direction_up=False).after_action("complete", True, exercise, score=100).transpose == lower


def test_custom_range_uses_extremes_and_includes_instrument_guide():
    ex = parse_custom_exercise("B3 D4 G4 E4\n500 500 500 500")
    assert transpose_limits(ex) == (-23,19)
    assert transpose_limits(replace(ex, guide_notes=("C3","D4","G4","E5"))) == (-12,10)
    assert transpose_limits(parse_custom_exercise("C-1 D-1\n500 500")) == (36,84)
    with pytest.raises(ValueError, match="excede a faixa"):
        parse_custom_exercise("C2 D#6\n500 500")


def test_preferences_keep_large_offsets_and_fit_new_custom_scores(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    ex = parse_custom_exercise("B3 D4 G4 E4\n500 500 500 500")
    store.set_training(40, TrainingSettings(transpose=15, bpm=60))
    assert SettingsStore(store.path).training(ex).transpose == 15
    high = parse_custom_exercise("C6 D6\n500 500")
    assert store.training(high).transpose == 0
    assert store.training(high).bpm == 60
    low = parse_custom_exercise("C1 D1\n500 500")
    assert TrainingSettings(transpose=0).for_exercise(low).transpose == 12


def test_custom_and_standard_ui_guide_and_training_share_transposition(qtbot, tmp_path, monkeypatch):
    from vocal_app.ui import main_window
    monkeypatch.setattr(main_window, "GuidePlayer", FakeGuide)
    win = MainWindow(SettingsStore(tmp_path / "settings.json"))
    qtbot.addWidget(win)
    win.show()
    for ex in win.catalog.exercises:
        win.show_exercise(ex.id)
        assert (win.transpose.minimum(), win.transpose.maximum()) == transpose_limits(ex)
    win.show_exercise(13)
    win.transpose.setValue(12)
    assert win.settings().transpose == 12
    win.complete_training(100)
    assert win.transpose.value() == 13
    win.session_select.setCurrentIndex(win.session_select.findData("I"))
    path = tmp_path / "custom.txt"
    path.write_text("B3 D4 G4 E4\n500 800 1000 500")
    assert win.load_custom_file(path)
    win.bpm.setValue(60)
    win.transpose.setValue(-12)
    assert "B2" in win.sequence.text() and "G3" in win.sequence.text()
    win.start_preview()
    win.preview_timer.stop()
    win._preview_tick()
    assert next(c for c in win.preview.calls if c[0] == "note")[1][0] == note_to_midi("B2")
    win.stop_preview()
    dialog = TrainingDialog(win.exercise, win.settings(), "acoustic_grand_piano", auto_start=False)
    qtbot.addWidget(dialog)
    assert [n.label for n in dialog.expected] == ["B2","D3","G3","E3"]
    assert [n.midi for n in dialog.guide_pattern] == [n.midi for n in dialog.expected]
    assert dialog.plot.expected == dialog.expected
    assert dialog.timeline.durations_ms == (1000,1600,2000,1000)
    dialog.reject()
    lower, upper = transpose_limits(win.exercise)
    win.transpose.setValue(upper + 100)
    assert win.transpose.value() == upper
    win.complete_training(100)
    assert win.transpose.value() == upper and "limite de tom" in win.status.text()
    win.direction.setCurrentIndex(1)
    win.transpose.setValue(lower - 100)
    win.complete_training(100)
    assert win.transpose.value() == lower
    win.close()


def test_direct_dialog_clamps_invalid_setting_before_building_targets(qtbot):
    ex = load_catalog().by_id[13]
    dialog = TrainingDialog(ex, TrainingSettings(transpose=999), "acoustic_grand_piano", auto_start=False)
    qtbot.addWidget(dialog)
    assert dialog.settings.transpose == transpose_limits(ex)[1]
    assert max(n.midi for n in dialog.expected) == MAX_TRAINING_MIDI
    dialog.reject()


@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("score", [74,75,100])
@pytest.mark.parametrize("direction_up", [False,True])
def test_report_automatically_updates_pitch_control_only_at_threshold(qtbot, tmp_path, monkeypatch, custom, score, direction_up):
    from functools import partial
    from vocal_app.core.evaluation import evaluate
    from vocal_app.ui import training_dialog
    monkeypatch.setattr(training_dialog, "TrainingDialog", partial(TrainingDialog, auto_start=False))
    win = MainWindow(SettingsStore(tmp_path / "settings.json"))
    qtbot.addWidget(win)
    win.show()
    if custom:
        win.session_select.setCurrentIndex(win.session_select.findData("I"))
        path = tmp_path / "score.txt"
        path.write_text("B3 D4 G4 E4\n500 500 500 500")
        assert win.load_custom_file(path)
    else:
        win.show_exercise(13)
    win.transpose.setValue(10)
    win.direction.setCurrentIndex(0 if direction_up else 1)
    win.start_training()
    dialog = win.dialog
    # A controlled final score isolates the completion signal and threshold boundary.
    report = evaluate(dialog.expected, [])
    dialog.render_report(replace(report, global_score=replace(report.global_score, score=score)))
    expected = 10 + ((1 if direction_up else -1) if score >= 75 else 0)
    assert win.dialog is dialog  # Already applied while the report is still open.
    assert win.transpose.value() == expected
    assert win.store.training(win.exercise).transpose == expected
    assert SettingsStore(win.store.path).training(win.exercise).transpose == expected
    if score < 75:
        assert "tom mantido" in win.status.text()
    dialog.complete_button.click()
    assert win.dialog is None and win.transpose.value() == expected  # Never apply twice on close.
    win.close()


def test_unknown_score_and_incomplete_attempts_do_not_progress():
    ex = load_catalog().by_id[13]
    settings = TrainingSettings(transpose=10)
    assert settings.after_action("complete", True, ex).transpose == 10
    assert settings.after_action("complete", False, ex, score=100).transpose == 10
    assert settings.after_action("retry", True, ex, score=100).transpose == 10
    assert settings.after_action("close", True, ex, score=100).transpose == 10
