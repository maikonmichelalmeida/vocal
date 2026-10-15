"""Amplify the catalog MP3 once, validating decoded output before replacing files.

Maintenance only: pass --ffmpeg or install imageio-ffmpeg in the project venv.
The application does not depend on this tool. Originals remain in Git history.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile

import numpy as np
from scipy.signal import resample_poly


def run(ffmpeg, *args):
    return subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", *map(str, args)],
                          check=True, capture_output=True).stdout


def measure(ffmpeg, path):
    raw = run(ffmpeg, "-i", path, "-map", "0:a:0", "-f", "f32le", "-acodec", "pcm_f32le", "-ac", 2, "-ar", 48000, "-")
    pcm = np.frombuffer(raw, dtype="<f4").reshape(-1, 2)
    if not len(pcm) or not np.isfinite(pcm).all():
        raise ValueError(f"Invalid audio: {path}")
    return {"frames_48000": len(pcm), "sample_peak": float(np.abs(pcm).max()),
            "estimated_true_peak_4x": float(np.abs(resample_poly(pcm, 4, 1, axis=0)).max()),
            "rms": float(np.sqrt(np.mean(pcm.astype(np.float64) ** 2)))}


def amplify(assets, ffmpeg):
    assets = Path(assets).resolve()
    manifest_path = assets / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audio = [entry for entry in manifest["resources"] if entry["kind"] == "audio"]
    if any("amplification" in entry for entry in audio):
        raise ValueError("Examples already amplified; refusing to apply gain twice. Restore originals before rebuilding.")
    ceiling = 10 ** (-1 / 20)
    with tempfile.TemporaryDirectory(prefix="vocal-audio-") as temporary:
        staged = []
        for entry in audio:
            source = (assets / entry["path"]).resolve()
            if not source.is_relative_to(assets):
                raise ValueError("Audio path outside assets")
            if hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError(f"Source hash mismatch: {source}")
            before = measure(ffmpeg, source)
            peak = max(before["sample_peak"], before["estimated_true_peak_4x"])
            gain = min(3., ceiling / peak) if peak else 3.
            output = Path(temporary) / f"{entry['exercise_id']}.mp3"
            for _ in range(3):
                run(ffmpeg, "-y", "-i", source, "-map", "0:a:0", "-map_metadata", "0",
                    "-af", f"volume={gain:.12g}", "-c:a", "libmp3lame", "-b:a", "320k", output)
                after = measure(ffmpeg, output)
                encoded_peak = max(after["sample_peak"], after["estimated_true_peak_4x"])
                if encoded_peak <= ceiling:
                    break
                # Encoding may change peaks. Re-encode from the original at lower gain.
                gain *= ceiling / encoded_peak * .99
            else:
                raise ValueError(f"Could not keep peaks below -1 dBFS: {source}")
            if abs(after["frames_48000"] - before["frames_48000"]) > 1:
                raise ValueError(f"Audio duration changed: {source}")
            entry["amplification"] = {
                "original_sha256": entry["sha256"], "original_bytes": entry["bytes"],
                "gain": gain, "gain_db": 20 * math.log10(gain), "ceiling_dbfs": -1,
                "encoder": "libmp3lame 320 kbit/s", "before": before, "after": after,
            }
            entry["bytes"] = output.stat().st_size
            entry["sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
            staged.append((output, source))
            print(f"{entry['exercise_id']:02d}: {gain:.3f}x; peak {20 * math.log10(encoded_peak):.2f} dBFS")
        # Decode and validate every output before modifying any project resource.
        for output, source in staged:
            shutil.copyfile(output, source)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, default=Path(__file__).resolve().parents[1] / "assets")
    parser.add_argument("--ffmpeg", default=shutil.which("ffmpeg"))
    args = parser.parse_args()
    if args.ffmpeg is None:
        import imageio_ffmpeg
        args.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    amplify(args.assets, args.ffmpeg)
