"""Decode every amplified MP3 and check levels through the real Qt backend."""
import json
import numpy as np
import pytest
from scipy.signal import resample_poly
from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
from vocal_app.core.catalog import load_catalog


@pytest.mark.parametrize("exercise_id", range(1, 40))
def test_all_mp3_decode(qtbot, exercise_id):
    catalog = load_catalog()
    decoder = QAudioDecoder()
    fmt = QAudioFormat()
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
    fmt.setChannelCount(2)
    fmt.setSampleRate(48000)
    decoder.setAudioFormat(fmt)
    chunks = []
    observed = {"frames": 0, "done": False, "error": ""}
    def read():
        buffer = decoder.read()
        assert buffer.isValid()
        observed["frames"] += buffer.frameCount()
        chunks.append(np.frombuffer(buffer.constData(), dtype=np.float32, count=buffer.sampleCount()).copy().reshape(-1, 2))
    decoder.bufferReady.connect(read)
    decoder.finished.connect(lambda: observed.update(done=True))
    decoder.error.connect(lambda *_: observed.update(error=decoder.errorString()))
    decoder.setSource(QUrl.fromLocalFile(str(catalog.asset_path(catalog.by_id[exercise_id].audio))))
    decoder.start()
    qtbot.waitUntil(lambda: observed["done"] or bool(observed["error"]), timeout=20000)
    decoder.stop()
    assert not observed["error"]
    assert observed["frames"] > 1000
    pcm = np.concatenate(chunks)
    assert np.isfinite(pcm).all()
    assert float(np.abs(pcm).max()) < 1
    assert float(np.abs(resample_poly(pcm, 4, 1, axis=0)).max()) <= 10 ** (-1 / 20)
    manifest = json.loads((catalog.assets_dir / "manifest.json").read_text(encoding="utf-8"))
    entry = next(r for r in manifest["resources"] if r["exercise_id"] == exercise_id and r["kind"] == "audio")
    before = entry["amplification"]["before"]
    assert observed["frames"] == before["frames_48000"]
    rms = float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2)))
    assert rms / before["rms"] == pytest.approx(3., rel=.03)
