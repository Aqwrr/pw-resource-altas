"""Explicit personal-preset actions instead of icon-only controls."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
)


class PresetsDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("Мои наборы")
        self.resize(680, 450)
        self.setMinimumWidth(600)
        box = QVBoxLayout(self)
        box.setContentsMargins(22, 20, 22, 20)
        box.setSpacing(12)
        title = QLabel("Мои наборы ресурсов")
        title.setObjectName("heading")
        box.addWidget(title)
        note = QLabel(
            "Сохраните текущие галочки под своим названием. Встроенные наборы для заданий и крафта доступны в главном списке."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        box.addWidget(note)
        self.save = QPushButton("Сохранить текущий выбор…")
        self.save.setObjectName("apply")
        self.save.setEnabled(bool(owner.selected()))
        self.save.clicked.connect(lambda: self.action(owner.save_preset))
        box.addWidget(self.save)
        self.list = QTreeWidget()
        self.list.setRootIsDecorated(False)
        self.list.setHeaderLabels(["Название", "Видов"])
        self.list.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.list.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.list.itemSelectionChanged.connect(self.selection)
        self.list.itemDoubleClicked.connect(lambda *_: self.apply())
        box.addWidget(self.list, 1)
        self.empty = QLabel("Своих наборов пока нет. Отметьте ресурсы в атласе и сохраните выбор.")
        self.empty.setWordWrap(True)
        self.empty.setObjectName("muted")
        box.addWidget(self.empty)
        tools = QHBoxLayout()
        self.rename = QPushButton("Переименовать")
        self.rename.clicked.connect(lambda: self.action(owner.rename_preset, self.key()))
        tools.addWidget(self.rename)
        self.update = QPushButton("Заменить галочки")
        self.update.setToolTip("Обновить этот набор текущим выбором в атласе")
        self.update.clicked.connect(lambda: self.action(owner.update_preset, self.key()))
        tools.addWidget(self.update)
        self.remove = QPushButton("Удалить")
        self.remove.clicked.connect(lambda: self.action(owner.delete_preset, self.key()))
        tools.addWidget(self.remove)
        box.addLayout(tools)
        row = QHBoxLayout()
        row.addStretch(1)
        self.use = QPushButton("Применить набор")
        self.use.setObjectName("apply")
        self.use.clicked.connect(self.apply)
        row.addWidget(self.use)
        close = QPushButton("Готово")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        box.addLayout(row)
        self.refresh()

    def key(self):
        return (
            self.list.currentItem().data(0, Qt.ItemDataRole.UserRole)
            if self.list.currentItem()
            else None
        )

    def refresh(self):
        key = self.key() or self.owner.active_preset
        self.list.clear()
        for r in self.owner.preset_store.presets:
            row = QTreeWidgetItem([r["name"], str(len(r["selected"]))])
            row.setData(0, Qt.ItemDataRole.UserRole, r["id"])
            self.list.addTopLevelItem(row)
            if r["id"] == key:
                self.list.setCurrentItem(row)
        self.empty.setVisible(not self.list.topLevelItemCount())
        self.selection()

    def selection(self):
        active = bool(self.key())
        for b in (self.rename, self.remove, self.use):
            b.setEnabled(active)
        self.update.setEnabled(active and bool(self.owner.selected()))

    def action(self, fn, *args):
        fn(*args)
        self.refresh()

    def apply(self):
        if self.key():
            self.owner.preset_changed(self.owner.presets.findData(self.key()))
            self.accept()
