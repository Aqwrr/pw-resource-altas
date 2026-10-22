"""Scale the existing minimap layout while preserving commands and artwork."""

import math
import re
import xml.etree.ElementTree as ET

SCALES = (1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5)


def xml_text(data):
    if data.startswith(b"\xff\xfe"):
        encoding = "utf-16le"
    elif data.startswith(b"\xfe\xff"):
        encoding = "utf-16be"
    else:
        try:
            data.decode("utf-8")
            encoding = "utf-8"
        except UnicodeDecodeError:
            encoding = "gb18030"
    return data.decode(encoding), encoding


def viewport(data):
    text, _ = xml_text(data)
    root = ET.fromstring(text.lstrip("\ufeff"))
    if root.tag != "DIALOG" or root.get("Name") != "Win_Map":
        raise ValueError("Неожиданный файл интерфейса миникарты")
    maps = [e for e in root if e.get("Name") == "Hide_2"]
    if len(maps) != 1:
        raise ValueError("Не найдена единственная область миникарты Hide_2")
    area = maps[0]
    return int(area.get("Width", "0")), int(area.get("Height", "0"))


def scale_layout(data, scale=1.5):
    scale = float(scale)
    if scale not in SCALES:
        raise ValueError("Размер миникарты: от 100% до 250% с шагом 25%.")
    width, height = viewport(data)
    if not (64 <= width <= 512 and 64 <= height <= 512):
        raise ValueError("Размер исходной миникарты отличается от ожидаемого")
    if scale == 1:
        return data
    if max(width, height) * scale > 512:
        raise ValueError("Область миникарты превышает 512 пикселей.")
    text, encoding = xml_text(data)

    def tag(match):
        is_root = match[0].startswith("<DIALOG")

        def attribute(m):
            key, value = m[1], int(m[2])
            if key in ("x", "y") and (is_root or value < -1000):
                return m[0]
            return key + '="' + str(math.floor(value * scale + 0.5)) + '"'

        return re.sub(r'\b(x|y|Width|Height)="(-?\d+)"', attribute, match[0])

    text = re.sub(
        r"<(?:DIALOG|IMAGEPICTURE|EDIT|LABEL|STILLIMAGEBUTTON|CHECK|TEXT)\b[^>]*>", tag, text
    )
    result = text.encode(encoding)
    if viewport(result) != (math.floor(width * scale + 0.5), math.floor(height * scale + 0.5)):
        raise ValueError("Не удалось увеличить область миникарты")
    return result
