"""Update controls and background downloads; never block game operations."""

import threading
from PySide6.QtCore import QObject, Signal, QTimer, Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QCheckBox,
    QPushButton,
    QProgressBar,
    QPlainTextEdit,
    QMessageBox,
    QFrame,
)
import atlas_core as core
import atlas_updates as updates


class UpdateController(QObject):
    changed = Signal()
    result = Signal(str, object)
    failed = Signal(str)
    progressed = Signal(int)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.closed = False
        self.applying = False
        self.cancel = threading.Event()
        self.busy = False
        self.latest = None
        self.plan = None
        self.restart_requested = False
        self.dialog = None
        self.progress = 0
        self.prefs = updates.read_json(core.ROOT / "update-settings.json", {})
        if not isinstance(self.prefs, dict):
            self.prefs = {}
        self.prefs.setdefault("check_on_start", True)
        self.prefs.setdefault("auto_update", False)
        self.repo = updates.repository(
            core.read_json(core.ASSETS / "update-source.json", {})["repository"]
        )
        self.message = "Проверка ещё не выполнялась."
        self.plan = updates.pending(core.ROOT, core.VERSION)
        if self.plan:
            self.message = (
                "Обновление "
                + updates.load_plan(self.plan)[1]["version"]
                + " загружено и готово к установке."
            )
        previous = updates.read_json(core.ROOT / "updates/last-result.json", {})
        if previous and not previous.get("ok"):
            self.message = "Предыдущее обновление отменено. " + previous.get("error", "")
        self.result.connect(self.done)
        self.failed.connect(self.error)
        self.progressed.connect(self.set_progress)
        self.timer = QTimer(self)
        self.timer.setInterval(4 * 60 * 60 * 1000)
        self.timer.timeout.connect(self.scheduled_check)
        if not window.preview:
            self.timer.start()
            if self.prefs["check_on_start"]:
                QTimer.singleShot(1800, self.scheduled_check)

    def save(self):
        updates.write_json(core.ROOT / "update-settings.json", self.prefs)

    def set_preference(self, key, on):
        self.prefs[key] = bool(on)
        if key == "auto_update" and on:
            self.prefs["check_on_start"] = True
        self.save()
        self.changed.emit()
        if (
            key == "auto_update"
            and on
            and self.latest
            and self.latest.get("available")
            and not self.plan
        ):
            self.download()

    def start(self, kind, operation):
        if self.busy:
            return
        self.busy = True
        self.progress = 0
        self.cancel.clear()
        self.changed.emit()

        def worker():
            try:
                result = operation()
                if not self.closed:
                    self.result.emit(kind, result)
            except Exception as error:
                if not self.closed:
                    self.failed.emit(str(error))

        threading.Thread(target=worker, daemon=True, name="Atlas update " + kind).start()

    def check(self):
        if self.busy:
            return
        self.message = "Проверяем последнюю стабильную версию на GitHub…"
        self.start("check", lambda: updates.check(self.repo, core.VERSION))

    def scheduled_check(self):
        if self.closed or self.busy or self.window.busy or not self.prefs["check_on_start"]:
            return
        self.check()

    def download(self):
        if self.busy or not self.latest or not self.latest.get("available"):
            return
        self.message = "Загружаем и проверяем обновление…"
        self.start(
            "download",
            lambda: updates.prepare(core.ROOT, self.latest, self.report_progress, self.cancel),
        )

    def report_progress(self, value):
        if not self.closed:
            self.progressed.emit(value)

    def set_progress(self, value):
        self.progress = value
        self.changed.emit()

    def done(self, kind, result):
        self.busy = False
        if kind == "check":
            self.latest = result
            self.message = (
                "Доступна версия " + result["version"] + "."
                if result["available"]
                else "Установлена актуальная версия " + core.VERSION + "."
            )
            if result["available"]:
                self.window.updateButton.setText("Обновление " + result["version"])
                self.window.status.setText(self.message + " Кнопка «Обновления» — внизу окна.")
        else:
            self.plan = result
            self.message = "Обновление готово. " + (
                "Установится при закрытии атласа."
                if self.prefs["auto_update"]
                else "Нажмите «Установить и перезапустить»."
            )
            self.window.status.setText(self.message)
        self.changed.emit()
        if kind == "check" and result["available"] and self.prefs["auto_update"] and not self.plan:
            self.download()

    def error(self, message):
        self.busy = False
        self.message = message
        self.changed.emit()

    def show(self):
        if self.dialog:
            self.dialog.show()
            self.dialog.raise_()
            self.dialog.activateWindow()
            return
        self.dialog = UpdatesDialog(self, self.window)
        self.dialog.finished.connect(lambda _: setattr(self, "dialog", None))
        self.dialog.show()
        if self.latest is None and not self.busy:
            self.check()

    def install(self):
        if self.window.busy:
            self.message = "Дождитесь завершения установки карты или маяков."
            self.changed.emit()
            return
        if not self.plan or self.busy:
            return
        self.restart_requested = True
        self.window.close()

    def before_close(self):
        if self.plan and (self.restart_requested or self.prefs["auto_update"]):
            try:
                updates.launch(core.ROOT, self.plan, self.restart_requested)
                self.applying = True
            except Exception as error:
                self.restart_requested = False
                self.message = str(error)
                self.changed.emit()
                QMessageBox.warning(self.window, "Обновление не запущено", str(error))
                return False
        self.closed = True
        self.cancel.set()
        return True


class UpdatesDialog(QDialog):
    def __init__(self, controller, parent):
        super().__init__(parent)
        self.c = controller
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("Обновления PW Resource Atlas")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(560)
        self.resize(640, 570)
        box = QVBoxLayout(self)
        box.setContentsMargins(22, 20, 22, 20)
        box.setSpacing(12)
        heading = QHBoxLayout()
        title = QLabel("Обновления атласа")
        title.setObjectName("heading")
        heading.addWidget(title, 1)
        source = QLabel("GitHub Releases")
        source.setObjectName("muted")
        heading.addWidget(source)
        box.addLayout(heading)
        self.versions = QLabel()
        self.versions.setStyleSheet(
            "background:#e7eff9;border-radius:8px;padding:10px 12px;color:#27588f"
        )
        box.addWidget(self.versions)
        options = QFrame()
        options.setObjectName("statusCard")
        options_box = QVBoxLayout(options)
        options_box.setContentsMargins(12, 6, 12, 6)
        options_box.setSpacing(2)
        self.startup = QCheckBox("Проверять при запуске и раз в 4 часа")
        self.startup.toggled.connect(lambda on: controller.set_preference("check_on_start", on))
        options_box.addWidget(self.startup)
        self.auto = QCheckBox("Автообновление при закрытии атласа")
        self.auto.setToolTip(
            "Новая версия загрузится в фоне и установится после выхода из программы."
        )
        self.auto.toggled.connect(lambda on: controller.set_preference("auto_update", on))
        options_box.addWidget(self.auto)
        box.addWidget(options)
        note = QLabel(
            "Настройки и резервные копии сохраняются. Мод в игре обновляется кнопкой установки ресурсов."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        box.addWidget(note)
        self.notesTitle = QLabel("Что нового")
        self.notesTitle.setStyleSheet("font-weight:600")
        box.addWidget(self.notesTitle)
        self.notes = QPlainTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setPlaceholderText("Проверяем версию и загружаем описание изменений…")
        box.addWidget(self.notes, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        box.addWidget(self.status)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        box.addWidget(self.bar)
        row = QHBoxLayout()
        self.check = QPushButton("Проверить снова")
        self.check.clicked.connect(controller.check)
        row.addWidget(self.check, 1)
        self.action = QPushButton()
        self.action.setObjectName("apply")
        self.action.clicked.connect(self.act)
        row.addWidget(self.action, 1)
        close = QPushButton("Готово")
        close.clicked.connect(self.close)
        row.addWidget(close, 1)
        box.addLayout(row)
        controller.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        c = self.c
        self.versions.setText(
            "Ваша версия: "
            + core.VERSION
            + (
                "     Доступна: " + c.latest["version"]
                if c.latest and c.latest["available"]
                else ("     Всё обновлено" if c.latest else "")
            )
        )
        for box, key in ((self.startup, "check_on_start"), (self.auto, "auto_update")):
            box.blockSignals(True)
            box.setChecked(c.prefs[key])
            box.blockSignals(False)
        self.startup.setEnabled(not c.prefs["auto_update"])
        self.status.setText(c.message)
        self.check.setEnabled(not c.busy)
        self.action.setText("Установить и перезапустить" if c.plan else "Скачать обновление")
        self.action.setEnabled(
            not c.busy
            and not c.window.busy
            and bool(c.plan or c.latest and c.latest.get("available"))
        )
        self.action.setVisible(bool(c.plan or c.latest and c.latest.get("available")))
        self.bar.setVisible(c.busy)
        self.bar.setRange(0, 100 if c.progress else 0)
        self.bar.setValue(c.progress)
        if c.latest:
            self.notesTitle.setText("Что нового в версии " + c.latest["version"])
            self.notes.setPlainText(
                c.latest.get("notes") or "Описание изменений для этой версии не добавлено."
            )

    def act(self):
        if self.c.plan:
            self.c.install()
        else:
            self.c.download()

    def closeEvent(self, event):
        self.c.changed.disconnect(self.refresh)
        super().closeEvent(event)
