"""Decode every original MP3 through Qt's actual local multimedia backend."""
import pytest
from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioDecoder
from vocal_app.core.catalog import load_catalog


@pytest.mark.parametrize("exercise_id", range(1, 40))
def test_all_mp3_decode(qtbot, exercise_id):
    catalog = load_catalog()
    decoder = QAudioDecoder()
    observed = {"frames": 0, "done": False, "error": ""}
    def read():
        buffer = decoder.read()
        assert buffer.isValid()
        observed["frames"] += buffer.frameCount()
    decoder.bufferReady.connect(read)
    decoder.finished.connect(lambda: observed.update(done=True))
    decoder.error.connect(lambda *_: observed.update(error=decoder.errorString()))
    decoder.setSource(QUrl.fromLocalFile(str(catalog.asset_path(catalog.by_id[exercise_id].audio))))
    decoder.start()
    qtbot.waitUntil(lambda: observed["done"] or bool(observed["error"]), timeout=20000)
    decoder.stop()
    assert not observed["error"]
    assert observed["frames"] > 1000
