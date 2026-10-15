"""Monophonic McLeod/NSDF fundamental-frequency detector, no learned models.

McLeod & Wyvill, ICMC 2005, 'A smarter way to find pitch':
https://quod.lib.umich.edu/i/icmc/bbp2372.2005.107/1/

Replaces browser Pitchy with FFT autocorrelation, exact lag-dependent energy
normalization and parabolic peak interpolation. Clarity is normalized periodicity,
not a probability. Analysis is on 4096 sample PCM windows every 20 milliseconds.
"""
from __future__ import annotations

import math
import numpy as np
from numpy.typing import ArrayLike
from scipy.fft import irfft, next_fast_len, rfft
from scipy.signal import find_peaks

from ..core.notes import hz_to_midi
from ..core.tracking import DEFAULT_CONFIG, PitchFrame, TrackerConfig


class PitchDetector:
    def __init__(self, sample_rate: float = 48000, frame_size: int = 4096,
                 config: TrackerConfig = DEFAULT_CONFIG, relative_peak_threshold: float = .93):
        if sample_rate <= 0 or frame_size < 32:
            raise ValueError("Taxa de amostragem ou tamanho de janela inválido.")
        self.sample_rate = float(sample_rate)
        self.frame_size = frame_size
        self.config = config
        self.relative_peak_threshold = relative_peak_threshold
        self.last_clarity = 0.0
        self.last_rms = 0.0

    def find_pitch(self, pcm: ArrayLike, sample_rate: float | None = None) -> tuple[float | None, float]:
        sample_rate = self.sample_rate if sample_rate is None else float(sample_rate)
        signal = np.asarray(pcm, dtype=np.float64)
        self.last_clarity, self.last_rms = 0.0, 0.0
        if signal.ndim != 1:
            raise ValueError("O detector requer PCM mono unidimensional.")
        if len(signal) < 32 or not np.isfinite(signal).all() or sample_rate <= 0:
            return None, 0.0
        # Remove DC bias before measuring usable voice amplitude.
        signal = signal - signal.mean()
        self.last_rms = float(np.sqrt(np.mean(signal * signal)))
        if self.last_rms < self.config.min_rms:
            return None, 0.0
        size = len(signal)
        # Zero-padding avoids circular correlation of the end with the attack.
        fft_size = next_fast_len(2 * size - 1)
        spectrum = rfft(signal, n=fft_size)
        correlation = irfft(spectrum * spectrum.conjugate(), n=fft_size)[:size]
        energy = np.concatenate(([0.0], np.cumsum(signal * signal)))
        lags = np.arange(size)
        denominator = energy[size - lags] + energy[size] - energy[lags]
        nsdf = np.divide(2 * correlation, denominator, out=np.zeros_like(correlation), where=denominator > 1e-15)

        # Search beyond voice bounds, then reject the frequency: restricting peaks
        # to min/max Hz would mislabel high tones as subharmonics inside the range.
        max_lag = min(size // 2, math.ceil(sample_rate / self.config.min_hz) + 2)
        peaks, _ = find_peaks(nsdf[:max_lag + 1], height=0)
        # MPM chooses one maximum in each positive lobe after the initial lobe.
        crossings = np.flatnonzero(nsdf[:max_lag + 1] <= 0)
        if not len(crossings):
            return None, 0.0
        peaks = peaks[peaks > crossings[0]]
        if not len(peaks):
            return None, 0.0
        lobe_peaks: list[int] = []
        for peak in peaks:
            peak = int(peak)
            if lobe_peaks and np.all(nsdf[lobe_peaks[-1]:peak + 1] > 0):
                if nsdf[peak] > nsdf[lobe_peaks[-1]]:
                    lobe_peaks[-1] = peak
            else:
                lobe_peaks.append(peak)
        best = max(float(nsdf[p]) for p in lobe_peaks)
        cutoff = self.relative_peak_threshold * best
        selected = next(p for p in lobe_peaks if nsdf[p] >= cutoff)
        a, b, c = nsdf[selected - 1:selected + 2]
        curvature = a - 2 * b + c
        offset = .5 * (a - c) / curvature if abs(curvature) > 1e-15 else 0.0
        offset = float(np.clip(offset, -.5, .5))
        clarity = float(np.clip(b - .25 * (a - c) * offset, 0, 1))
        self.last_clarity = clarity
        frequency = sample_rate / (selected + offset)
        if clarity < self.config.min_clarity or not self.config.min_hz <= frequency <= self.config.max_hz:
            return None, clarity
        return float(frequency), clarity

    def detect(self, pcm: ArrayLike, t: float = 0) -> PitchFrame | None:
        frequency, clarity = self.find_pitch(pcm)
        if frequency is None:
            return None
        return PitchFrame(t, frequency, hz_to_midi(frequency), clarity, self.last_rms)
