"""Predictable ghost positions, independent of pitch or exercise spelling."""
import pytest
from vocal_app.core.guide import GUIDE_LEVELS, guide_mask, apply_guide_level
from vocal_app.core.settings import SettingsStore, TrainingSettings
from vocal_app.core.catalog import load_catalog


@pytest.mark.parametrize("level,positions", [
    ("integral", list(range(9))), ("final", [0,1,2,3,4,5]),
    ("meio", [0,1,2,5,6,7,8]), ("guias", [0,3,6]), ("total", [0]),
])
def test_nine_note_pattern(level, positions):
    assert [i for i, value in enumerate(guide_mask(9, level)) if value] == positions


@pytest.mark.parametrize("length", [0,1,2,3,5,8,9,21,41])
def test_short_and_long_patterns_keep_first_and_preserve_length(length):
    for level, _, _ in GUIDE_LEVELS:
        mask = guide_mask(length, level)
        assert len(mask) == length
        if length:
            assert mask[0]
    assert sum(guide_mask(length, "guias")) <= (3 if length >= 9 else 2)
    assert sum(not b for b in guide_mask(length, "meio")) <= 3


def test_masks_use_positions_and_preserve_existing_silences():
    notes = ["A3", "A3", None, "A3", "A3"]
    assert apply_guide_level(notes, "final") == ["A3", "A3", None, None, None]
    assert notes == ["A3", "A3", None, "A3", "A3"]
    assert apply_guide_level(notes) == notes


def test_settings_migration_persistence_and_progression(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"training":{"13":{"transpose":2,"bpm":76}}}', encoding="utf-8")
    store = SettingsStore(path)
    exercise = load_catalog().by_id[13]
    assert store.training(exercise).guide_level == "integral"
    settings = TrainingSettings(transpose=2, guide_level="total")
    store.set_training(exercise.id, settings)
    assert SettingsStore(path).training(exercise).guide_level == "total"
    assert settings.after_action("complete", True).guide_level == "total"
    assert TrainingSettings(guide_level="obsolete").guide_level == "integral"
