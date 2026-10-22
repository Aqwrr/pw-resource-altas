"""First-run setup; a game folder is a per-user choice, never a default."""

from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QStackedWidget,
    QWidget,
)
import atlas_core as core


class OnboardingDialog(QDialog):
    def __init__(self, parent=None, client=""):
        super().__init__(parent)
        self.setWindowTitle("Добро пожаловать в PW Resource Atlas")
        self.setMinimumWidth(560)
        self.resize(620, 420)
        self.client = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)
        self.steps = QLabel("ШАГ 1 ИЗ 2 · ПАПКА ИГРЫ")
        self.steps.setObjectName("muted")
        layout.addWidget(self.steps)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        first = QWidget()
        box = QVBoxLayout(first)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(14)
        title = QLabel("Настроим атлас для вашей игры")
        title.setObjectName("heading")
        box.addWidget(title)
        description = QLabel(
            "Укажите папку обычного клиента Comeback PW 1.3.6. Можно выбрать корень игры или каталог element. Русские буквы и пробелы в пути поддерживаются."
        )
        description.setWordWrap(True)
        box.addWidget(description)
        row = QHBoxLayout()
        self.path = QLineEdit(str(client or ""))
        self.path.setPlaceholderText("Путь к папке игры")
        self.path.setAccessibleName("Путь к папке игры")
        row.addWidget(self.path, 1)
        self.browse = QPushButton("Выбрать…")
        self.browse.clicked.connect(self.choose)
        row.addWidget(self.browse)
        box.addLayout(row)
        self.validation = QLabel("Папка ещё не выбрана. Без неё установка мода недоступна.")
        self.validation.setObjectName("muted")
        self.validation.setWordWrap(True)
        box.addWidget(self.validation)
        privacy = QLabel(
            "Путь хранится только на этом компьютере. Файлы игры на этом шаге не изменяются."
        )
        privacy.setObjectName("muted")
        privacy.setWordWrap(True)
        box.addWidget(privacy)
        box.addStretch(1)
        self.pages.addWidget(first)
        second = QWidget()
        box = QVBoxLayout(second)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(16)
        title = QLabel("Можно начинать сбор")
        title.setObjectName("heading")
        box.addWidget(title)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setObjectName("muted")
        box.addWidget(self.summary)
        for text in (
            "1. Выберите ресурсы галочками или примените готовый набор. Список всегда можно вернуть кнопкой «Показать все».",
            "2. «Карта поверх игры» открывает отдельное окно карты. Перемещайте и растягивайте его под своё окно игры.",
            "3. Для карты и маяков внутри игры закройте клиент и нажмите «Установить выбранные ресурсы».",
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            box.addWidget(label)
        box.addStretch(1)
        self.pages.addWidget(second)
        buttons = QHBoxLayout()
        self.exit = QPushButton("Выход")
        self.exit.clicked.connect(self.reject)
        buttons.addWidget(self.exit)
        buttons.addStretch(1)
        self.back = QPushButton("Назад")
        self.back.clicked.connect(self.previous)
        self.back.hide()
        buttons.addWidget(self.back)
        self.next = QPushButton("Продолжить")
        self.next.setObjectName("apply")
        self.next.setEnabled(False)
        self.next.clicked.connect(self.advance)
        buttons.addWidget(self.next)
        layout.addLayout(buttons)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(300)
        self.debounce.timeout.connect(self.validate)
        self.path.textChanged.connect(self.path_changed)
        if client:
            self.validate()

    def path_changed(self):
        self.client = None
        self.next.setEnabled(False)
        self.debounce.start()

    def choose(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Выберите папку Comeback PW 1.3.6", self.path.text() or str(Path.home())
        )
        if folder:
            self.path.setText(folder)
            self.debounce.stop()
            self.validate()

    def validate(self):
        try:
            self.client = core.require_supported_client(self.path.text().strip().strip('"'))
        except (OSError, ValueError, TypeError) as error:
            self.client = None
            self.validation.setText(str(error))
            self.validation.setStyleSheet("color:#9b4c31")
            self.next.setEnabled(False)
            return False
        self.validation.setText("Клиент 1.3.6 найден. Папка подходит.")
        self.validation.setStyleSheet("color:#24745c")
        self.next.setEnabled(True)
        return True

    def previous(self):
        self.pages.setCurrentIndex(0)
        self.steps.setText("ШАГ 1 ИЗ 2 · ПАПКА ИГРЫ")
        self.back.hide()
        self.next.setText("Продолжить")
        self.validate()

    def advance(self):
        if not self.validate():
            return
        if self.pages.currentIndex() == 0:
            self.summary.setText("Ваш клиент: " + str(self.client))
            self.pages.setCurrentIndex(1)
            self.steps.setText("ШАГ 2 ИЗ 2 · БЫСТРЫЙ СТАРТ")
            self.back.show()
            self.next.setText("Открыть атлас")
        else:
            self.accept()
