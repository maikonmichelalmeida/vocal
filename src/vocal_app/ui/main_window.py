"""Exercise catalog and controls. All media are local resources."""
from pathlib import Path
import time
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QComboBox, QSpinBox, QCheckBox, QGroupBox, QFileDialog,
    QDialog, QSizePolicy, QStackedWidget,
)
from vocal_app.core.catalog import load_catalog
from vocal_app.core.custom_exercise import load_custom_exercise
from vocal_app.core.training import FixedTimeline
from vocal_app.core.settings import SettingsStore, TrainingSettings
from vocal_app.core.guide import GUIDE_LEVELS, apply_guide_level
from vocal_app.core.notes import note_to_midi, transpose_note, parse_exercise
from vocal_app.audio.playback import GuidePlayer
from vocal_app.ui.widgets import TablatureView, DemoPlayer, PitchPlot


STYLE = """
QWidget { background: #101721; color: #edf3fa; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QDialog { background: #101721; }
QLabel { background: transparent; }
QLabel#title { font-size: 25px; font-weight: 700; color: #f6fbff; }
QLabel#eyebrow { color: #82c9ff; font-size: 11px; font-weight: 700; }
QLabel#objective { color: #bdcad9; font-size: 14px; }
QPushButton, QComboBox, QSpinBox, QLineEdit { background: #1c293b; border: 1px solid #34465e; border-radius: 6px; padding: 6px 9px; min-height: 23px; }
QPushButton:hover { background: #2a3c54; border-color: #7fc4ff; }
QPushButton:disabled { color: #738094; background: #151f2d; }
QPushButton#primary { background: #216950; border-color: #389c79; font-weight: 700; }
QGroupBox { border: 1px solid #304057; border-radius: 8px; margin-top: 12px; padding: 14px 10px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; color: #9eb4ce; }
QCheckBox { spacing: 7px; }
QTableWidget { background: #142031; gridline-color: #304057; alternate-background-color: #1b2a3d; }
QHeaderView::section { background: #26384f; color: #cbdcee; border: 0; padding: 7px; }
QScrollArea { border: 0; }
QProgressBar { border: 1px solid #304057; border-radius: 5px; text-align: center; }
QProgressBar::chunk { background: #288969; }
"""


class MainWindow(QMainWindow):
    def __init__(self, store=None, catalog=None):
        super().__init__()
        self.setWindowTitle("Vocal Trainer · Desktop")
        self.resize(1220, 880)
        self.setMinimumSize(850, 550)
        self.setStyleSheet(STYLE)
        self.store = store or SettingsStore()
        self.catalog = catalog or load_catalog()
        self.exercise = None
        self.custom_exercise = None
        self._loading = False
        self._session_index = int(self.store.data.get("session_index", 0))
        self.preview = None
        self.preview_future = None
        self.preview_started = None
        self.preview_index = -1
        self.preview_timer = QTimer(self)
        self.preview_timer.setInterval(15)
        self.preview_timer.timeout.connect(self._preview_tick)
        self.dialog = None
        central = QWidget()
        self.outer_layout = QVBoxLayout(central)
        self.outer_layout.setContentsMargins(12, 8, 12, 8)
        body = QWidget()
        self.outer_layout.addWidget(body, 1)
        self.layout = QVBoxLayout(body)
        self.layout.setSpacing(6)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.setCentralWidget(central)
        top = QHBoxLayout()
        self.session_select = QComboBox()
        self.session_select.setObjectName("sessionSelect")
        for key, focus in self.catalog.session_focus.items():
            self.session_select.addItem(f"{key} · {focus}", key)
        self.session_select.addItem("I · Personalizado (.txt)", "I")
        self.session_select.setMinimumWidth(0)
        self.session_select.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        top.addWidget(self.session_select, 1)
        self.exercise_select = QComboBox()
        self.exercise_select.setObjectName("exerciseSelect")
        for ex in self.catalog.exercises:
            self.exercise_select.addItem(f"{ex.id:02d} · {ex.name}", ex.id)
        top.addWidget(self.exercise_select, 1)
        self.exercise_select.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.import_button = QPushButton("Selecionar arquivo .txt…")
        self.import_button.clicked.connect(self.choose_custom_file)
        top.addWidget(self.import_button, 1)
        self.import_button.hide()
        self.previous = QPushButton("← Anterior")
        self.next = QPushButton("Próximo →")
        self.previous.clicked.connect(lambda: self.move(-1))
        self.next.clicked.connect(lambda: self.move(1))
        top.addWidget(self.previous)
        top.addWidget(self.next)
        self.layout.addLayout(top)
        self.eyebrow = QLabel()
        self.eyebrow.setObjectName("eyebrow")
        self.title = QLabel()
        self.title.setObjectName("title")
        self.objective = QLabel()
        self.objective.setObjectName("objective")
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        title_row = QHBoxLayout()
        title_row.addWidget(self.title, 1)
        self.demo = DemoPlayer()
        self.demo.setMaximumWidth(480)
        self.demo.playback_requested.connect(self.stop_preview)
        title_row.addWidget(self.demo, 1)
        self.layout.addLayout(title_row)
        info = QHBoxLayout()
        self.objective.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info.addWidget(self.objective, 1)
        info.addWidget(self.eyebrow)
        self.layout.addLayout(info)
        self.sequence = QLabel()
        self.sequence.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.sequence.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.variation = QLabel()
        self.variation.hide()
        self.layout.addWidget(self.sequence)
        self.score_pages = QStackedWidget()
        self.score_pages.setMinimumSize(0, 0)
        self.layout.addWidget(self.score_pages, 1)
        self.tab_view = TablatureView()
        self.score_pages.addWidget(self.tab_view)
        self.custom_plot = PitchPlot()
        self.score_pages.addWidget(self.custom_plot)
        self.placeholder = QLabel()
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.score_pages.addWidget(self.placeholder)
        self.zoom_controls = QWidget()
        zoom = QHBoxLayout(self.zoom_controls)
        zoom.setContentsMargins(0, 0, 0, 0)
        zoom.addWidget(QLabel("Tablatura"))
        zoom.addStretch()
        fit = QPushButton("Ajustar")
        fit.clicked.connect(self.tab_view.fit)
        expand = QPushButton("Ampliar tablatura")
        expand.clicked.connect(self.expand_tablature)
        zoom.addWidget(fit)
        zoom.addWidget(expand)
        self.layout.addWidget(self.zoom_controls)
        controls = QGroupBox("Treino principal")
        grid = QGridLayout(controls)
        self.start_button = QPushButton("Início")
        self.start_button.setObjectName("primary")
        self.start_button.clicked.connect(self.start_training)
        self.listen_button = QPushButton("Ouvir guia")
        self.listen_button.clicked.connect(self.start_preview)
        grid.addWidget(self.start_button, 0, 0)
        grid.addWidget(self.listen_button, 0, 1)
        self.instrument = QComboBox()
        for text, key in (("Violão nylon", "acoustic_guitar_nylon"), ("Violão aço", "acoustic_guitar_steel"), ("Piano acústico", "acoustic_grand_piano")):
            self.instrument.addItem(text, key)
        self.instrument.setCurrentIndex(max(0, self.instrument.findData(self.store.data.get("instrument", "acoustic_guitar_nylon"))))
        self.instrument.setToolTip("Instrumento do guia")
        grid.addWidget(self.instrument, 0, 2)
        self.guided = QCheckBox("Guia")
        self.guided.setToolTip("Desmarcado: só referência inicial; nos respiratórios, só contagem de entrada.")
        guide_row = QHBoxLayout()
        guide_row.addWidget(self.guided)
        tempo_row = QHBoxLayout()
        self.bpm = QSpinBox()
        self.bpm.setRange(40, 180)
        self.bpm.setSuffix(" bpm")
        minus, plus = QPushButton("−4"), QPushButton("+4")
        self.tempo_buttons = (minus, plus)
        minus.setFixedWidth(42)
        plus.setFixedWidth(42)
        minus.clicked.connect(lambda: self.bpm.setValue(self.bpm.value() - 4))
        plus.clicked.connect(lambda: self.bpm.setValue(self.bpm.value() + 4))
        tempo_row.addWidget(minus)
        tempo_row.addWidget(self.bpm)
        tempo_row.addWidget(plus)
        grid.addLayout(tempo_row, 1, 0, 1, 2)
        self.subdivision = QComboBox()
        for n in range(1, 5):
            self.subdivision.addItem(f"{n} nota(s) / pulso", n)
        grid.addWidget(self.subdivision, 1, 2)
        self.transpose = QSpinBox()
        self.transpose.setRange(-8, 8)
        self.transpose.setSuffix(" semitons")
        grid.addWidget(self.transpose, 1, 3, 1, 2)
        self.direction = QComboBox()
        self.direction.addItem("Concluir: subir ↑", True)
        self.direction.addItem("Concluir: descer ↓", False)
        grid.addWidget(self.direction, 1, 5)
        self.guide_level = QComboBox()
        self.guide_level.setObjectName("guideLevel")
        for key, label, description in GUIDE_LEVELS:
            self.guide_level.addItem(label, key)
            self.guide_level.setItemData(self.guide_level.count() - 1, description, Qt.ItemDataRole.ToolTipRole)
        self.guide_level.setToolTip("Notas fantasmas: alvo visível, sem instrumento nem correção ao vivo. O relatório mostra tudo.")
        guide_row.addWidget(QLabel("Nível"))
        self.guide_level.setMaximumWidth(200)
        guide_row.addWidget(self.guide_level)
        guide_row.addStretch()
        grid.addLayout(guide_row, 0, 3, 1, 3)
        self.outer_layout.addWidget(controls)
        self.status = QLabel("Pronto")
        self.status.setWordWrap(True)
        self.outer_layout.addWidget(self.status)
        self.session_select.currentIndexChanged.connect(self.choose_session)
        self.exercise_select.currentIndexChanged.connect(self.choose_exercise)
        for control, signal in ((self.bpm, "valueChanged"), (self.transpose, "valueChanged"), (self.subdivision, "currentIndexChanged"), (self.direction, "currentIndexChanged"), (self.instrument, "currentIndexChanged"), (self.guided, "toggled"), (self.guide_level, "currentIndexChanged")):
            getattr(control, signal).connect(self.save_controls)
        self._loading = True
        self.session_select.setCurrentIndex(max(0, self.session_select.findData(self.store.data.get("session", "A"))))
        self._loading = False
        exercise_id = self.store.data.get("exercise_id", 1)
        if self.session_select.currentData() == "I":
            self.choose_session()
        else:
            self.show_exercise(exercise_id if exercise_id in self.catalog.by_id else 1)
        if self.store.error:
            self.status.setText(self.store.error)
        available = self.screen().availableGeometry()
        self.resize(min(1220, available.width() - 40), min(880, available.height() - 50))

    def settings(self):
        return TrainingSettings(self.transpose.value(), self.direction.currentData(), self.guided.isChecked(), self.bpm.value(), self.subdivision.currentData(), self.guide_level.currentData())

    def save_controls(self, *_):
        if self._loading or self.exercise is None:
            return
        self.stop_preview()
        self.store.data.update(instrument=self.instrument.currentData(), session=self.session_select.currentData(), exercise_id=self.exercise.id, session_index=self._session_index)
        self.store.set_training(self.exercise.id, self.settings())
        self.update_sequence()
        if self.store.error:
            self.status.setText(self.store.error)

    def update_sequence(self):
        if self.exercise.mode == "breathing":
            self.sequence.setText("Respiração · 30 segundos · sem avaliação de pitch")
        else:
            shifted = [transpose_note(n, self.transpose.value()) for n in self.exercise.vocal_notes if n]
            self.sequence.setText("Notas  ·  " + "  ".join(shifted))
        self.variation.setText("Variação original  ·  " + self.exercise.variation)
        self.sequence.setToolTip(self.sequence.text() + "\n" + self.variation.text())
        if self.exercise.durations_ms:
            expected = parse_exercise(shifted)
            durations = self.settings().custom_durations_ms(self.exercise)
            self.custom_plot.configure(expected, self.settings().note_duration_ms, durations)
            self.custom_plot.cursor.hide()
            self.sequence.setToolTip(self.sequence.text() + "\nTempos atuais (ms): " + "  ".join(f"{d:g}" for d in durations))
            self.objective.setText(f"{len(durations)} notas · {sum(durations) / 1000:g} s · {self.bpm.value()} bpm (TXT: base 120)")

    def show_exercise(self, exercise_id):
        self.stop_preview()
        self.exercise = self.custom_exercise if exercise_id == 40 else self.catalog.by_id[exercise_id]
        if self.exercise is None:
            return
        custom = bool(self.exercise.durations_ms)
        self.set_custom_navigation(custom)
        self.start_button.setEnabled(True)
        self.listen_button.setEnabled(True)
        self._loading = True
        self.exercise_select.setCurrentIndex(self.exercise_select.findData(exercise_id))
        settings = self.store.training(self.exercise)
        self.bpm.setValue(settings.bpm)
        self.subdivision.setCurrentIndex(settings.subdivision - 1)
        self.transpose.setValue(settings.transpose)
        self.direction.setCurrentIndex(0 if settings.direction_up else 1)
        self.guided.setChecked(settings.guided)
        self.guide_level.setCurrentIndex(max(0, self.guide_level.findData(settings.guide_level)))
        self.guide_level.setEnabled(self.exercise.mode == "pitch")
        self.subdivision.setEnabled(not custom)
        self.subdivision.setToolTip("O ritmo relativo vem do TXT; ajuste a velocidade pelo BPM" if custom else "")
        for widget in (self.bpm, *self.tempo_buttons):
            widget.setEnabled(True)
            widget.setToolTip("Tempo da nota = tempo do TXT × 120 / BPM" if custom else "")
        self._loading = False
        self.eyebrow.setText("I · PERSONALIZADO" if custom else f"{self.exercise.id:02d} / 39 · {self.exercise.category.upper()}")
        self.title.setText(self.exercise.name)
        self.title.setToolTip(self.exercise.name)
        self.objective.setText(self.exercise.objective)
        self.objective.setToolTip(self.exercise.objective)
        self.update_sequence()
        if custom:
            self.score_pages.setCurrentWidget(self.custom_plot)
        elif self.exercise.image:
            self.tab_view.load(self.catalog.asset_path(self.exercise.image))
            self.score_pages.setCurrentWidget(self.tab_view)
        else:
            self.tab_view.load(None)
            self.placeholder.setText("Respiração · acompanhe o cronômetro e o metrônomo.")
            self.score_pages.setCurrentWidget(self.placeholder)
        self.zoom_controls.setVisible(bool(self.exercise.image))
        self.demo.load(self.catalog.asset_path(self.exercise.audio) if self.exercise.audio else None)
        self.demo.setVisible(not custom)
        self.status.setText("Pronto")
        self.save_controls()

    def set_custom_navigation(self, custom):
        self.exercise_select.setVisible(not custom)
        self.import_button.setVisible(custom)
        self.previous.setEnabled(not custom)
        self.next.setEnabled(not custom)

    def clear_custom_exercise(self):
        self.stop_preview()
        self.custom_exercise = self.exercise = None
        self.set_custom_navigation(True)
        self.start_button.setEnabled(False)
        self.listen_button.setEnabled(False)
        self.demo.load(None)
        self.demo.hide()
        self.title.setText("Exercício personalizado")
        self.title.setToolTip("")
        self.eyebrow.setText("I · PERSONALIZADO")
        self.objective.setText("Carregue um TXT com notas e tempos")
        self.objective.setToolTip("")
        self.sequence.clear()
        self.sequence.setToolTip("")
        self.zoom_controls.hide()
        self.placeholder.setText("Selecione um arquivo .txt para começar.\n\nExemplo:\nB3 D4 G4 E4\n500 500 500 500\n\nTempos em milissegundos, um por nota.")
        self.score_pages.setCurrentWidget(self.placeholder)
        self.status.setText("Aguardando arquivo .txt")

    def choose_custom_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Exercício personalizado", "", "Texto (*.txt)")
        if path:
            self.load_custom_file(path)

    def load_custom_file(self, path):
        self.clear_custom_exercise()
        try:
            exercise = load_custom_exercise(path)
        except (OSError, ValueError) as exc:
            self.status.setText(f"Arquivo inválido: {exc}")
            return False
        self.custom_exercise = exercise
        self.show_exercise(40)
        self.status.setText("Arquivo carregado · ouça o guia antes de iniciar")
        return True

    def choose_session(self, *_):
        if not self._loading:
            self._session_index = 0
            if self.session_select.currentData() == "I":
                self.clear_custom_exercise()
                self.store.data.update(session="I", session_index=0)
                self.store.save()
            else:
                self.show_exercise(self.catalog.sessions[self.session_select.currentData()][0])

    def choose_exercise(self, *_):
        if not self._loading and self.session_select.currentData() != "I":
            self.show_exercise(self.exercise_select.currentData())

    def move(self, delta):
        if self.session_select.currentData() == "I":
            return
        ids = self.catalog.sessions[self.session_select.currentData()]
        self._session_index = (self._session_index + delta) % len(ids)
        self.show_exercise(ids[self._session_index])

    def expand_tablature(self):
        if not self.exercise or not self.exercise.image:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(self.exercise.name + " · Tablatura")
        dialog.resize(1200, 750)
        layout = QVBoxLayout(dialog)
        view = TablatureView()
        layout.addWidget(view)
        view.load(self.catalog.asset_path(self.exercise.image))
        dialog.exec()

    def soundfont_path(self):
        return self.store.data.get("soundfont") or None

    def start_preview(self):
        if self.exercise is None:
            return
        if self.preview:
            self.stop_preview()
            return
        self.demo.player.stop()
        self.preview = GuidePlayer()
        self.preview_future = None if self.exercise.mode == "breathing" else self.preview.prepare(self.soundfont_path(), self.instrument.currentData())
        self.preview_started = time.perf_counter() if self.exercise.mode == "breathing" else None
        self.preview_index = -1
        self.preview_timeline = (FixedTimeline(parse_exercise(self.exercise.vocal_notes), self.settings().note_duration_ms,
                                              durations_ms=self.settings().custom_durations_ms(self.exercise))
                                 if self.exercise.mode == "pitch" else None)
        self.listen_button.setText("Parar guia")
        self.status.setText("Preparando guia local…")
        self.preview_timer.start()

    def _preview_tick(self):
        if self.preview and self.preview.last_error and self.preview_future is None:
            self.status.setText("Não foi possível reproduzir o guia: " + self.preview.last_error)
            self.stop_preview()
            return
        if self.preview_future:
            if not self.preview_future.done():
                return
            try:
                self.preview_future.result()
            except Exception as exc:
                self.status.setText(str(exc))
                self.stop_preview()
                return
            self.preview_future = None
            self.preview_started = time.perf_counter()
        settings = self.settings()
        elapsed = (time.perf_counter() - self.preview_started) * 1000
        duration = 60000 / settings.bpm if self.exercise.mode == "breathing" else settings.note_duration_ms
        index = int(elapsed // duration)
        count = 8 if self.exercise.mode == "breathing" else len(self.exercise.guide_notes)
        if self.preview_timeline:
            index = (self.preview_timeline.guide_index_at(elapsed)
                     if elapsed < self.preview_timeline.boundaries[-1] else count)
            if 0 <= index < count:
                duration = self.preview_timeline.durations_ms[index]
        if index >= count:
            self.stop_preview()
            self.status.setText("Prévia concluída.")
            return
        if index != self.preview_index:
            self.preview_index = index
            if self.exercise.mode == "breathing":
                self.preview.click(accent=index % 4 == 0)
            else:
                self.preview.stop()
                note = apply_guide_level(self.exercise.guide_notes, settings.guide_level)[index]
                if note:
                    self.preview.note_on(note_to_midi(note) + settings.transpose, velocity=127, duration=duration / 1000 * .9)
            self.status.setText(f"Prévia · {index + 1}/{count}")

    def stop_preview(self):
        self.preview_timer.stop()
        self.preview_future = None
        if self.preview:
            self.preview.close()
            self.preview = None
        self.listen_button.setText("Ouvir guia")

    def start_training(self):
        if self.exercise is None:
            return
        from vocal_app.ui.training_dialog import TrainingDialog
        self.stop_preview()
        self.demo.player.stop()
        self.save_controls()
        self.dialog = TrainingDialog(self.exercise, self.settings(), self.instrument.currentData(), self.soundfont_path(), parent=self)
        self.dialog.completed.connect(self.complete_training)
        self.dialog.finished.connect(lambda *_: setattr(self, "dialog", None))
        self.dialog.open()

    def complete_training(self):
        settings = self.settings().after_action("complete", finished=True)
        self.store.set_training(self.exercise.id, settings)
        self.show_exercise(self.exercise.id)
        self.status.setText(f"Concluído · próxima transposição: {settings.transpose:+d} semitons.")

    def closeEvent(self, event):
        if self.dialog:
            self.dialog.close()
        self.stop_preview()
        self.demo.player.stop()
        super().closeEvent(event)
