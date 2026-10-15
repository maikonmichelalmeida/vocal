"""Run this file from Spyder (F5) to launch Vocal in its own Python/Qt process."""
from pathlib import Path
import os
import subprocess


def launch():
    root = Path(__file__).resolve().parent
    python = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.is_file():
        raise RuntimeError("Ambiente ausente. Execute scripts/install.ps1 primeiro.")
    environment = os.environ.copy()
    # Spyder may export its own Qt plugin paths. The child must use its PySide6.
    for name in ("QT_API", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH", "PYTHONPATH", "PYTHONHOME"):
        environment.pop(name, None)
    environment["PYQTGRAPH_QT_LIB"] = "PySide6"
    process = subprocess.Popen([str(python), "-m", "vocal_app"], cwd=root, env=environment,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    print(f"Vocal Trainer aberto em processo separado (PID {process.pid}).")
    return process


if __name__ == "__main__":
    vocal_process = launch()
