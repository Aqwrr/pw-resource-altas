import os
import sys
import argparse
import traceback
from pathlib import Path
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSize, QEvent
from PySide6.QtGui import QFont, QIcon, QFontDatabase, QColor, QPalette, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QComboBox,
    QFrame,
    QFileDialog,
    QMessageBox,
    QProgressBar,
    QDialog,
    QCheckBox,
    QSpinBox,
    QDialogButtonBox,
    QHeaderView,
    QStyledItemDelegate,
    QSizePolicy,
    QInputDialog,
)
import atlas_core as core
import atlas_minimap
from atlas_map import MapCanvas, resource_pixmap
from atlas_catalog import CatalogRepository
from atlas_presets import builtin_presets, PresetStore, clean_name
from atlas_routes import MAX_POINTS, world_routes, build_loop

STYLE = """
QWidget{font-family:"Segoe UI";font-size:13px;color:#263345;}
QMainWindow,QDialog{background:#f3f5f8;}
QMenuBar,QMenu{background:#fff;color:#263345;}
QMenuBar::item{padding:5px 9px;background:transparent;}
QMenuBar::item:selected,QMenu::item:selected{background:#eaf2ff;color:#164f96;}
QMenu{border:1px solid #d1d9e4;padding:5px;}
QMenu::item{padding:7px 24px 7px 12px;}
QFrame#sidebar{background:#fff;border-right:1px solid #dce3ec;}
QLabel#heading{font-size:21px;font-weight:600;color:#1b2c43;}
QLabel#muted{color:#67768a;font-size:12px;}
QLineEdit,QComboBox,QSpinBox{background:#fff;border:1px solid #bdc9d8;border-radius:8px;padding:0 11px;selection-background-color:#dceaff;selection-color:#183e72;min-height:36px;max-height:36px;}
QLineEdit:hover,QComboBox:hover,QSpinBox:hover{border-color:#829bb9;}
QLineEdit:focus,QComboBox:focus,QSpinBox:focus{border-color:#2671cb;background:#fbfdff;}
QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled{background:#edf1f6;color:#8794a5;border-color:#dbe2eb;}
QLineEdit{placeholder-text-color:#8190a3;}
QComboBox{padding-right:36px;}
QComboBox::drop-down{border:0;width:32px;subcontrol-origin:padding;subcontrol-position:top right;}
QComboBox::down-arrow{image:url("@UI@/chevron-down.svg");width:16px;height:16px;}
QComboBox QAbstractItemView{background:#fff;color:#263345;border:1px solid #bdc9d8;outline:0;padding:5px;selection-background-color:#e6effd;selection-color:#164f96;}
QComboBox QAbstractItemView::item{min-height:30px;padding:4px 10px;border-radius:4px;}
QSpinBox{padding-right:30px;}
QSpinBox::up-button,QSpinBox::down-button{border:0;width:28px;background:#f0f4f9;subcontrol-origin:border;}
QSpinBox::up-button{subcontrol-position:top right;border-top-right-radius:8px;}
QSpinBox::down-button{subcontrol-position:bottom right;border-bottom-right-radius:8px;}
QSpinBox::up-button:hover,QSpinBox::down-button:hover{background:#e0ebfa;}
QSpinBox::up-arrow{image:url("@UI@/chevron-up.svg");width:12px;height:12px;}
QSpinBox::down-arrow{image:url("@UI@/chevron-down.svg");width:12px;height:12px;}
QPushButton{background:#fff;border:1px solid #c4cfdd;border-radius:8px;padding:0 12px;min-height:36px;max-height:36px;font-weight:500;}
QPushButton:hover{background:#eff5ff;border-color:#8eacd1;color:#164f96;}
QPushButton:pressed{background:#dceaff;border-color:#5d8ec9;}
QPushButton:focus{border-color:#2671cb;}
QPushButton:disabled{color:#8b98a8;border-color:#dfe5ed;background:#f2f5f8;}
QPushButton#apply{background:#2469b9;border-color:#2469b9;color:#fff;font-size:13px;font-weight:600;padding:0 10px;}
QPushButton#apply:hover{background:#1b59a3;border-color:#1b59a3;}
QPushButton#apply:pressed{background:#164b8b;}
QPushButton#apply:disabled{background:#dce6f2;border-color:#dce6f2;color:#7a91ad;}
QPushButton#restore{font-size:13px;padding:0 10px;border-color:#e2bec5;color:#923b4c;background:#fff9fa;}
QPushButton#restore:hover{background:#fff0f3;border-color:#c78c9a;color:#7f2d3e;}
QPushButton#restore:disabled{color:#8b98a8;border-color:#dfe5ed;background:#f2f5f8;}
QTreeWidget{background:#fff;border:1px solid #dce3ec;border-radius:8px;outline:0;alternate-background-color:#fafbfd;show-decoration-selected:1;}
QTreeWidget::item{min-height:34px;padding:3px 4px;border:0;}
QTreeWidget::item:hover{background:#edf4fe;}
QTreeWidget::item:selected{background:#dfeeff;color:#173d70;}
QHeaderView::section{background:#f2f5f9;color:#63748b;border:0;border-bottom:1px solid #dce3ec;padding:8px 6px;font-weight:500;}
QCheckBox{spacing:9px;padding:6px 0;}
QCheckBox::indicator,QTreeView::indicator{width:20px;height:20px;}
QCheckBox::indicator:unchecked,QTreeView::indicator:unchecked{image:url("@UI@/check-empty.svg");}
QCheckBox::indicator:unchecked:hover,QTreeView::indicator:unchecked:hover{image:url("@UI@/check-hover.svg");}
QCheckBox::indicator:checked,QTreeView::indicator:checked{image:url("@UI@/check-on.svg");}
QCheckBox::indicator:checked:hover,QTreeView::indicator:checked:hover{image:url("@UI@/check-on-hover.svg");}
QCheckBox::indicator:disabled,QTreeView::indicator:disabled{image:url("@UI@/check-disabled.svg");}
QCheckBox::indicator:checked:disabled,QTreeView::indicator:checked:disabled{image:url("@UI@/check-on-disabled.svg");}
QScrollBar:vertical{background:#f3f6fa;width:11px;border:0;margin:2px;}
QScrollBar::handle:vertical{background:#b7c5d7;min-height:30px;border-radius:4px;}
QScrollBar::handle:vertical:hover{background:#8aa3c2;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}
QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{background:transparent;}
QProgressBar{border:0;background:#e1e9f3;border-radius:3px;max-height:7px;}
QProgressBar::chunk{background:#2671cb;border-radius:3px;}
QToolTip{background:#fff;color:#263345;border:1px solid #bdc9d8;padding:7px;}
QFrame#statusCard{background:#fff;border:1px solid #dce3ec;border-radius:10px;}
QLabel#coordinates{background:#e9eff7;color:#3d5574;border-radius:7px;padding:7px 9px;font-size:12px;}
QPlainTextEdit{background:#fff;border:1px solid #dce3ec;border-radius:8px;padding:10px;selection-background-color:#dceaff;}
QTextBrowser{background:#fff;border:0;selection-background-color:#dceaff;}
QTabWidget::pane{background:#fff;border:1px solid #dce3ec;border-radius:8px;top:-1px;}
QTabBar::tab{background:#edf1f6;border:1px solid #dce3ec;padding:10px 13px;margin-right:3px;border-top-left-radius:7px;border-top-right-radius:7px;color:#63748b;}
QTabBar::tab:selected{background:#fff;color:#164f96;border-bottom-color:#fff;}
QTabBar::tab:hover{color:#164f96;background:#eff5ff;}
""".replace("@UI@", (core.ASSETS / "ui").as_posix())


class StatusLabel(QLabel):
    """Keep long messages in a tooltip without making the window wider."""

    def __init__(self, text=""):
        super().__init__()
        self.full_text = ""
        self.setMinimumWidth(0)
        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setText(text)

    def setText(self, text):
        self.full_text = str(text)
        self.setToolTip(self.full_text)
        self.render_text()

    def render_text(self):
        super().setText(
            self.fontMetrics().elidedText(
                self.full_text, Qt.TextElideMode.ElideRight, max(1, self.width())
            )
        )

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render_text()


class ResourceDelegate(QStyledItemDelegate):
    """A resource can be checked by its whole name cell or the Space key."""

    def editorEvent(self, event, model, option, index):
        state = index.data(Qt.ItemDataRole.CheckStateRole)
        if state is None or not index.flags() & Qt.ItemFlag.ItemIsEnabled:
            return super().editorEvent(event, model, option, index)
        if (
            event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            return True
        mouse = (
            event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
            and option.rect.contains(event.position().toPoint())
        )
        keyboard = (
            event.type() == QEvent.Type.KeyPress
            and event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Select)
            and not event.isAutoRepeat()
        )
        if mouse or keyboard:
            checked = state in (Qt.CheckState.Checked, Qt.CheckState.Checked.value)
            return model.setData(
                index,
                Qt.CheckState.Unchecked.value if checked else Qt.CheckState.Checked.value,
                Qt.ItemDataRole.CheckStateRole,
            )
        return False


class Worker(QThread):
    progress = Signal(int)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, operation):
        super().__init__()
        self.operation = operation

    def run(self):
        try:
            self.completed.emit(self.operation(self.progress.emit))
        except Exception as error:
            log = core.ROOT / "logs/atlas-error.log"
            log.parent.mkdir(exist_ok=True)
            log.write_text(traceback.format_exc(), encoding="utf8")
            self.failed.emit(str(error))


class SettingsDialog(QDialog):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(420)
        box = QVBoxLayout(self)
        box.setSpacing(14)
        row = QHBoxLayout()
        row.addWidget(QLabel("Иконки большой карты"), 1)
        self.size = QSpinBox()
        self.size.setRange(8, 18)
        self.size.setFixedWidth(86)
        self.size.setValue(state.get("marker_size", 10))
        row.addWidget(self.size)
        box.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Размер миникарты"), 1)
        self.minimapScale = QComboBox()
        for scale in atlas_minimap.SCALES:
            self.minimapScale.addItem(
                f"{round(scale * 100)}% · {round(128 * scale)} × {round(128 * scale)}", scale
            )
        self.minimapScale.setCurrentIndex(
            max(0, self.minimapScale.findData(state.get("minimap_scale", 1.5)))
        )
        row.addWidget(self.minimapScale)
        box.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Размер меток на миникарте"), 1)
        self.miniSize = QSpinBox()
        self.miniSize.setRange(12, 40)
        self.miniSize.setFixedWidth(86)
        self.miniSize.setValue(state.get("minimap_marker_size", 24))
        self.miniSize.setToolTip("Настраивается отдельно от иконок большой карты")
        row.addWidget(self.miniSize)
        box.addLayout(row)
        self.bright = QCheckBox("Яркая подсветка ресурсов на миникарте")
        self.bright.setChecked(state.get("minimap_highlight", True))
        box.addWidget(self.bright)
        note = QLabel("Эти настройки применяются при следующей установке.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        box.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)


class CatalogDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ДК и формы")
        self.resize(750, 460)
        override = core.ROOT / "data/drop-catalog.json"
        self.repo = CatalogRepository.from_file(
            override if override.exists() else core.ASSETS / "drop-catalog.json"
        )
        box = QVBoxLayout(self)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Название предмета")
        row.addWidget(self.search, 1)
        self.kind = QComboBox()
        self.kind.addItem("Драконьи квесты", "dq")
        self.kind.addItem("Формы", "form")
        row.addWidget(self.kind)
        box.addLayout(row)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setObjectName("muted")
        box.addWidget(self.note)
        self.results = QTreeWidget()
        self.results.setHeaderLabels(["Предмет", "Моб", "Подземелье", "Шанс"])
        self.results.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        box.addWidget(self.results)
        self.search.textChanged.connect(self.refresh)
        self.kind.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        self.results.clear()
        items = self.repo.search_items(self.search.text(), self.kind.currentData())
        for item in items:
            for source in self.repo.item_sources(item["id"]) or [{}]:
                chance = source.get("probability")
                row = QTreeWidgetItem(
                    [
                        item["name"],
                        source.get("monster_name", "Нет данных"),
                        source.get("dungeon_name") or ("Открытый мир" if source else "Нет данных"),
                        "—" if chance is None else f"{chance * 100:g}%",
                    ]
                )
                if source:
                    row.setToolTip(
                        0,
                        (
                            "Подтверждено для сервера"
                            if source["verified"]
                            else "Не подтверждено для сервера"
                        )
                        + "\n"
                        + source["server"]
                        + " · "
                        + source["version"]
                        + "\n"
                        + source["url"],
                    )
                self.results.addTopLevelItem(row)
        self.note.setText(
            "В справочнике пока нет данных о дропе Comeback."
            if not self.repo.search_items()
            else f"Найдено предметов: {len(items)}"
        )

    def done(self, result):
        self.repo.close()
        super().done(result)


class Window(QMainWindow):
    def __init__(self, preview=False):
        super().__init__()
        if not preview:
            core.atlas_access.require_activated(core.ROOT)
        self.preview = preview
        self.items = core.resources()
        self.state = core.read_json(core.ROOT / "settings.json", {})
        self.worker = None
        self.busy = False
        self.leaves = {}
        self.groups = {}
        self.overlay = None
        self.state["client"] = self.state.get("client") or ""
        self.setWindowTitle("PW Resource Atlas " + core.VERSION)
        self.setMinimumSize(980, 600)
        available = QApplication.primaryScreen().availableGeometry()
        size = self.state.get("window_size", [1350, 900])
        self.resize(
            min(int(size[0]), max(980, available.width() - 24)) if not preview else 1350,
            min(int(size[1]), max(600, available.height() - 64)) if not preview else 900,
        )
        self.state.setdefault("marker_size", 10)
        self.state.setdefault("minimap_scale", 1.5)
        self.state.setdefault("minimap_highlight", True)
        self.state.setdefault("minimap_marker_size", 24)
        self.create_menu()
        self.routes = world_routes(self.state.get("routes"), self.state.get("route", []))
        self.builtin_presets = builtin_presets(self.items)
        self.active_preset = self.state.get("active_preset")
        self.preset_error = ""
        try:
            self.preset_store = PresetStore(core.ROOT / "presets.json")
        except ValueError as error:
            self.preset_store = None
            self.preset_error = str(error)
        outer = QWidget()
        self.setCentralWidget(outer)
        layout = QHBoxLayout(outer)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(370)
        left = QVBoxLayout(side)
        left.setContentsMargins(16, 16, 16, 16)
        left.setSpacing(8)
        layout.addWidget(side)
        heading_row = QHBoxLayout()
        heading = QLabel("Ресурсы и травы")
        heading.setObjectName("heading")
        heading_row.addWidget(heading, 1)
        self.resetFilters = QPushButton("Показать все")
        self.resetFilters.setToolTip(
            "Сбросить поиск и фильтры списка. Выбранные галочки сохранятся."
        )
        self.resetFilters.clicked.connect(self.reset_filters)
        heading_row.addWidget(self.resetFilters)
        left.addLayout(heading_row)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        self.presets = QComboBox()
        self.presets.setMinimumWidth(0)
        self.presets.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.presets.setAccessibleName("Быстрые наборы для сбора")
        self.presets.setMaxVisibleItems(18)
        self.presets.view().setMinimumWidth(350)
        preset_row.addWidget(self.presets, 1)
        self.managePresets = QPushButton("Мои наборы…")
        self.managePresets.setToolTip(
            "Сохранить текущие галочки, применить или изменить свой набор"
        )
        self.managePresets.clicked.connect(self.open_presets)
        preset_row.addWidget(self.managePresets)
        left.addLayout(preset_row)
        self.refresh_presets()
        self.presets.activated.connect(self.preset_changed)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Найти по названию")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_tree)
        left.addWidget(self.search)
        self.search.addAction(
            QIcon(str(core.ASSETS / "ui/search.svg")), QLineEdit.ActionPosition.LeadingPosition
        )
        filters = QHBoxLayout()
        self.tier = QComboBox()
        self.tier.addItem("Все уровни", 0)
        for n in range(1, 6):
            self.tier.addItem(f"Т{n}", n)
        self.category = QComboBox()
        self.category.addItem("Всё", "all")
        self.category.addItem("Материалы", "materials")
        self.category.addItem("Травы", "herbs")
        self.category.addItem("Выбранные", "selected")
        self.tier.currentIndexChanged.connect(self.filter_tree)
        self.category.currentIndexChanged.connect(self.filter_tree)
        filters.addWidget(self.tier)
        filters.addWidget(self.category)
        left.addLayout(filters)
        tools = QHBoxLayout()
        self.selectAll = QPushButton("Выбрать все")
        self.clear = QPushButton("Сбросить выбор")
        self.selectAll.setToolTip("Отметить все ресурсы, показанные в списке")
        self.clear.setToolTip("Снять все галочки и вернуть полный список ресурсов")
        self.selectAll.clicked.connect(lambda: self.select_visible(True))
        self.clear.clicked.connect(self.reset_selection)
        tools.addWidget(self.selectAll)
        tools.addWidget(self.clear)
        left.addLayout(tools)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Ресурс", "Точки"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIconSize(QSize(24, 24))
        self.tree.setIndentation(12)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.tree.setColumnWidth(1, 52)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setItemDelegate(ResourceDelegate(self.tree))
        self.tree.setUniformRowHeights(True)
        self.populate_tree()
        self.tree.itemChanged.connect(self.selection_changed)
        left.addWidget(self.tree, 1)
        self.count = QLabel()
        self.count.setObjectName("muted")
        self.count.setWordWrap(True)
        left.addWidget(self.count)
        self.beaconEnabled = QCheckBox("Маяки выбранных ресурсов")
        self.beaconEnabled.setChecked(bool(self.state.get("beacon_enabled", True)))
        self.beaconEnabled.setToolTip(
            "Добавить световые столбы только отмеченным материалам и травам Т1–Т5. Обновляются вместе с картой при установке."
        )
        self.beaconEnabled.toggled.connect(self.beacons_changed)
        left.addWidget(self.beaconEnabled)
        self.apply = QPushButton("Установить выбранные ресурсы")
        self.apply.setObjectName("apply")
        self.apply.clicked.connect(lambda: self.build(True))
        left.addWidget(self.apply)
        self.restore = QPushButton("Вернуть исходную карту")
        self.restore.setObjectName("restore")
        self.restore.setToolTip(
            "Убрать мод и восстановить сохранённые оригиналы карты, интерфейса и клиента"
        )
        self.restore.clicked.connect(self.restore_original)
        left.addWidget(self.restore)
        self.installState = QLabel()
        self.installState.setObjectName("muted")
        self.installState.setWordWrap(True)
        left.addWidget(self.installState)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        left.addWidget(self.progress)
        main = QVBoxLayout()
        main.setContentsMargins(18, 18, 18, 12)
        main.setSpacing(10)
        layout.addLayout(main, 1)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Мир:"))
        self.world = QComboBox()
        for key, spec in core.WORLDS.items():
            self.world.addItem(spec["name"], key)
        self.world.setCurrentIndex(
            max(0, self.world.findData(self.state.get("preview_world", "world")))
        )
        bar.addWidget(self.world)
        bar.addSpacing(10)
        bar.addWidget(QLabel("Карта:"))
        self.style = QComboBox()
        self.style.addItem("Цветная PW", "classic")
        self.style.addItem("Стандартная Comeback", "original")
        self.style.setCurrentIndex(1 if self.state.get("world_style") == "original" else 0)
        self.style.setMinimumWidth(215)
        bar.addWidget(self.style)
        bar.addStretch(1)
        self.settings = QPushButton("Настройки")
        self.settings.clicked.connect(self.edit_settings)
        bar.addWidget(self.settings)
        main.addLayout(bar)
        route_bar = QHBoxLayout()
        route_bar.setSpacing(6)
        self.autoRoute = QPushButton("Построить круг")
        self.autoRoute.setToolTip(
            "Замкнуть маршрут по выбранным точкам в видимой области карты (до 120). Приблизьте нужный район."
        )
        self.autoRoute.clicked.connect(self.auto_route)
        route_bar.addWidget(self.autoRoute)
        self.clearRoute = QPushButton("Очистить")
        self.clearRoute.setToolTip("Убрать круг в открытом мире")
        self.clearRoute.clicked.connect(self.clear_route)
        route_bar.addWidget(self.clearRoute)
        self.exportRoute = QPushButton("CSV")
        self.exportRoute.setToolTip("Сохранить координаты круга в CSV")
        self.exportRoute.clicked.connect(self.save_route)
        route_bar.addWidget(self.exportRoute)
        self.routeCount = QLabel("0 / 120")
        self.routeCount.setObjectName("muted")
        route_bar.addWidget(self.routeCount)
        route_bar.addStretch(1)
        self.topmost = QCheckBox("Карта поверх игры")
        self.topmost.setToolTip(
            "Отдельное окно только с картой. Его можно перемещать и растягивать; основная программа остаётся обычным окном."
        )
        self.topmost.setChecked(
            bool(self.state.get("overlay_enabled", self.state.get("topmost", False)))
        )
        self.topmost.toggled.connect(self.toggle_top)
        route_bar.addWidget(self.topmost)
        main.addLayout(route_bar)
        self.map = MapCanvas(self.items)
        main.addWidget(self.map, 1)
        self.map.coordinates.connect(self.show_coordinates)
        self.map.copied.connect(lambda text: self.status.setText("Координаты скопированы: " + text))
        self.map.routeChanged.connect(self.route_changed)
        self.map.notice.connect(lambda text: self.status.setText(text))
        navigation = QHBoxLayout()
        navigation.setSpacing(6)
        self.coords = QLabel("Координаты: —")
        self.coords.setObjectName("coordinates")
        self.coords.setFixedWidth(165)
        navigation.addWidget(self.coords)
        self.mapHelp = QPushButton("Управление")
        self.mapHelp.clicked.connect(self.show_map_help)
        navigation.addWidget(self.mapHelp)
        navigation.addStretch(1)
        for text, fn in [
            ("−", lambda: self.map.zoom(1 / 1.25)),
            ("Вся карта", self.map.fit),
            ("+", lambda: self.map.zoom(1.25)),
        ]:
            b = QPushButton(text)
            b.clicked.connect(fn)
            navigation.addWidget(b)
        main.addLayout(navigation)
        card = QFrame()
        card.setObjectName("statusCard")
        card_box = QVBoxLayout(card)
        card_box.setContentsMargins(10, 8, 10, 8)
        card_box.setSpacing(4)
        footer = QHBoxLayout()
        self.clientLabel = StatusLabel()
        self.clientLabel.setObjectName("muted")
        footer.addWidget(self.clientLabel, 1)
        self.folder = QPushButton("Папка игры…")
        self.folder.clicked.connect(self.choose_client)
        footer.addWidget(self.folder)
        card_box.addLayout(footer)
        main.addWidget(card)
        self.updateButton = QPushButton("Обновления")
        self.updateButton.clicked.connect(lambda: self.updates.show())
        footer.addWidget(self.updateButton)
        self.status = StatusLabel("Выберите ресурсы галочками или примените готовый набор.")
        self.status.setObjectName("muted")
        card_box.addWidget(self.status)
        self.world.currentIndexChanged.connect(self.view_changed)
        self.style.currentIndexChanged.connect(self.view_changed)
        self.view_changed()
        self.selection_changed()
        self.refresh_install_state()
        if self.preset_error:
            self.status.setText(self.preset_error)
        from atlas_updates_ui import UpdateController

        self.updates = UpdateController(self)

    def create_menu(self):
        menu = self.menuBar().addMenu("Файл")
        menu.addAction("Настройки…", self.edit_settings)
        menu.addAction("Собрать отдельные файлы", lambda: self.build(False))
        menu.addSeparator()
        menu.addAction("Папка программы", lambda: os.startfile(str(core.ROOT)))
        menu.addAction("Выход", self.close)
        help = self.menuBar().addMenu("Справка")
        help.addAction("Как пользоваться…", lambda: self.show_help("start"))
        help.addAction("Карта и управление…", lambda: self.show_help("map"))
        help.addAction("Маяки…", lambda: self.show_help("beacons"))
        help.addAction("ДК и формы…", self.open_catalog)
        help.addSeparator()
        help.addAction("Обновления…", lambda: self.updates.show())
        help.addAction("О программе…", lambda: self.show_help("about"))

    def populate_tree(self):
        selected = set(self.state.get("selected", []))
        self.tree.blockSignals(True)
        for tier in range(1, 6):
            level = 1 if tier == 1 else (tier - 1) * 20
            group = QTreeWidgetItem([f"Т{tier} · с {level} уровня", ""])
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            group.setFlags(Qt.ItemFlag.ItemIsEnabled)
            group.setBackground(0, QBrush(QColor("#f0f4f9")))
            group.setBackground(1, QBrush(QColor("#f0f4f9")))
            self.tree.addTopLevelItem(group)
            group.setExpanded(True)
            self.groups[tier] = group
            for r in self.items:
                if r["tier"] != tier:
                    continue
                item = QTreeWidgetItem([r["name"], ""])
                item.setData(0, Qt.ItemDataRole.UserRole, r["key"])
                item.setIcon(0, QIcon(resource_pixmap(r, 24)))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(
                    0, Qt.CheckState.Checked if r["key"] in selected else Qt.CheckState.Unchecked
                )
                item.setTextAlignment(
                    1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
                group.addChild(item)
                self.leaves[r["key"]] = item
        self.tree.blockSignals(False)

    def selected(self):
        return {
            key for key, row in self.leaves.items() if row.checkState(0) == Qt.CheckState.Checked
        }

    def all_presets(self):
        return self.builtin_presets + (self.preset_store.presets if self.preset_store else [])

    def find_preset(self, preset_id):
        return next((row for row in self.all_presets() if row["id"] == preset_id), None)

    def refresh_presets(self):
        self.presets.blockSignals(True)
        self.presets.clear()
        self.presets.addItem("Ручной выбор", None)
        group = None
        for row in self.all_presets():
            section = row.get("group", "Мои пресеты")
            if section != group:
                group = section
                self.presets.addItem(section, None)
                item = self.presets.model().item(self.presets.count() - 1)
                item.setEnabled(False)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
            self.presets.addItem(row["name"], row["id"])
            self.presets.setItemData(
                self.presets.count() - 1,
                row.get("note", "Свой набор ресурсов") + "\n" + row.get("details", ""),
                Qt.ItemDataRole.ToolTipRole,
            )
        self.presets.setCurrentIndex(max(0, self.presets.findData(self.active_preset)))
        self.presets.blockSignals(False)
        self.managePresets.setEnabled(self.preset_store is not None and not self.busy)

    def sync_preset(self, selected):
        row = self.find_preset(self.active_preset)
        if row is None or set(row["selected"]) != selected:
            self.active_preset = None
            row = None
        self.presets.blockSignals(True)
        self.presets.setCurrentIndex(max(0, self.presets.findData(self.active_preset)))
        self.presets.blockSignals(False)
        self.presets.setToolTip(
            (
                row["name"]
                + "\n"
                + row.get("note", "Свой набор ресурсов")
                + "\n"
                + row.get("details", "")
            )
            if row
            else "Недельки, полики, материалы для крафта и свои пресеты. Выбор набора заменяет все галочки."
        )

    def preset_changed(self, index):
        preset_id = self.presets.itemData(index)
        if not preset_id:
            self.active_preset = None
            self.reset_filters()
            self.sync_preset(self.selected())
            self.save_settings()
            return
        row = self.find_preset(preset_id)
        if row is None:
            return
        selected = set(row["selected"])
        unknown = selected - set(self.leaves)
        if unknown:
            self.sync_preset(self.selected())
            QMessageBox.warning(
                self,
                "Не удалось применить набор",
                "В наборе есть неизвестные ресурсы: "
                + ", ".join(sorted(unknown))
                + ". Текущий выбор сохранён.",
            )
            return
        self.search.clear()
        self.tier.setCurrentIndex(0)
        self.active_preset = preset_id
        self.tree.blockSignals(True)
        for key, item in self.leaves.items():
            item.setCheckState(
                0, Qt.CheckState.Checked if key in selected else Qt.CheckState.Unchecked
            )
        self.tree.blockSignals(False)
        self.category.setCurrentIndex(self.category.findData("all"))
        counts = {
            world: sum(core.resource_count(r, world) for r in self.items if r["key"] in selected)
            for world in core.WORLDS
        }
        if not counts[self.world.currentData()] and max(counts.values()):
            self.world.setCurrentIndex(self.world.findData(max(counts, key=counts.get)))
        self.selection_changed()
        first = next((self.leaves[r["key"]] for r in self.items if r["key"] in selected), None)
        if first:
            self.tree.scrollToItem(first)
        self.status.setText(
            row["name"]
            + " · "
            + row.get("note", "Галочки набора применены.")
            + " Состав — в подсказке списка наборов."
        )

    def save_preset(self):
        if self.busy or self.preset_store is None:
            return
        if not self.selected():
            QMessageBox.information(
                self, "Сохранить пресет", "Сначала выберите хотя бы один ресурс."
            )
            return
        active = self.preset_store.find(self.active_preset)
        name, accepted = QInputDialog.getText(
            self, "Сохранить свой пресет", "Название набора:", text=active["name"] if active else ""
        )
        if not accepted:
            return
        try:
            name = clean_name(name)
            existing = next(
                (r for r in self.preset_store.presets if r["name"].casefold() == name.casefold()),
                None,
            )
            if (
                existing
                and QMessageBox.question(
                    self,
                    "Обновить пресет",
                    f"Заменить набор «{existing['name']}» текущим выбором?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            row = self.preset_store.save(
                name, self.selected(), existing["id"] if existing else None
            )
            self.active_preset = row["id"]
            self.refresh_presets()
            self.selection_changed()
            self.status.setText("Сохранён свой пресет: " + row["name"])
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Не удалось сохранить пресет", str(error))

    def open_presets(self):
        if self.busy or self.preset_store is None:
            return
        from atlas_preset_ui import PresetsDialog

        PresetsDialog(self).exec()

    def reset_filters(self):
        if not hasattr(self, "tree"):
            return
        for widget in (self.search, self.tier, self.category):
            widget.blockSignals(True)
        self.search.clear()
        self.tier.setCurrentIndex(0)
        self.category.setCurrentIndex(self.category.findData("all"))
        for widget in (self.search, self.tier, self.category):
            widget.blockSignals(False)
        self.filter_tree()

    def reset_selection(self):
        if self.busy:
            return
        self.active_preset = None
        self.tree.blockSignals(True)
        for row in self.leaves.values():
            row.setCheckState(0, Qt.CheckState.Unchecked)
        self.tree.blockSignals(False)
        self.reset_filters()
        self.selection_changed()
        self.status.setText("Выбор сброшен. Показаны все доступные ресурсы.")

    def update_preset(self, preset_id):
        if self.busy or self.preset_store is None:
            return
        row = self.preset_store.find(preset_id)
        if row is None:
            return
        try:
            self.preset_store.save(row["name"], self.selected(), preset_id)
            self.active_preset = preset_id
            self.refresh_presets()
            self.selection_changed()
            self.status.setText("Пресет обновлён: " + row["name"])
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Не удалось обновить пресет", str(error))

    def rename_preset(self, preset_id):
        if self.busy or self.preset_store is None:
            return
        row = self.preset_store.find(preset_id)
        if row is None:
            return
        name, accepted = QInputDialog.getText(
            self, "Переименовать пресет", "Новое название:", text=row["name"]
        )
        if not accepted:
            return
        try:
            self.preset_store.rename(preset_id, name)
            self.refresh_presets()
            self.selection_changed()
            self.status.setText("Название пресета сохранено.")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Не удалось переименовать пресет", str(error))

    def delete_preset(self, preset_id):
        if self.busy or self.preset_store is None:
            return
        row = self.preset_store.find(preset_id)
        if row is None:
            return
        if (
            QMessageBox.question(
                self,
                "Удалить пресет",
                f"Удалить свой набор «{row['name']}»? Выбранные галочки останутся.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.preset_store.delete(preset_id)
            self.refresh_presets()
            self.selection_changed()
            self.status.setText("Свой пресет удалён. Текущий выбор сохранён.")
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Не удалось удалить пресет", str(error))

    def selection_changed(self, *args):
        if not hasattr(self, "map"):
            return
        selected = self.selected()
        world = self.world.currentData()
        self.map.selected = selected
        self.map.marker_size = self.state["marker_size"] + 4
        self.sync_preset(selected)
        self.tree.blockSignals(True)
        for key, row in self.leaves.items():
            brush = QBrush(QColor("#edf5ff")) if key in selected else QBrush()
            row.setBackground(0, brush)
            row.setBackground(1, brush)
        self.tree.blockSignals(False)
        self.filter_tree()
        if self.map.auto_fit:
            self.map.fit()
        else:
            self.map.update()
        count = sum(len(core.resource_points(r, world)) for r in self.items if r["key"] in selected)
        self.count.setText(
            f"Выбрано видов: {len(selected)} · Точек здесь: {count:,}".replace(",", " ")
        )
        self.apply.setEnabled(bool(selected) and not self.busy and bool(self.state.get("client")))
        self.sync_overlay()
        self.save_settings()
        self.refresh_install_state()

    def filter_tree(self, *args):
        if not hasattr(self, "tree"):
            return
        query = self.search.text().casefold().replace("ё", "е").strip()
        tier = self.tier.currentData()
        category = self.category.currentData()
        selected = self.selected()
        for r in self.items:
            matches = (
                category == "all"
                or (category == "selected" and r["key"] in selected)
                or (category == "materials" and r["kind"] != "herb")
                or (category == "herbs" and r["kind"] == "herb")
            )
            visible = (
                (not tier or r["tier"] == tier)
                and matches
                and query in r["name"].casefold().replace("ё", "е")
            )
            self.leaves[r["key"]].setHidden(not visible)
        for group in self.groups.values():
            group.setHidden(all(group.child(i).isHidden() for i in range(group.childCount())))
        visible = sum(not row.isHidden() for row in self.leaves.values())
        self.tree.setHeaderLabels([f"Ресурс · {visible} / {len(self.leaves)}", "Точки"])
        self.resetFilters.setEnabled(bool(query or tier or category != "all") and not self.busy)

    def select_visible(self, checked):
        self.tree.blockSignals(True)
        for row in self.leaves.values():
            if not row.isHidden() and not row.parent().isHidden():
                row.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.tree.blockSignals(False)
        self.selection_changed()

    def view_changed(self, *args):
        if not hasattr(self, "map"):
            return
        world = self.world.currentData()
        self.map.route = self.routes[world]
        self.map.set_view(world, self.style.currentData())
        self.style.setEnabled(world == "world")
        self.refresh_route_controls()
        self.tree.blockSignals(True)
        for r in self.items:
            row = self.leaves[r["key"]]
            count = len(core.resource_points(r, world))
            row.setText(1, str(count))
            row.setForeground(1, QColor("#6b7480" if count else "#a3aab3"))
            areas = ", ".join(
                spec["name"] for key, spec in core.WORLDS.items() if core.resource_points(r, key)
            )
            row.setToolTip(
                0, f"Т{r['tier']} · ID {r['id']}\nМиры: {areas}\nВ текущем мире: {count} точек"
            )
        self.tree.blockSignals(False)
        self.selection_changed()
        self.map.fit()

    def show_coordinates(self, x, y):
        px, py = core.project(x, y, self.map.world)
        spec = core.WORLDS[self.map.world]
        self.coords.setText(
            f"X: {x:.1f} · Y: {y:.1f}"
            if 0 <= px < spec["columns"] * 256 and 0 <= py < spec["rows"] * 256
            else "Координаты: —"
        )

    def show_help(self, topic="start"):
        from atlas_help import HelpDialog

        HelpDialog(self, topic).exec()

    def show_map_help(self):
        self.show_help("map")

    def beacons_changed(self):
        self.save_settings()
        self.refresh_install_state()

    def refresh_route_controls(self):
        route = self.map.route
        self.routeCount.setText(f"{len(route)} / {MAX_POINTS}")
        self.routeCount.setToolTip(
            "Точек в круге: "
            + str(len(route))
            + ". Начало отмечено зелёным номером 1. Порядок обхода сохранён в CSV."
        )
        self.clearRoute.setEnabled(bool(route) and not self.busy)
        self.exportRoute.setEnabled(bool(route) and not self.busy)

    def route_changed(self):
        self.routes[self.map.world] = self.map.route
        self.refresh_route_controls()
        self.map.update()
        self.sync_overlay()
        self.save_settings()
        self.refresh_install_state()

    def auto_route(self):
        if self.busy:
            return
        points = [
            (x, y)
            for r, x, y in self.map.visible_nodes()
            if self.map.rect().contains(self.map.point(x, y).toPoint())
        ]
        center = self.map.gamepoint(self.map.rect().center())
        try:
            route = build_loop(points, center)
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.map.route = route
        self.route_changed()
        self.status.setText(
            f"Круг построен: {len(route)} точек. Линия замкнута; рельеф и препятствия не учитываются."
        )

    def clear_route(self):
        if self.busy:
            return
        self.map.route = []
        self.route_changed()
        self.status.setText("Круг в открытом мире очищен.")

    def save_route(self):
        if self.busy or not self.map.route:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить круг сбора",
            str(core.ROOT / ("route-" + self.map.world + ".csv")),
            "CSV (*.csv)",
        )
        if path:
            try:
                core.export_route(self.map.route, path)
                self.status.setText("Координаты круга сохранены: " + path)
            except OSError as error:
                QMessageBox.warning(self, "Не удалось сохранить CSV", str(error))

    def toggle_top(self, on):
        if on:
            if self.overlay is None:
                from atlas_overlay import MapOverlay

                self.overlay = MapOverlay(self)
                self.overlay.closed.connect(self.overlay_closed)
                self.overlay.geometryChanged.connect(self.save_settings)
            self.overlay.closing_with_owner = False
            self.overlay.sync()
            self.overlay.show()
            self.overlay.raise_()
        elif self.overlay:
            self.overlay.close()
        self.save_settings()

    def overlay_closed(self):
        if self.overlay and not self.overlay.closing_with_owner:
            self.topmost.blockSignals(True)
            self.topmost.setChecked(False)
            self.topmost.blockSignals(False)
            self.save_settings()

    def sync_overlay(self):
        if self.overlay:
            self.overlay.sync()

    def overlay_route_changed(self):
        if not self.overlay:
            return
        self.map.route = [list(p) for p in self.overlay.map.route]
        self.route_changed()

    def begin_first_run(self):
        if self.preview:
            return
        try:
            client = core.require_supported_client(self.state.get("client"))
        except (OSError, ValueError, TypeError):
            from atlas_onboarding import OnboardingDialog

            dialog = OnboardingDialog(self, self.state.get("client", ""))
            if dialog.exec() != QDialog.DialogCode.Accepted:
                self.close()
                return
            client = dialog.client
        self.state["client"] = str(client)
        self.state["onboarding_completed"] = True
        self.save_settings()
        self.selection_changed()
        self.refresh_install_state()
        if self.topmost.isChecked():
            self.toggle_top(True)

    def save_settings(self):
        if self.preview or not hasattr(self, "map"):
            return
        self.state.update(
            selected=sorted(self.selected()),
            world_style=self.style.currentData(),
            preview_world=self.world.currentData(),
            ui_version=core.VERSION,
            active_preset=self.active_preset,
            routes=self.routes,
            route=self.routes["world"],
            topmost=False,
            overlay_enabled=self.topmost.isChecked(),
        )
        self.state["beacon_enabled"] = self.beaconEnabled.isChecked()
        if self.overlay:
            self.state["overlay_geometry"] = self.overlay.saved_geometry()
        if self.isVisible():
            geometry = (
                self.normalGeometry()
                if self.isMaximized() or self.isFullScreen()
                else self.geometry()
            )
            self.state.update(
                window_size=[geometry.width(), geometry.height()],
                window_maximized=self.isMaximized(),
            )
        core.write_json(core.ROOT / "settings.json", self.state)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "sidebar"):
            self.sidebar.setFixedWidth(max(350, min(420, round(event.size().width() * 0.274))))

    def refresh_install_state(self):
        state = core.read_json(core.ROOT / "installed.json")
        self.restore.setEnabled(bool(state) and not self.busy)
        pending = bool(state) and (
            state.get("map_version", state.get("version")) != core.MAP_VERSION
            or set(state.get("selected", [])) != self.selected()
            or any(
                self.state.get(key) != value
                for key, value in state.get("build_options", {}).items()
            )
            or self.routes != world_routes(state.get("routes"), state.get("route", []))
        )
        beacon = core.read_json(core.ROOT / "glow-test/installed.json")
        enabled = self.beaconEnabled.isChecked()
        pending |= bool(state) and (
            (
                enabled
                and (
                    not beacon
                    or beacon.get("status") != "installed"
                    or beacon.get("format") != 2
                    or set(beacon.get("resource_keys", [])) != self.selected()
                )
            )
            or (not enabled and bool(beacon))
        )
        client = self.state.get("client") or ""
        other_client = bool(state) and (
            not client or Path(state["client"]).resolve() != Path(client).resolve()
        )
        self.installState.setText(
            "Сначала укажите папку игры."
            if not client
            else (
                "Мод установлен в другом клиенте."
                if other_client
                else (
                    "Есть изменения · нужно установить"
                    if pending
                    else (
                        "Мод установлен · оригиналы сохранены"
                        if state
                        else "Исходная карта · мод не установлен"
                    )
                )
            )
        )
        self.installState.setStyleSheet("color:#956017" if pending or other_client else "")
        self.restore.setToolTip(
            "Восстановить оригиналы в " + state["client"] if state else "Мод ещё не установлен"
        )
        self.clientLabel.setText(
            "Клиент · " + Path(client).name if client else "Папка игры не выбрана"
        )
        self.clientLabel.setToolTip(client or "Укажите папку обычного клиента Comeback PW 1.3.6")

    def choose_client(self):
        path = QFileDialog.getExistingDirectory(
            self, "Папка клиента Comeback PW", self.state.get("client") or str(Path.home())
        )
        if path:
            try:
                client = core.require_supported_client(path)
            except (OSError, ValueError, TypeError) as error:
                QMessageBox.warning(self, "Папка клиента", str(error))
                return
            self.state["client"] = str(client)
            self.state["onboarding_completed"] = True
            self.save_settings()
            self.selection_changed()
            self.refresh_install_state()
            self.status.setText("Папка игры сохранена. Выберите ресурсы для установки.")

    def edit_settings(self):
        if not hasattr(self, "state"):
            return
        dialog = SettingsDialog(self.state, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.state.update(
                marker_size=dialog.size.value(),
                minimap_scale=dialog.minimapScale.currentData(),
                minimap_highlight=dialog.bright.isChecked(),
                minimap_marker_size=dialog.miniSize.value(),
            )
            self.selection_changed()

    def open_catalog(self):
        try:
            dialog = CatalogDialog(self)
            dialog.exec()
        except Exception as error:
            QMessageBox.warning(self, "Справочник", str(error))

    def set_busy(self, on):
        self.busy = on
        for widget in (
            self.tree,
            self.search,
            self.tier,
            self.category,
            self.selectAll,
            self.clear,
            self.world,
            self.style,
            self.settings,
            self.folder,
            self.presets,
            self.managePresets,
            self.resetFilters,
            self.autoRoute,
            self.beaconEnabled,
        ):
            widget.setEnabled(not on)
        self.map.route_editable = not on
        self.refresh_route_controls()
        self.managePresets.setEnabled(not on and self.preset_store is not None)
        self.style.setEnabled(not on and self.world.currentData() == "world")
        self.apply.setEnabled(not on and bool(self.selected()) and bool(self.state.get("client")))
        self.restore.setEnabled(not on and bool(core.read_json(core.ROOT / "installed.json")))
        self.progress.setVisible(on)
        self.sync_overlay()
        self.filter_tree()

    def start_job(self, operation, callback, text):
        if self.busy:
            return
        self.set_busy(True)
        self.progress.setValue(0)
        self.status.setText(text)
        self.worker = Worker(operation)
        self.worker.progress.connect(self.progress.setValue)
        self.worker.completed.connect(callback)
        self.worker.failed.connect(self.job_error)
        self.worker.start()

    def build(self, install):
        if self.busy or not self.selected():
            return
        if not self.state.get("client"):
            self.choose_client()
            return
        try:
            if install and core.game_running():
                QMessageBox.information(
                    self, "Закройте игру", "Перед установкой полностью закройте игру."
                )
                return
        except Exception as error:
            QMessageBox.warning(self, "Проверка клиента", str(error))
            return
        self.save_settings()
        selected = sorted(self.selected())
        client = self.state.get("client") or ""
        options = {
            key: self.state[key]
            for key in ("marker_size", "minimap_scale", "minimap_highlight", "minimap_marker_size")
        }
        options["world_style"] = self.style.currentData()
        options["routes"] = {
            world: [list(point) for point in route] for world, route in self.routes.items()
        }
        beacons = self.beaconEnabled.isChecked()

        def operation(progress):
            import atlas_glow
            import atlas_bundle

            manifest = core.build_patch(
                selected,
                client=client,
                progress=lambda value: progress(round(value * 0.7)),
                **options,
            )
            if beacons:
                atlas_glow.build_beacons(
                    client, lambda value: progress(70 + round(value * 0.25)), selected=selected
                )
            if install:
                atlas_bundle.install(client, beacons)
            progress(100)
            return manifest

        self.last_install = install
        self.start_job(operation, self.build_done, "Подготовка карт и миникарт…")

    def build_done(self, manifest):
        self.set_busy(False)
        self.refresh_install_state()
        self.status.setText(
            "Ресурсы установлены. Перезапустите игру, чтобы увидеть изменения."
            if self.last_install
            else "Отдельные файлы готовы: " + str(core.ROOT / "patch")
        )

    def restore_original(self):
        if not self.busy:
            self.start_job(
                lambda progress: core.uninstall(),
                self.restore_done,
                "Восстановление исходной карты…",
            )

    def restore_done(self, result):
        count, pending = result
        self.set_busy(False)
        self.refresh_install_state()
        if pending:
            self.status.setText("Восстановление остановлено: файлы клиента изменены извне.")
            QMessageBox.warning(
                self,
                "Карта пока не восстановлена",
                "Сохранены внешние изменения. Набор мода оставлен целым.\n\n" + "\n".join(pending),
            )
        else:
            self.status.setText(
                "Исходная карта восстановлена. Мод удалён."
                if count
                else "Мод не установлен: восстанавливать нечего."
            )

    def job_error(self, message):
        self.set_busy(False)
        self.refresh_install_state()
        self.status.setText("Операция не завершена.")
        QMessageBox.warning(self, "Не удалось выполнить", message)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.status.setText("Дождитесь завершения операции с файлами.")
            event.ignore()
            return
        self.save_settings()
        if not self.preview and not self.updates.before_close():
            event.ignore()
            return
        if self.overlay:
            self.overlay.closing_with_owner = True
            self.overlay.close()
        self.updates.closed = True
        self.updates.cancel.set()
        event.accept()
        if self.updates.applying:
            QTimer.singleShot(0, QApplication.instance().quit)


def configure_app(app):
    app.setStyle("Fusion")
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#f5f6f8"),
        (QPalette.ColorRole.Base, "#ffffff"),
        (QPalette.ColorRole.Text, "#252a31"),
        (QPalette.ColorRole.WindowText, "#252a31"),
        (QPalette.ColorRole.Button, "#ffffff"),
        (QPalette.ColorRole.ButtonText, "#252a31"),
        (QPalette.ColorRole.Highlight, "#dceafe"),
        (QPalette.ColorRole.HighlightedText, "#182f50"),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setStyleSheet(STYLE)
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for filename in ("segoeui.ttf", "segoeuib.ttf"):
        if (fonts / filename).exists():
            QFontDatabase.addApplicationFont(str(fonts / filename))
    app.setFont(QFont("Segoe UI", 10))
    icon = core.ASSETS / "atlas.ico"
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--screenshot", action="store_true")
    parser.add_argument("--screenshot-path")
    parser.add_argument("--world", choices=core.WORLDS)
    parser.add_argument("--style", choices=("classic", "original"))
    parser.add_argument("--tier", type=int)
    options, _ = parser.parse_known_args()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    configure_app(app)
    from atlas_access_ui import ensure_activation

    if not ensure_activation():
        return
    window = Window(preview=options.screenshot)
    if window.state.get("window_maximized", False) and not options.screenshot:
        window.showMaximized()
    else:
        window.show()
    if options.world:
        window.world.setCurrentIndex(window.world.findData(options.world))
    if options.style:
        window.style.setCurrentIndex(window.style.findData(options.style))
    if options.tier is not None:
        window.tier.setCurrentIndex(window.tier.findData(options.tier))
    if not options.screenshot:
        QTimer.singleShot(0, window.begin_first_run)
    if options.screenshot:

        def capture():
            window.map.fit()
            window.grab().save(
                str(
                    Path(options.screenshot_path)
                    if options.screenshot_path
                    else core.ROOT / "interface-preview.png"
                )
            )
            app.quit()

        QTimer.singleShot(1000, capture)
    sys.exit(app.exec())
