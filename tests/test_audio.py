"""Audio infrastructure tests: deterministic, no real input/output device needed."""
from types import SimpleNamespace
import time

import numpy as np
import pytest

from vocal_app.audio.capture import CaptureEngine
from vocal_app.audio import playback


class Detector:
    def detect(self, pcm, t):
        return SimpleNamespace(t=t, hz=220, rms=float(np.sqrt(np.mean(pcm ** 2))))


def test_callback_copies_original_pcm_and_retains_even_when_analysis_queue_full():
    engine = CaptureEngine(Detector(), sample_rate=1000, window_size=8, queue_blocks=1)
    original = np.arange(20, dtype=np.float32).reshape(-1, 1)
    engine._callback(original[:10], 10, None, None)
    engine._callback(original[10:], 10, None, None)
    original[:] = -1
    segment = engine.segment(5, 16, "A3")
    np.testing.assert_array_equal(segment.pcm, np.arange(5, 16, dtype=np.float32))
    assert segment.label == "A3" and segment.sample_rate == 1000
    assert segment.dropped_analysis_blocks == 1
    assert not segment.pcm.flags.writeable


def test_worker_overlapping_windows_and_timestamps():
    engine = CaptureEngine(Detector(), sample_rate=1000, window_size=40, hop_ms=20)
    for i in range(4):
        engine._callback(np.full((20, 1), .1, dtype=np.float32), 20, None, None)
    engine._halt.set()
    engine._process()
    events = engine.drain_frames()
    assert [event.t for event in events] == [40, 60, 80]
    assert all(event.frame.hz == 220 for event in events)
    assert engine.drain_frames() == []


def test_detector_silence_emits_unvoiced_event():
    engine = CaptureEngine(SimpleNamespace(detect=lambda pcm, t: None), sample_rate=1000, window_size=20)
    engine._callback(np.zeros((20, 1), dtype=np.float32), 20, None, None)
    engine._halt.set()
    engine._process()
    assert engine.drain_frames()[0].frame is None


def test_missing_soundfont_has_actionable_diagnostic(tmp_path):
    with pytest.raises(playback.AudioUnavailable, match="SoundFont ausente"):
        playback._FluidSynth(tmp_path / "missing.sf2")


def test_metronome_distinct_accent_and_duration():
    normal = playback.metronome_pcm(False)
    accent = playback.metronome_pcm(True)
    assert len(normal) == 3120
    assert max(abs(accent)) > max(abs(normal))
    assert max(abs(normal[-100:])) < .001


def test_guide_uses_gm_programs_and_async_worker(monkeypatch):
    import sounddevice
    calls = []
    class Synth:
        def __init__(self, *args): calls.append("load")
        def select(self, instrument): calls.append(instrument)
        def note_on(self, midi, velocity): calls.append(("on", midi))
        def note_off(self, midi): calls.append(("off", midi))
        def stop(self): calls.append("stop")
        def render(self, count): return np.zeros((count, 2), dtype=np.float32)
        def close(self): calls.append("closed")
    class Stream:
        def __init__(self, **kwargs): pass
        def start(self): pass
        def write(self, output): time.sleep(.005)
        def abort(self): pass
        def close(self): pass
    monkeypatch.setattr(playback, "_FluidSynth", Synth)
    monkeypatch.setattr(sounddevice, "OutputStream", Stream)
    player = playback.GuidePlayer()
    try:
        assert player.prepare("mock.sf2", "acoustic_guitar_steel").result(timeout=2)
        player.note_on(60, duration=.01)
        deadline = time.monotonic() + 2
        while ("off", 60) not in calls and time.monotonic() < deadline:
            time.sleep(.01)
        assert ("on", 60) in calls and ("off", 60) in calls
        assert playback.INSTRUMENTS == {"acoustic_guitar_nylon": 24, "acoustic_guitar_steel": 25, "acoustic_grand_piano": 0}
    finally:
        player.close()
    assert "stop" in calls and "closed" in calls


def test_failed_prepare_completes_future_without_fake_instrument(tmp_path):
    player = playback.GuidePlayer()
    try:
        with pytest.raises(playback.AudioUnavailable, match="SoundFont ausente"):
            player.prepare(tmp_path / "missing.sf2").result(timeout=2)
        assert not player.ready
        assert "SoundFont ausente" in player.last_error
    finally:
        player.close()
