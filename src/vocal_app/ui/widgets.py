"""Qt widgets for local tablatures, demo audio and the live pitch plot."""
import math
from bisect import bisect_left
from pathlib import Path
import numpy as np
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QPixmap, QPainter
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider,
    QGraphicsView, QGraphicsScene, QSizePolicy,
)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import pyqtgraph as pg
from vocal_app.core.training import FixedTimeline


class TablatureView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("background: #eef1f4; border: 0; border-radius: 8px;")
        self.item = None

    def load(self, path: Path | None):
        self.scene().clear()
        self.item = None
        if path:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                self.scene().addText(f"Imagem indisponível: {path.name}")
            else:
                self.item = self.scene().addPixmap(pixmap)
                self.scene().setSceneRect(self.item.boundingRect())
        else:
            self.scene().addText("Exercício respiratório · acompanhe o cronômetro e o metrônomo.")
        self.fit()

    def fit(self):
        self.resetTransform()
        if self.item:
            self.fitInView(self.item, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
            self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)


class DemoPlayer(QWidget):
    playback_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.output = QAudioOutput(self)
        self.output.setVolume(.8)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.output)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.play = QPushButton("Tocar exemplo")
        self.play.setObjectName("demoPlay")
        self.play.clicked.connect(self.toggle)
        row.addWidget(self.play)
        stop = QPushButton("■")
        stop.setFixedWidth(34)
        stop.setToolTip("Parar exemplo")
        stop.clicked.connect(self.player.stop)
        row.addWidget(stop)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setToolTip("Posição do exemplo sonoro")
        self.seek.sliderMoved.connect(self.player.setPosition)
        row.addWidget(self.seek, 1)
        self.time = QLabel("00:00 / 00:00")
        row.addWidget(self.time)
        self.player.durationChanged.connect(lambda n: self.seek.setRange(0, n))
        self.player.positionChanged.connect(self.update_position)
        self.player.playbackStateChanged.connect(self.update_state)
        self.player.errorOccurred.connect(lambda *_: self.time.setText(self.player.errorString()))

    def load(self, path):
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(path)) if path else QUrl())
        self.setEnabled(bool(path))

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.playback_requested.emit()
            self.player.play()

    def update_state(self, state):
        self.play.setText("Pausar exemplo" if state == QMediaPlayer.PlaybackState.PlayingState else "Tocar exemplo")

    def update_position(self, position):
        if not self.seek.isSliderDown():
            self.seek.setValue(position)
        def clock(ms):
            return f"{ms // 60000:02d}:{ms // 1000 % 60:02d}"
        self.time.setText(f"{clock(position)} / {clock(self.player.duration())}")


class PitchPlot(pg.PlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent, background="#101925")
        self.setLabel("bottom", "Tempo", units="s")
        self.setLabel("left", "Altura", units="MIDI")
        self.showGrid(x=True, y=True, alpha=.18)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.setMouseEnabled(x=False, y=False)
        self.setMenuEnabled(False)
        self.hideButtons()
        self.disableAutoRange()
        self.target = self.plot(pen=pg.mkPen("#ff5267", width=3), connect="finite")
        self.voice = self.plot(pen=pg.mkPen("#70c9ff", width=2), connect="finite")
        self.cursor = pg.InfiniteLine(pen=pg.mkPen("#3ee18f", width=2))
        self.addItem(self.cursor)
        self.dot = self.plot([], [], pen=None, symbol="o", symbolSize=12, symbolBrush="#3ee18f")
        self.expected = []
        self.note_ms = 750
        self.lead_ms = 150
        self.timeline = FixedTimeline([], self.note_ms)
        self.report_voice_traces = []
        self.highlighted_index = -1
        self._live_y_range = None

    def configure(self, expected, note_ms, durations_ms=()):
        for item in self.report_voice_traces:
            self.removeItem(item)
        self.report_voice_traces.clear()
        self.highlighted_index = -1
        self.target.show()
        self.timeline = FixedTimeline(expected, note_ms, durations_ms=durations_ms)
        self.expected, self.note_ms, self.lead_ms = expected, note_ms, self.timeline.lead_ms
        x, y = [], []
        for note in self.timeline.windows():
            x.extend([note.start_t / 1000, note.end_t / 1000, math.nan])
            y.extend([note.midi, note.midi, math.nan])
        self.target.setData(x, y)
        if expected:
            self.setYRange(min(n.midi for n in expected) - 2, max(n.midi for n in expected) + 2)
            from vocal_app.core.notes import midi_to_note
            ticks = sorted(set(n.midi for n in expected))
            self.getAxis("left").setTicks([[(m, midi_to_note(m)) for m in ticks]])
        self.voice.setData([], [])
        self.dot.setData([], [])
        self._live_y_range = None
        self.fit_complete([], 0)

    def highlight_report(self, report, frames):
        """Highlight the recorded voice, aligned to evaluated segments, never the targets."""
        from vocal_app.core.evaluation import grade_tuning
        colors = {"grade-excellent": "#77cea0", "grade-good": "#77cea0",
                  "grade-attention": "#e0c36a", "grade-deviation": "#e4a16b",
                  "grade-problem": "#ff6679", "grade-uncertain": "#9aa7ba", "grade-missing": "#9aa7ba"}
        grades = [grade_tuning(row) for row in report.rows]
        # Use the evaluator's largest reliable tuning error, but never mark a good note red.
        worst = report.worst_index
        if worst < 0 or grades[worst].rank < 3:
            worst = -1
        self.highlighted_index = worst
        for item in self.report_voice_traces:
            self.removeItem(item)
        self.report_voice_traces.clear()
        times = [frame.t for frame in frames]
        for index, (row, grade) in enumerate(zip(report.rows, grades)):
            if row is None:
                continue  # No execution trace exists for a missing note.
            samples = frames[bisect_left(times, row.segment.start_t):bisect_left(times, row.segment.end_t)]
            if not samples:
                continue
            x, y, last = [], [], None
            for frame in samples:
                if last is not None and frame.t - last > 120:
                    x.append(math.nan)
                    y.append(math.nan)
                x.append(frame.t / 1000)
                y.append(frame.midi)
                last = frame.t
            highlighted = index == worst
            color = "#ff6679" if highlighted else colors[grade.class_name]
            pen = pg.mkPen(color, width=6 if highlighted else 4)
            item = self.plot(x, y, pen=pen, connect="finite")
            item.setToolTip(f"Voz · #{index + 1} · {row.expected.label} · {grade.label}" + (" · Maior desvio" if highlighted else ""))
            item.setZValue(2)
            self.report_voice_traces.append(item)

    def fit_complete(self, frames, now_ms, review=False):
        """Fit the entire score and every visible sample with explicit breathing room."""
        visible = [f for f in frames if (review or not f.hidden_during_live) and math.isfinite(f.midi)]
        heights = [n.midi for n in self.expected] + [f.midi for f in visible]
        low, high = (min(heights), max(heights)) if heights else (48, 72)
        if not review and self._live_y_range:
            low = min(low, self._live_y_range[0])
            high = max(high, self._live_y_range[1])
        if not review:
            self._live_y_range = (low, high)
        margin = max(1., (high - low) * .10)
        self.setYRange(low - margin, high + margin, padding=0)
        end = self.timeline.end_t / 1000
        times = [0., end, now_ms / 1000] + [f.t / 1000 for f in visible]
        start, end = min(times), max(times)
        margin = max(.15, (end - start) * .035)
        self.setXRange(start - margin, end + margin, padding=0)

    def update_frames(self, frames, now_ms, review=False):
        # A NaN breaks lines at silence and hidden ghost positions; no interpolation across gaps.
        x, y, last = [], [], None
        for frame in frames:
            if (frame.hidden_during_live and not review) or (last is not None and frame.t - last > 120):
                x.append(math.nan)
                y.append(math.nan)
            if review or not frame.hidden_during_live:
                x.append(frame.t / 1000)
                y.append(frame.midi)
            last = frame.t
        self.voice.setData(np.asarray(x), np.asarray(y))
        self.cursor.setVisible(not review)
        self.cursor.setValue(now_ms / 1000)
        index = self.timeline.target_index_at(now_ms)
        if not review and 0 <= index < len(self.expected):
            self.dot.setData([now_ms / 1000], [self.expected[index].midi])
        else:
            self.dot.setData([], [])
        self.fit_complete(frames, now_ms, review)
