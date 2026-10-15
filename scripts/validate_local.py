"""Opt-in hardware smoke check; transient microphone PCM is never written to disk.

Run: .venv/Scripts/python scripts/validate_local.py
Plays a short MP3 and a sampled guide, then captures a brief timed attempt.
"""
import json
from pathlib import Path
import sys
import time
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
from vocal_app.core.catalog import load_catalog
from vocal_app.core.settings import SettingsStore, TrainingSettings
from vocal_app.ui.main_window import MainWindow
from vocal_app.ui.training_dialog import TrainingDialog


def main():
    app = QApplication(sys.argv[:1])
    root = Path(__file__).resolve().parents[1]
    output = root / "test-results"
    output.mkdir(exist_ok=True)
    window = MainWindow(store=SettingsStore(output / "hardware-settings.json"))
    window.show_exercise(4)
    window.show()
    evidence = {"mp3_position_ms": 0, "mp3_error": "", "completed": False}
    started = time.perf_counter()
    stage = "mp3"
    trainer = None
    window.demo.player.play()
    timer = QTimer()

    def tick():
        nonlocal stage, trainer, started
        elapsed = time.perf_counter() - started
        if elapsed > 25:
            evidence["error"] = "Timeout de validação local"
            finish()
        elif stage == "mp3" and elapsed > 2:
            evidence["mp3_position_ms"] = window.demo.player.position()
            evidence["mp3_error"] = window.demo.player.errorString()
            window.grab().save(str(output / "main-window.png"))
            window.demo.player.stop()
            trainer = TrainingDialog(load_catalog().by_id[4], TrainingSettings(bpm=120),
                                     "acoustic_guitar_nylon", parent=window)
            trainer.open()
            stage = "training"
        elif stage == "training" and trainer.state in ("DONE", "ERROR", "AUDIO_ERROR"):
            evidence["state"] = trainer.state
            evidence["status"] = trainer.status.text()
            evidence["completed"] = trainer.state == "DONE"
            if trainer.capture:
                evidence["samples"] = sum(len(c.pcm) for c in trainer.capture.chunks)
                evidence["events_with_pitch"] = len(trainer.frames)
                evidence["dropped_blocks"] = trainer.capture.dropped_analysis_blocks
                evidence["capture_error"] = trainer.capture.last_error
            if trainer.report:
                evidence["score"] = trainer.report.global_score.score
                evidence["evaluated_positions"] = len(trainer.report.rows)
            trainer.grab().save(str(output / "training-report.png"))
            finish()

    def finish():
        timer.stop()
        (output / "hardware-check.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(evidence, ensure_ascii=False))
        if trainer:
            trainer.reject()
        window.close()
        app.quit()

    timer.timeout.connect(tick)
    timer.start(50)
    app.exec()
    return 0 if evidence["completed"] and evidence["mp3_position_ms"] > 0 and not evidence["mp3_error"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
