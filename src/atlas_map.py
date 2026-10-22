"""Qt map view; game installation and resource storage stay outside the view."""

import math
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPixmap, QPen, QPolygonF, QFont
from PySide6.QtWidgets import QWidget, QToolTip, QApplication
import atlas_core as core
from atlas_markers import group_nodes, icon_offsets
from atlas_routes import MAX_POINTS

_icons = {}


def resource_pixmap(resource, size=22):
    key = (resource["key"], size)
    if key not in _icons:
        pix = QPixmap()
        pix.loadFromData(core.marker_png(resource["key"], resource["tier"], size), "PNG")
        _icons[key] = pix
    return _icons[key]


class MapCanvas(QWidget):
    coordinates = Signal(float, float)
    copied = Signal(str)
    routeChanged = Signal()
    notice = Signal(str)

    def __init__(self, resources):
        super().__init__()
        self.resources = resources
        self.selected = set()
        self.world = "world"
        self.style = "classic"
        self.params = core.read_json(core.ASSETS / "map-parameters.json")
        self.scale = 0.2
        self.pan = QPointF()
        self.fitted = False
        self.auto_fit = True
        self.last = None
        self.dragged = False
        self.marker_size = 16
        self.pix = QPixmap()
        self.nodes = []
        self.route = []
        self.route_editable = True
        self.setMouseTracking(True)
        self.setMinimumSize(320, 200)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.set_view("world", "classic")

    def set_view(self, world, style):
        self.world = world
        self.style = style
        source = core.ASSETS / (
            "classic-map.jpg"
            if world == "world" and style == "classic"
            else "default-" + world + ".jpg"
        )
        self.pix = QPixmap(str(source))
        if self.pix.isNull():
            raise ValueError("Не найдена карта " + world)
        self.nodes = [(r, x, y) for r in self.resources for x, y in core.resource_points(r, world)]
        self.fitted = False
        self.fit()

    def point(self, x, y):
        if self.world == "world" and self.style == "classic":
            px, py = core.project(x, y)
        else:
            px, py = core.world_project(x, y, self.params[self.world])
            py -= 256
        return QPointF(px * self.scale + self.pan.x(), py * self.scale + self.pan.y())

    def gamepoint(self, pos):
        px = (pos.x() - self.pan.x()) / self.scale
        py = (pos.y() - self.pan.y()) / self.scale
        if self.world == "world" and self.style == "classic":
            return core.unproject(px, py)
        p = self.params[self.world]
        py += 256
        return 400 + ((px - 1024) * 1024 * p["a"] / (2 * p["w"]) + p["ox"]) / 10, 550 + (
            p["oy"] - (py - 1024) * 1024 * p["b"] / (2 * p["h"])
        ) / 10

    def fit(self):
        if self.width() < 1 or self.height() < 1:
            return
        if self.world == "world" and self.style == "classic":
            left, top, right, bottom = core.CLASSIC_CROP
            for r, x, y in self.nodes:
                if r["key"] in self.selected:
                    px, py = core.project(x, y)
                    left = min(left, px - 45)
                    top = min(top, py - 45)
                    right = max(right, px + 45)
                    bottom = max(bottom, py + 45)
            for x, y in self.route:
                px, py = core.project(x, y)
                left = min(left, px - 45)
                top = min(top, py - 45)
                right = max(right, px + 45)
                bottom = max(bottom, py + 45)
        else:
            left, top, right, bottom = 0, 0, self.pix.width(), self.pix.height()
        groups = group_nodes([(r, x, y) for r, x, y in self.nodes if r["key"] in self.selected])
        radius = max(
            (
                max(
                    max(abs(dx), abs(dy))
                    for dx, dy in icon_offsets(len(group), self.marker_size + 3)
                )
                + self.marker_size / 2
                for group in groups
            ),
            default=0,
        )
        margin = max(12, radius + 4)
        self.scale = min(
            (self.width() - 2 * margin) / (right - left),
            (self.height() - 2 * margin) / (bottom - top),
        )
        self.pan = QPointF(
            self.width() / 2 - (left + right) / 2 * self.scale,
            self.height() / 2 - (top + bottom) / 2 * self.scale,
        )
        self.fitted = True
        self.auto_fit = True
        self.update()

    def zoom(self, factor, anchor=None):
        anchor = anchor or QPointF(self.width() / 2, self.height() / 2)
        old = self.scale
        self.scale = max(0.06, min(8, self.scale * factor))
        self.pan = anchor - (anchor - self.pan) * (self.scale / old)
        self.auto_fit = False
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.auto_fit or not self.fitted:
            self.fit()
        elif event.oldSize().isValid():
            self.pan += QPointF(
                (event.size().width() - event.oldSize().width()) / 2,
                (event.size().height() - event.oldSize().height()) / 2,
            )
            self.update()

    def visible_nodes(self):
        pad = self.marker_size * 3
        bounds = self.rect().adjusted(-pad, -pad, pad, pad)
        return [
            (r, x, y)
            for r, x, y in self.nodes
            if r["key"] in self.selected and bounds.contains(self.point(x, y).toPoint())
        ]

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#e9edf0"))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self.fitted:
            self.fit()
        p.save()
        p.translate(self.pan)
        p.scale(self.scale, self.scale)
        p.drawPixmap(0, 0, self.pix)
        p.restore()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(self.route) > 1:
            loop = QPolygonF([self.point(*xy) for xy in self.route + [self.route[0]]])
            p.setPen(
                QPen(
                    QColor("#173348"),
                    5,
                    Qt.PenStyle.SolidLine,
                    Qt.PenCapStyle.RoundCap,
                    Qt.PenJoinStyle.RoundJoin,
                )
            )
            p.drawPolyline(loop)
            p.setPen(QPen(QColor("#f0e5ac"), 2, Qt.PenStyle.DashLine))
            p.drawPolyline(loop)
        p.setPen(QColor("#24374c"))
        for members in group_nodes(self.visible_nodes()):
            s = self.marker_size
            anchor = self.point(*members[0][1:])
            offsets = icon_offsets(len(members), s + 3)
            if len(members) > 1:
                for dx, dy in offsets:
                    p.drawLine(anchor, anchor + QPointF(dx, dy))
            for (r, x, y), (dx, dy) in zip(members, offsets):
                q = anchor + QPointF(dx, dy)
                pix = resource_pixmap(r, s)
                p.drawPixmap(QRectF(q.x() - s / 2, q.y() - s / 2, s, s), pix, QRectF(pix.rect()))
            if len(members) > 1 and not any(dx == dy == 0 for dx, dy in offsets):
                p.fillRect(QRectF(anchor.x() - 1, anchor.y() - 1, 3, 3), QColor("#24374c"))
        font = QFont(self.font())
        font.setPixelSize(10)
        font.setBold(True)
        p.setFont(font)
        labels = []
        for i, xy in enumerate(self.route, 1):
            anchor = self.point(*xy)
            badge = QRectF(anchor.x() + 8, anchor.y() - 21, 26, 17)
            if not self.rect().intersects(badge.toAlignedRect()):
                continue
            if any(badge.adjusted(-2, -2, 2, 2).intersects(other) for other in labels):
                continue
            labels.append(badge)
            p.setPen(QPen(QColor("#fff8dd"), 1))
            p.setBrush(QColor("#087b69" if i == 1 else "#173348"))
            p.drawRoundedRect(badge, 5, 5)
            p.setPen(QColor("#ffffff"))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(i))

    def marker_positions(self):
        result = []
        for members in group_nodes(self.visible_nodes()):
            anchor = self.point(*members[0][1:])
            for (r, x, y), (dx, dy) in zip(
                members, icon_offsets(len(members), self.marker_size + 3)
            ):
                result.append((r, x, y, anchor + QPointF(dx, dy)))
        return result

    def closest(self, pos):
        best = None
        distance = max(12, self.marker_size / 2)
        for r, x, y, q in self.marker_positions():
            d = math.hypot(q.x() - pos.x(), q.y() - pos.y())
            if d < distance:
                best = (r, x, y)
                distance = d
        return best

    def wheelEvent(self, event):
        self.zoom(1.2 if event.angleDelta().y() > 0 else 1 / 1.2, event.position())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.last = event.position()
            self.dragged = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.last is not None:
            delta = event.position() - self.last
            if delta.manhattanLength() > 1:
                self.dragged = True
                self.pan += delta
                self.last = event.position()
                self.auto_fit = False
                self.update()
        else:
            x, y = self.gamepoint(event.position())
            self.coordinates.emit(x, y)
            near = self.closest(event.position())
            if near:
                r, x, y = near
                others = [
                    other["name"]
                    for other, ox, oy in self.visible_nodes()
                    if other["key"] != r["key"]
                    and round(ox, 4) == round(x, 4)
                    and round(oy, 4) == round(y, 4)
                ]
                extra = ("\nВ этой точке также: " + ", ".join(others)) if others else ""
                QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"{r['name']} · Т{r['tier']}\n{x:.1f}, {y:.1f}"
                    + extra
                    + "\nКлик — координаты · Shift+клик — в круг",
                    self,
                )
            else:
                QToolTip.hideText()

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        if event.button() == Qt.MouseButton.RightButton and self.route_editable and self.route:
            self.route.pop()
            self.routeChanged.emit()
            self.update()
        if event.button() == Qt.MouseButton.LeftButton and not self.dragged:
            near = self.closest(event.position())
            xy = (near[1], near[2]) if near else self.gamepoint(event.position())
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                if self.route_editable:
                    px, py = core.project(*xy, self.world)
                    spec = core.WORLDS[self.world]
                    if not (0 <= px < spec["columns"] * 256 and 0 <= py < spec["rows"] * 256):
                        self.notice.emit("Выберите точку внутри карты мира.")
                        self.last = None
                        return
                    if len(self.route) >= MAX_POINTS:
                        self.notice.emit("В круге уже 120 точек. Правый клик убирает последнюю.")
                    elif not any(math.dist(point, xy) < 0.0001 for point in self.route):
                        self.route.append(list(xy))
                        self.routeChanged.emit()
                        self.update()
            else:
                text = f"{round(xy[0])}, {round(xy[1])}"
                QApplication.clipboard().setText(text)
                self.copied.emit(text)
        self.last = None
