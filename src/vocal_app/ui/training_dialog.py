"""Nonblocking count-in, capture, fixed guide clock, graph and final report."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import math
import time
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QProgressBar, QWidget, QGridLayout,
    QStackedWidget, QSizePolicy,
)
from vocal_app.audio.capture import CaptureEngine
from vocal_app.audio.playback import GuidePlayer
from vocal_app.core.notes import parse_score, nearest_note
from vocal_app.core.tracking import SegmentTracker
from vocal_app.core.training import FixedTimeline
from vocal_app.core.guide import GUIDE_LEVELS, apply_guide_level
from vocal_app.core.evaluation import evaluate
from vocal_app.ui.widgets import PitchPlot, WindowSpaceShortcut


# Muted fills retain readable text; labels communicate the grade without color.
GRADE_COLORS = {
    "grade-excellent": ("#244d40", "#d9f4e7"),
    "grade-good": ("#253e39", "#d8e9e2"),
    "grade-attention": ("#514a2b", "#fff1bd"),
    "grade-deviation": ("#553c2c", "#ffe0c1"),
    "grade-problem": ("#542f38", "#ffdae0"),
    "grade-uncertain": ("#3c4050", "#e0e4f1"),
    "grade-missing": ("#343c48", "#d1d9e4"),
}


class TrainingDialog(QDialog):
    completed = Signal(int)
    attempt_finished = Signal(int)

    def __init__(self, exercise, settings, instrument, soundfont=None, parent=None,
                 capture_factory=CaptureEngine, guide_factory=GuidePlayer, auto_start=True):
        super().__init__(parent)
        settings = settings.for_exercise(exercise)
        self.exercise, self.settings = exercise, settings
        self.instrument, self.soundfont = instrument, soundfont
        self.capture_factory, self.guide_factory = capture_factory, guide_factory
        self.capture = None
        self.guide = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vocal-session")
        self.future = None
        self.state = "WAITING"
        self.audio_warning = ""
        self.allow_unaccompanied = False
        self.frames = []
        self.report = None
        self.now_ms = 0
        self.last_guide_index = -1
        self.last_beat = -1
        self.configure_score(settings)
        self.next_settings = settings
        self._progression_published = False
        self.setWindowTitle(exercise.name + " · Treino assistido")
        self.resize(1180, 850)
        self.setMinimumSize(760, 460)
        self.setModal(True)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(6)
        self.header = QWidget()
        header = QGridLayout(self.header)
        header.setContentsMargins(0, 0, 0, 0)
        header.setHorizontalSpacing(16)
        header.setVerticalSpacing(4)
        title = QLabel(exercise.name)
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        title.setToolTip(exercise.objective)
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(title, 0, 0)
        configuration = self.configuration = QLabel(self.configuration_text())
        configuration.setStyleSheet("color: #a9bdd3; font-size: 11px;")
        configuration.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        configuration.setToolTip("Sequência: " + "  ".join(n.label for n in self.expected))
        header.addWidget(configuration, 0, 1)
        self.cue = QLabel("Preparando…")
        self.cue.setStyleSheet("font-size: 18px; font-weight: 700; color: #86efb9;")
        self.cue.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        header.addWidget(self.cue, 1, 0)
        self.live = QLabel("Nota —   |   Hz —   |   cents —")
        self.live.setStyleSheet("font-size: 12px; color: #a9d9ff;")
        self.live.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.live, 1, 1)
        header.setColumnStretch(0, 1)
        header.setColumnStretch(1, 1)
        outer.addWidget(self.header)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet("font-size: 11px; color: #b6c6d8;")
        outer.addWidget(self.status)
        self.summary = QLabel()
        self.summary.setStyleSheet("font-size: 12px; color: #9ed4ff;")
        self.summary.hide()
        outer.addWidget(self.summary)
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        self.live_page = QWidget()
        self.live_layout = QVBoxLayout(self.live_page)
        self.live_layout.setContentsMargins(0, 0, 0, 0)
        self.plot = PitchPlot()
        self.plot.configure(self.positions, settings.note_duration_ms, self.durations_ms)
        self.live_layout.addWidget(self.plot, 1)
        self.pages.addWidget(self.live_page)
        self.report_page = QWidget()
        report_layout = QHBoxLayout(self.report_page)
        report_layout.setContentsMargins(0, 0, 0, 0)
        report_layout.setSpacing(10)
        self.preview_panel = QWidget()
        self.preview_layout = QVBoxLayout(self.preview_panel)
        self.preview_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_layout.addStretch()
        self.preview_panel.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        report_layout.addWidget(self.preview_panel, 3)
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(["#", "Alvo", "Voz", "Tempo\n(s)", "Viés\n(c)", "MAE\n(c)", "P90\n(c)", "Desvio\n(c)", "Troca\n(ms)", "Conf.", "Afinação"])
        self.table.setToolTip("MAE: erro absoluto médio. Desvio: oscilação da nota. Passe o mouse sobre uma célula para detalhes.")
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(False)
        self.table.setStyleSheet("QTableWidget { font-size: 11px; } QHeaderView::section { font-size: 11px; padding: 3px 1px; }")
        self.table.horizontalHeader().setMinimumSectionSize(20)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().resizeSection(0, 26)
        self.table.horizontalHeader().setSectionResizeMode(10, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().resizeSection(10, 76)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding)
        self.table.setMinimumSize(0, 0)
        report_layout.addWidget(self.table, 8)
        self.pages.addWidget(self.report_page)
        footer = QHBoxLayout()
        self.legend = QLabel("● Alvo   ● Voz   ● Posição")
        self.legend.setText('<span style="color:#ff5267">● Alvo</span> &nbsp; <span style="color:#70c9ff">● Voz</span> &nbsp; <span style="color:#3ee18f">● Posição</span>')
        self.live_legend = self.legend.text()
        self.legend.setStyleSheet("font-size: 11px;")
        footer.addWidget(self.legend)
        footer.addStretch()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedSize(110, 6)
        footer.addWidget(self.progress)
        outer.addLayout(footer)
        actions = QHBoxLayout()
        self.retry_button = QPushButton("Repetir tom")
        self.retry_button.clicked.connect(self.retry)
        self.complete_button = QPushButton("Concluir")
        self.complete_button.clicked.connect(self.complete)
        self.next_button = QPushButton("Próxima · Espaço")
        self.next_button.setObjectName("primary")
        self.next_button.clicked.connect(self.next_attempt)
        self.next_button.setEnabled(False)
        self.space_shortcut = WindowSpaceShortcut(self, self.on_space)
        self.close_button = QPushButton("Cancelar / fechar")
        self.close_button.clicked.connect(self.reject)
        self.unaccompanied_button = QPushButton("Treinar sem referência instrumental")
        self.unaccompanied_button.clicked.connect(self.continue_unaccompanied)
        self.unaccompanied_button.hide()
        actions.addWidget(self.unaccompanied_button)
        actions.addStretch()
        for button in (self.retry_button, self.next_button, self.complete_button, self.close_button):
            actions.addWidget(button)
        outer.addLayout(actions)
        self.retry_button.setEnabled(False)
        self.complete_button.setEnabled(False)
        breathing = exercise.mode == "breathing"
        for widget in (self.live, self.plot, self.legend):
            widget.setVisible(not breathing)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.tick)
        if auto_start:
            QTimer.singleShot(0, self.prepare)
        available = self.screen().availableGeometry()
        self.resize(min(1180, available.width() - 40), min(850, available.height() - 50))

    def configure_score(self, settings):
        self.settings = settings = settings.for_exercise(self.exercise)
        exercise = self.exercise
        self.positions = parse_score(exercise.vocal_notes, settings.transpose) if exercise.mode == "pitch" else []
        self.expected = [note for note in self.positions if note is not None]
        guide_notes = parse_score(exercise.guide_notes, settings.transpose)
        rests = [i for i, note in enumerate(self.positions) if note is None]
        self.guide_pattern = apply_guide_level(guide_notes, settings.guide_level, rests)
        self.initial_reference = next((note for note in self.guide_pattern if note is not None), None)
        self.durations_ms = settings.custom_durations_ms(exercise)
        self.timeline = FixedTimeline(self.positions, settings.note_duration_ms, self.guide_pattern, settings.guided, self.durations_ms)
        self.tracker = SegmentTracker(self.expected, settings.note_duration_ms, durations_ms=self.timeline.note_durations_ms)
        self.last_event_t = -1

    def configuration_text(self):
        settings = self.settings
        level = next(label for key, label, _ in GUIDE_LEVELS if key == settings.guide_level)
        mode = level if self.exercise.mode == "pitch" else "Respiração"
        tempo = f"{settings.bpm} bpm · TXT base 120" if self.exercise.durations_ms else f"{settings.bpm} bpm | {settings.subdivision}/pulso"
        return f"{tempo} | {settings.transpose:+d} st | {mode}"

    def prepare(self):
        if self.state == "CLOSED":
            return
        self.state = "PREPARING"
        self._progression_published = False
        self.next_button.setEnabled(False)
        self.configuration.setText(self.configuration_text())
        self.configuration.setToolTip("Sequência: " + "  ".join(n.label for n in self.expected))
        self.report = None
        self.frames = []
        self.now_ms = 0
        self.tracker = SegmentTracker(self.expected, self.settings.note_duration_ms, durations_ms=self.timeline.note_durations_ms)
        self.last_event_t = -1
        self.legend.setText(self.live_legend)
        self.summary.clear()
        self.summary.hide()
        self.live.setVisible(self.exercise.mode == "pitch")
        self.live_layout.addWidget(self.plot, 1)
        self.plot.setMaximumHeight(16777215)
        self.pages.setCurrentWidget(self.live_page)
        self.progress.setValue(0)
        self.retry_button.setEnabled(False)
        self.complete_button.setEnabled(False)
        self.unaccompanied_button.hide()
        self.guide = self.guide_factory()
        self.last_guide_index = self.last_beat = -1
        if self.exercise.mode == "breathing" or self.allow_unaccompanied:
            self.begin_countdown()
        else:
            self.future = self.guide.prepare(self.soundfont, self.instrument)
            self.cue.setText("Preparando instrumento…")
        self.timer.start()

    def continue_unaccompanied(self):
        self.allow_unaccompanied = True
        self.unaccompanied_button.hide()
        self.begin_countdown()

    def begin_countdown(self):
        self.state = "COUNTDOWN"
        self.phase_started = time.perf_counter()
        self.last_count = -1
        self.reference_delay = .47 if self.expected and self.settings.guided and not self.allow_unaccompanied else 0
        if self.reference_delay and self.initial_reference:
            self.guide.note_on(self.initial_reference.midi, 127, duration=2.12)
        self.cue.setText("Referência inicial" if self.reference_delay else "Prepare a entrada")
        self.status.setText("")

    def tick(self):
        if self.state == "PREPARING":
            if self.future and self.future.done():
                try:
                    self.future.result()
                except Exception as exc:
                    self.state = "AUDIO_ERROR"
                    self.audio_warning = str(exc)
                    self.cue.setText("Referência instrumental indisponível")
                    self.status.setText(self.audio_warning)
                    self.unaccompanied_button.show()
                else:
                    self.begin_countdown()
                self.future = None
        elif self.state == "COUNTDOWN":
            elapsed = time.perf_counter() - self.phase_started - self.reference_delay
            count = int(elapsed / .3)
            if elapsed >= 1.2:
                self.guide.stop()
                if self.expected and not self.settings.guided and not self.allow_unaccompanied and self.initial_reference:
                    self.guide.note_on(self.initial_reference.midi, 127, duration=.42)
                    self.state = "INITIAL_REFERENCE"
                    self.phase_started = time.perf_counter()
                    self.cue.setText("Nota inicial · " + self.expected[0].label)
                else:
                    self.begin_listening()
            elif elapsed >= 0 and count != self.last_count:
                self.last_count = count
                self.guide.click(accent=count == 0)
                self.cue.setText(f"{4 - count}  ·  prepare-se")
        elif self.state == "INITIAL_REFERENCE":
            if time.perf_counter() - self.phase_started >= .51:
                self.begin_listening()
        elif self.state == "OPENING_MIC":
            if self.future.done():
                try:
                    self.future.result()
                except Exception as exc:
                    self.fail(str(exc))
                else:
                    self.state = "LISTENING"
                    self.status.setText("" if self.settings.guided else "Somente referência inicial")
                self.future = None
        elif self.state == "LISTENING":
            self.tick_listening()
        elif self.state == "BREATHING":
            elapsed = (time.perf_counter() - self.phase_started) * 1000
            duration = self.exercise.breathing_seconds * 1000
            remaining = max(0, math.ceil((duration - elapsed) / 1000))
            self.cue.setText(f"Respiração · {remaining // 60:02d}:{remaining % 60:02d}")
            self.progress.setValue(min(1000, round(elapsed / duration * 1000)))
            beat = int(elapsed / (60000 / self.settings.bpm))
            if self.settings.guided and beat != self.last_beat:
                self.guide.click(accent=beat % 4 == 0)
                self.last_beat = beat
            if elapsed >= duration:
                self.finish_breathing()
        elif self.state == "EVALUATING" and self.future.done():
            try:
                self.future.result()
                self.consume_events()
                self.render_report(evaluate(self.expected, self.tracker.finish()))
            except Exception as exc:
                self.fail(f"Falha na avaliação: {exc}")
            self.future = None
        if self.guide and self.guide.last_error and self.state in ("BREATHING", "LISTENING"):
            self.status.setText("Áudio: " + self.guide.last_error)

    def begin_listening(self):
        if self.exercise.mode == "breathing":
            self.state = "BREATHING"
            self.phase_started = time.perf_counter()
            self.status.setText("Metrônomo" if self.settings.guided else "Sem metrônomo contínuo")
        else:
            self.state = "OPENING_MIC"
            self.cue.setText("Abrindo microfone…")
            self.capture = self.capture_factory()
            self.future = self.executor.submit(self.capture.start)

    def consume_events(self):
        for event in self.capture.drain_frames():
            for rest_start in self.timeline.rests_between(self.last_event_t, event.t):
                self.tracker.deliberate_rest(rest_start)
            self.last_event_t = event.t
            index = self.timeline.target_index_at(event.t)
            if index < 0:
                continue
            frame = event.frame
            if frame is None:
                self.tracker.no_pitch(event.t)
                self.live.setText("Sem pitch" if not self.timeline.hidden_during_live(event.t) else "Fantasma · correção oculta")
                self.live.setToolTip(f"RMS {event.rms:.4f} · {self.tracker.state}")
            else:
                frame = replace(frame, hidden_during_live=self.timeline.hidden_during_live(event.t))
                self.tracker.ingest(frame)
                self.frames.append(frame)
                nearest = nearest_note(frame.midi)
                if frame.hidden_during_live:
                    self.live.setText("Fantasma · correção oculta")
                    self.live.setToolTip("")
                else:
                    self.live.setText(f"{nearest.name}  |  {frame.hz:.1f} Hz  |  {nearest.cents:+.1f} c  |  {frame.clarity:.0%}")
                    self.live.setToolTip(f"Clareza {frame.clarity:.2f} · {self.tracker.state}")

    def tick_listening(self):
        self.now_ms = self.capture.elapsed_ms
        self.consume_events()
        if self.capture.last_error:
            self.fail(self.capture.last_error)
            return
        index = self.timeline.target_index_at(self.now_ms)
        guide_index = self.timeline.guide_index_at(self.now_ms)
        if guide_index >= 0 and guide_index != self.last_guide_index:
            self.last_guide_index = guide_index
            self.guide.stop()
            reference = self.guide_pattern[guide_index]
            if self.settings.guided and not self.allow_unaccompanied and reference:
                self.guide.note_on(reference.midi, 127, duration=self.timeline.durations_ms[guide_index] / 1000 * 1.08)
        if index >= 0:
            next_label = self.expected[index + 1].label if index + 1 < len(self.expected) else "fim"
            ghost = " · fantasma" if self.guide_pattern[self.timeline.note_positions[index]] is None else ""
            self.cue.setText(f"{index + 1}/{len(self.expected)} · {self.expected[index].label}{ghost}   →   {next_label}")
        elif self.timeline.is_rest(self.now_ms):
            self.cue.setText("Pausa")
            self.live.setText("Pausa · aguarde a próxima nota")
        else:
            self.cue.setText("Entre na primeira nota…")
        self.progress.setValue(min(1000, round(self.now_ms / self.timeline.end_t * 1000)))
        self.plot.update_frames(self.frames, self.now_ms)
        if self.now_ms >= self.timeline.end_t:
            self.state = "EVALUATING"
            self.guide.stop()
            self.cue.setText("Calculando avaliação…")
            self.future = self.executor.submit(self.capture.stop)

    def fail(self, message):
        self.state = "ERROR"
        self.status.setText(message)
        self.cue.setText("Não foi possível iniciar ou concluir o treino")
        self.retry_button.setEnabled(True)
        if self.guide:
            self.guide.stop()
        if self.capture:
            self.executor.submit(self.capture.stop)

    def finish_breathing(self):
        self.timer.stop()
        self.guide.stop()
        self.state = "DONE"
        self.progress.setValue(1000)
        self.cue.setText("Treino respiratório concluído")
        self.summary.setText(f"{self.exercise.breathing_seconds} segundos concluídos")
        self.summary.show()
        self.status.setText("")
        self.retry_button.setEnabled(True)
        self.complete_button.setEnabled(True)
        self.publish_progression(0)

    def render_report(self, report):
        self.timer.stop()
        self.report = report
        self.state = "DONE"
        score = report.global_score
        self.cue.setText(f"{score.score}/100 · {score.label}")
        self.summary.setText(f"Notas confiáveis: {score.reliable_count}/{score.total_count}   ·   Extras: {len(report.alignment.extras)}")
        self.summary.show()
        self.live.hide()
        self.status.setText("")
        if self.allow_unaccompanied:
            self.status.setText("Sem referência instrumental")
        if self.capture and self.capture.dropped_analysis_blocks:
            self.status.setText(self.status.text() + f" Atenção: {self.capture.dropped_analysis_blocks} blocos de análise perdidos.")
        self.table.setRowCount(len(self.expected))
        for i, result in enumerate(report.rows):
            background, foreground = GRADE_COLORS[result.tuning.class_name if result else "grade-missing"]
            if result is None:
                values = [str(i + 1), self.expected[i].label, "—", "—", "—", "—", "—", "—", "—", "Baixa", "Ausente"]
                details = "Nota não identificada"
            else:
                segment = result.segment
                transition = segment.transition_from_previous
                tuning = {"grade-uncertain": "Incerta", "grade-deviation": "Desvio", "grade-problem": "Erro"}.get(result.tuning.class_name, result.tuning.label)
                values = [str(i + 1), result.expected.label, nearest_note(segment.center_midi).name,
                          f"{segment.duration_ms / 1000:.2f}", f"{result.bias:+.1f}", f"{result.mae:.1f}", f"{result.p90:.1f}",
                          f"{result.sigma:.1f}", f"{transition.duration_ms:.0f}" if transition else "—", result.confidence.label, tuning]
                details = f"{result.tuning.label} · {result.stability.label} (desvio {result.sigma:.1f} cents) · confiança {result.confidence.label}"
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(details)
                item.setBackground(QColor(background))
                item.setForeground(QColor(foreground))
                self.table.setItem(i, column, item)
        self.preview_layout.insertWidget(0, self.plot)
        self.plot.setMaximumHeight(240)
        self.pages.setCurrentWidget(self.report_page)
        self.plot.update_frames(self.frames, self.timeline.end_t, review=True)
        self.plot.highlight_report(report, self.frames)
        self.legend.setText('Voz: <span style="color:#77cea0">● Boa/excelente</span> &nbsp; <span style="color:#e0c36a">● Atenção</span> &nbsp; <span style="color:#e4a16b">● Desvio</span> &nbsp; <span style="color:#ff6679">● Pior/erro</span> &nbsp; | &nbsp; Barras: alvo')
        self.progress.setValue(1000)
        self.retry_button.setEnabled(True)
        self.complete_button.setEnabled(True)
        self.publish_progression(score.score)

    def publish_progression(self, score):
        if self._progression_published:
            return
        self._progression_published = True
        self.next_settings = self.settings.after_action("complete", True, self.exercise, score=score)
        changed = self.next_settings.transpose != self.settings.transpose
        self.next_button.setText("Próxima · Espaço" if changed else "Repetir · Espaço")
        self.next_button.setEnabled(True)
        if self.exercise.mode == "pitch":
            self.summary.setText(self.summary.text() + f" · Próximo tom: {self.next_settings.transpose:+d} st")
        self.attempt_finished.emit(score)

    def next_attempt(self):
        if self.state != "DONE":
            return
        self.configure_score(self.next_settings)
        self.retry()

    def on_space(self):
        if self.state == "DONE":
            self.next_attempt()
        elif self.state == "ERROR":
            self.retry()

    def retry(self):
        if self.state not in ("DONE", "ERROR"):
            return
        if self.capture:
            self.capture.stop()
            self.capture = None
        if self.guide:
            self.guide.close()
            self.guide = None
        self.plot.configure(self.positions, self.settings.note_duration_ms, self.durations_ms)
        self.prepare()

    def complete(self):
        if self.state != "DONE":
            return
        self.state = "COMPLETED"
        self.completed.emit(self.report.global_score.score if self.report else 0)
        self.accept()

    def done(self, result):
        if self.state != "CLOSED":
            self.state = "CLOSED"
            self.timer.stop()
            if self.capture:
                self.executor.submit(self.capture.stop)
            if self.guide:
                self.guide.close()
            self.executor.shutdown(wait=False)
        super().done(result)
