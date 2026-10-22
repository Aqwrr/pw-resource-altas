"""The only user window available before activation."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

import atlas_access as access
import atlas_core as core


class ActivationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PW Resource Atlas · Активация")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(500)
        self.resize(560, 330)
        box = QVBoxLayout(self)
        box.setContentsMargins(24, 24, 24, 24)
        box.setSpacing(14)
        title = QLabel("Активация атласа")
        title.setObjectName("heading")
        box.addWidget(title)
        note = QLabel("Введите ключ доступа. Он нужен для карты, маршрутов и установки ресурсов.")
        note.setWordWrap(True)
        box.addWidget(note)
        self.key = QLineEdit()
        self.key.setPlaceholderText("PWA-ADMIN-…")
        self.key.setAccessibleName("Ключ доступа")
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setMaxLength(256)
        self.key.returnPressed.connect(self.submit)
        box.addWidget(self.key)
        reveal = QCheckBox("Показать ключ")
        reveal.toggled.connect(
            lambda on: self.key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        box.addWidget(reveal)
        self.message = QLabel("Активация сохраняется на этом компьютере. Интернет не нужен.")
        self.message.setWordWrap(True)
        self.message.setObjectName("muted")
        box.addWidget(self.message)
        box.addStretch(1)
        buttons = QHBoxLayout()
        exit_button = QPushButton("Выход")
        exit_button.clicked.connect(self.reject)
        buttons.addWidget(exit_button)
        buttons.addStretch(1)
        self.activate_button = QPushButton("Активировать")
        self.activate_button.setObjectName("apply")
        self.activate_button.setEnabled(False)
        self.activate_button.clicked.connect(self.submit)
        buttons.addWidget(self.activate_button)
        box.addLayout(buttons)
        self.key.textChanged.connect(
            lambda text: self.activate_button.setEnabled(bool(text.strip()))
        )

    def submit(self):
        if not self.key.text().strip():
            return
        self.activate_button.setEnabled(False)
        try:
            access.activate(core.ROOT, self.key.text())
        except (OSError, ValueError) as error:
            self.message.setText(str(error))
            self.message.setStyleSheet("color:#9b4c31")
            self.activate_button.setEnabled(True)
            self.key.setFocus()
            return
        self.key.clear()
        self.accept()


def ensure_activation():
    if access.is_activated(core.ROOT):
        return True
    return ActivationDialog().exec() == QDialog.DialogCode.Accepted
