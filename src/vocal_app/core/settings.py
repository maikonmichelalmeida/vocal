"""Small atomic JSON preference store, independent of Qt and the source checkout."""
from dataclasses import asdict, dataclass, replace
import json
import os
from pathlib import Path


@dataclass
class TrainingSettings:
    transpose: int = 0
    direction_up: bool = True
    guided: bool = True
    bpm: int = 80
    subdivision: int = 1
    guide_level: str = "integral"

    def __post_init__(self):
        self.transpose = int(self.transpose)
        self.bpm = max(40, min(180, int(self.bpm)))
        self.subdivision = max(1, min(4, int(self.subdivision)))
        from .guide import GUIDE_LEVELS
        if self.guide_level not in {item[0] for item in GUIDE_LEVELS}:
            self.guide_level = "integral"

    @property
    def note_duration_ms(self) -> int:
        return int(60000 / (self.bpm * self.subdivision) + .5)

    def custom_durations_ms(self, exercise) -> tuple[float, ...]:
        """TXT durations are written at 120 BPM; never mutate the source score."""
        if exercise.rhythm:
            return tuple(weight * self.note_duration_ms for weight in exercise.rhythm)
        return tuple(duration * 120 / self.bpm for duration in exercise.durations_ms)

    def for_exercise(self, exercise) -> "TrainingSettings":
        from .transposition import clamp_transpose
        return replace(self, transpose=clamp_transpose(exercise, self.transpose))

    def after_action(self, action: str, finished: bool, exercise=None, *, score: float = 0) -> "TrainingSettings":
        from .training import progressed_transpose
        transpose = progressed_transpose(self.transpose, "up" if self.direction_up else "down", action, finished, exercise, score=score)
        return replace(self, transpose=transpose)


class SettingsStore:
    def __init__(self, path: Path | None = None):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".config"))
        self.path = path or base / "VocalTrainer" / "settings.json"
        self.data = {}
        self.error = ""
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.data = raw
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            self.error = f"Não foi possível ler as preferências: {exc}"

    def training(self, exercise) -> TrainingSettings:
        saved = self.data.get("training", {}).get(str(exercise.id), {})
        fields = {k: v for k, v in saved.items() if k in TrainingSettings.__dataclass_fields__}
        try:
            return TrainingSettings(**({"bpm": exercise.bpm, "subdivision": exercise.subdivision} | fields)).for_exercise(exercise)
        except (TypeError, ValueError):
            return TrainingSettings(bpm=exercise.bpm, subdivision=exercise.subdivision).for_exercise(exercise)

    def set_training(self, exercise_id: int, settings: TrainingSettings):
        self.data.setdefault("training", {})[str(exercise_id)] = asdict(settings)
        self.save()

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
            self.error = ""
        except OSError as exc:
            self.error = f"Não foi possível salvar as preferências: {exc}"
