"""Short, built-in help. No file associations or external applications."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
)

import atlas_core as core

PAGES = {
    "start": (
        "Начало",
        """
<h3>Установить ресурсы</h3>
<p>Выберите материалы и травы. Закройте игру, нажмите <b>«Установить выбранные ресурсы»</b> и запустите клиент.</p>
<p>Быстрый набор заменяет галочки. <b>«Показать все»</b> убирает поиск и фильтры списка. <b>«Сбросить выбор»</b> снимает все галочки.</p>
<p>Свои наборы — в <b>«Мои наборы…»</b>. Другую папку клиента можно указать кнопкой <b>«Папка игры…»</b>.</p>
<p>Чтобы удалить мод, закройте игру и нажмите <b>«Вернуть исходную карту»</b>. Не удаляйте резервные копии.</p>""",
    ),
    "map": (
        "Карта",
        """
<h3>Управление картой</h3>
<p>Колесо — масштаб. Перетаскивание — перемещение.<br>
Клик — скопировать координаты.<br>
Shift+клик — добавить точку в круг.<br>
Правый клик — убрать последнюю точку.</p>
<p><b>«Построить круг»</b> соединяет выбранные ресурсы в видимой области: до 120 точек. Рельеф не учитывается. CSV сохраняет порядок обхода.</p>
<p><b>«Карта поверх игры»</b> открывает отдельное окно. Двигайте его за заголовок и растягивайте за края. Игра должна быть в оконном или безрамочном режиме.</p>
<p>Метки показывают места появления. Собранные ресурсы с карты не исчезают.</p>""",
    ),
    "beacons": (
        "Маяки",
        """
<h3>Подсветка в мире</h3>
<p>Включите <b>«Маяки выбранных ресурсов»</b> и установите набор при закрытой игре.</p>
<p>Маяки получают только отмеченные материалы и травы. Маяк исчезает вместе с собранным ресурсом.</p>
<p>Чтобы убрать подсветку, снимите галочку маяков и снова установите набор. Метки на карте останутся.</p>
<p>После изменения выбора нужна повторная установка и перезапуск игры.</p>""",
    ),
    "updates": (
        "Обновления",
        """
<h3>Обновление атласа</h3>
<p>Откройте <b>«Справка → Обновления»</b>. Если есть новая версия, скачайте её и нажмите <b>«Установить и перезапустить»</b>.</p>
<p>Автообновление можно включить там же: пакет загрузится в фоне и установится при закрытии атласа.</p>
<p>Настройки, свои наборы и резервные копии сохраняются. Файлы игры обновляются отдельно — кнопкой установки ресурсов.</p>""",
    ),
    "about": (
        "О программе",
        f"""
<h3>PW Resource Atlas {core.VERSION}</h3>
<p>Для обычного клиента Comeback PW 1.3.6.<br>49 видов материалов и трав, маршруты и маяки.</p>
<p>Comeback 1.4.6 и тестовые клиенты пока не поддерживаются.</p>
<p>Исходники и релизы: github.com/Aqwrr/pw-resource-altas</p>
<p>Программа использует PySide6 и Pillow. Тексты лицензий находятся в папке third-party-licenses.</p>""",
    ),
}


class HelpDialog(QDialog):
    def __init__(self, parent=None, topic="start"):
        super().__init__(parent)
        self.setWindowTitle("Справка")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.resize(660, 460)
        self.setMinimumSize(540, 360)
        box = QVBoxLayout(self)
        box.setContentsMargins(18, 18, 18, 18)
        self.tabs = QTabWidget()
        for key, (title, body) in PAGES.items():
            page = QTextBrowser()
            page.setOpenExternalLinks(False)
            page.setOpenLinks(False)
            page.document().setDocumentMargin(16)
            page.setHtml(body)
            self.tabs.addTab(page, title)
            if key == topic:
                self.tabs.setCurrentWidget(page)
        box.addWidget(self.tabs, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        box.addLayout(row)
