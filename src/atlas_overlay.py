"""A separate resizable map window; the main app never becomes topmost."""

from PySide6.QtCore import Qt, Signal, QRect, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizeGrip,
    QApplication,
)
from atlas_map import MapCanvas
import atlas_core as core


class MapOverlay(QWidget):
    closed = Signal()
    geometryChanged = Signal()

    def __init__(self, owner):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.owner = owner
        self.closing_with_owner = False
        self.initialized = False
        self.setWindowTitle("Карта ресурсов · Поверх игры")
        self.setMinimumSize(340, 300)
        self.resize(560, 620)
        box = QVBoxLayout(self)
        box.setContentsMargins(8, 8, 8, 6)
        box.setSpacing(6)
        header = QHBoxLayout()
        self.title = QLabel("Карта ресурсов")
        self.title.setStyleSheet("font-weight:600")
        header.addWidget(self.title, 1)
        for text, fn in [
            ("−", lambda: self.map.zoom(1 / 1.25)),
            ("Вся карта", lambda: self.map.fit()),
            ("+", lambda: self.map.zoom(1.25)),
        ]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            if text in ("−", "+"):
                b.setFixedWidth(38)
            header.addWidget(b)
        box.addLayout(header)
        self.map = MapCanvas(owner.items)
        self.map.setMinimumSize(220, 180)
        box.addWidget(self.map, 1)
        self.map.routeChanged.connect(owner.overlay_route_changed)
        self.map.coordinates.connect(self.coordinates)
        self.map.copied.connect(lambda text: owner.status.setText("Скопировано: " + text))
        self.map.notice.connect(lambda text: owner.status.setText(text))
        footer = QHBoxLayout()
        self.coords = QLabel("Колесо — масштаб · Shift+клик — в круг")
        self.coords.setObjectName("muted")
        footer.addWidget(self.coords, 1)
        footer.addWidget(QSizeGrip(self))
        box.addLayout(footer)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(400)
        self.debounce.timeout.connect(self.geometryChanged)
        saved = owner.state.get("overlay_geometry")
        if isinstance(saved, list) and len(saved) == 4:
            rect = QRect(*map(int, saved))
            rect.setWidth(max(340, rect.width()))
            rect.setHeight(max(300, rect.height()))
            screens = [s.availableGeometry() for s in QApplication.screens()]
            screen = next(
                (
                    s
                    for s in screens
                    if s.intersects(
                        QRect(rect.topLeft(), rect.size().boundedTo(QRect(0, 0, 80, 40).size()))
                    )
                ),
                screens[0],
            )
            rect.setWidth(min(rect.width(), screen.width()))
            rect.setHeight(min(rect.height(), screen.height()))
            rect.moveLeft(max(screen.left(), min(rect.left(), screen.right() - rect.width() + 1)))
            rect.moveTop(max(screen.top(), min(rect.top(), screen.bottom() - rect.height() + 1)))
            self.setGeometry(rect)
        self.initialized = True
        self.sync()

    def sync(self):
        source = self.owner.map
        changed = (self.map.world, self.map.style) != (source.world, source.style)
        if changed:
            self.map.set_view(source.world, source.style)
        self.map.selected = set(source.selected)
        self.map.marker_size = source.marker_size
        self.map.route = [list(p) for p in source.route]
        self.map.route_editable = not self.owner.busy
        self.title.setText(core.WORLDS[source.world]["name"])
        if self.map.auto_fit:
            self.map.fit()
        else:
            self.map.update()

    def coordinates(self, x, y):
        px, py = core.project(x, y, self.map.world)
        spec = core.WORLDS[self.map.world]
        self.coords.setText(
            f"X: {x:.1f} · Y: {y:.1f}"
            if 0 <= px < spec["columns"] * 256 and 0 <= py < spec["rows"] * 256
            else "Колесо — масштаб · Shift+клик — в круг"
        )

    def saved_geometry(self):
        r = self.normalGeometry() if self.isMaximized() else self.geometry()
        return [r.x(), r.y(), r.width(), r.height()]

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.initialized:
            self.debounce.start()

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.initialized:
            self.debounce.start()

    def closeEvent(self, event):
        self.debounce.stop()
        self.geometryChanged.emit()
        self.closed.emit()
        event.accept()
