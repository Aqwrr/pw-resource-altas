"""Offline display-only patch for one verified client build; no process access.

The native map parameter lookup remains unchanged for JourneyMap, hidden M,
the detailed map and other instances. Only a visible normal M uses its own fit.
The original executable is required and must be retained by the installer.
"""

import hashlib
import struct

SUPPORTED_SHA256 = "0746df26d696e0d892aed3303b480367542c39dd1d3354d7e92716892422f3ca"
SELECTOR = 0x63FFF0
LOOKUP = 0x63D9E0
IMAGE_BASE = 0x400000


def align(value, unit):
    return (value + unit - 1) // unit * unit


class Code:
    def __init__(self, va):
        self.va = va
        self.data = bytearray()
        self.labels = {}
        self.refs = []

    def emit(self, data):
        self.data.extend(data)

    def label(self, name):
        self.labels[name] = self.va + len(self.data)

    def branch(self, opcode, target):
        self.emit(opcode)
        offset = len(self.data)
        self.emit(b"\0" * 4)
        self.refs.append((offset, target))

    def finish(self):
        for offset, target in self.refs:
            dest = self.labels[target] if isinstance(target, str) else target
            struct.pack_into("<i", self.data, offset, dest - (self.va + offset + 4))
        return bytes(self.data)


def patch(data, params):
    if hashlib.sha256(data).hexdigest() != SUPPORTED_SHA256:
        raise ValueError(
            "Версия ElementClient.exe отличается от проверенной. Поправка масштаба требует адаптации; файлы не установлены."
        )
    data = bytearray(data)
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    coff = pe + 4
    opt = coff + 20
    count = struct.unpack_from("<H", data, coff + 2)[0]
    optsize = struct.unpack_from("<H", data, coff + 16)[0]
    table = opt + optsize
    base = struct.unpack_from("<I", data, opt + 28)[0]
    section_align, file_align = struct.unpack_from("<II", data, opt + 32)
    sections = [struct.unpack_from("<8sIIIIIIHHI", data, table + i * 40) for i in range(count)]
    if base != IMAGE_BASE or table + (count + 2) * 40 > min(s[4] for s in sections):
        raise ValueError("Неожиданный формат PE")

    def offset(va):
        rva = va - base
        for s in sections:
            if s[2] <= rva < s[2] + s[3]:
                return s[4] + rva - s[2]
        raise ValueError("Адрес вне исходного исполняемого файла")

    if data[offset(SELECTOR) : offset(SELECTOR) + 5] != bytes.fromhex("55 8b ec 6a ff"):
        raise ValueError("Изменился код выбора карты")
    if data[offset(LOOKUP) : offset(LOOKUP) + 6] != bytes.fromhex("55 8b ec 83 e4 f8"):
        raise ValueError("Изменился код проекции")
    code_rva = align(max(s[2] + max(s[1], s[3]) for s in sections), section_align)
    state_rva = code_rva + section_align
    code_va = base + code_rva
    state_va = base + state_rva
    # At map texture selection, remember its mode and the normal M dialog.
    # Position independent references also work when Windows rebases the EXE.
    select = Code(code_va)
    select.emit(b"\x9c\x60\xe8\0\0\0\0\x5b")  # pushfd;pushad;call next;pop ebx
    origin = code_va + 7
    select.emit(bytes.fromhex("8b 44 24 2c"))  # original stack argument 2 (mode)
    select.emit(b"\x89\x83" + struct.pack("<i", state_va - origin))
    select.emit(b"\xc7\x83" + struct.pack("<i", state_va + 4 - origin) + b"\0" * 4)
    select.emit(b"\x8b\x83" + struct.pack("<i", 0xCAE5CC - origin))
    select.emit(b"\x85\xc0")
    select.branch(b"\x0f\x84", "done")
    select.emit(bytes.fromhex("8b 40 1c 85 c0"))
    select.branch(b"\x0f\x84", "done")
    select.emit(bytes.fromhex("8b 40 10 85 c0"))
    select.branch(b"\x0f\x84", "done")
    select.emit(bytes.fromhex("83 78 0c 01"))
    select.branch(b"\x0f\x85", "done")
    select.emit(bytes.fromhex("8b 48 08 85 c9"))
    select.branch(b"\x0f\x84", "done")
    select.emit(b"\x8d\x93" + struct.pack("<i", 0xBA70B8 - origin))  # Win_WorldMap
    select.emit(bytes.fromhex("52 8b 01 ff 50 38"))  # UI manager GetDialog
    select.emit(b"\x89\x83" + struct.pack("<i", state_va + 4 - origin))
    select.label("done")
    select.emit(b"\x61\x9d")
    select.emit(bytes.fromhex("55 8b ec 6a ff"))
    select.branch(b"\xe9", SELECTOR + 5)
    select_bytes = select.finish()
    # Override only the output record of the existing projection lookup.
    # All original projection arithmetic, hit testing and teleport IDs remain.
    lookup_va = align(code_va + len(select_bytes), 16)
    lookup = Code(lookup_va)
    lookup.emit(b"\x52\xe8\0\0\0\0\x5a")  # preserve edx;position independent base
    origin = lookup_va + 6
    lookup.emit(b"\x83\xba" + struct.pack("<i", state_va - origin) + b"\0")
    lookup.branch(b"\x0f\x85", "native")
    lookup.emit(bytes.fromhex("83 7c 24 08 01"))
    lookup.branch(b"\x0f\x85", "native")
    lookup.emit(b"\x8b\x82" + struct.pack("<i", state_va + 4 - origin))
    lookup.emit(b"\x85\xc0")
    lookup.branch(b"\x0f\x84", "native")
    lookup.emit(bytes.fromhex("80 b8 90 00 00 00 00"))
    lookup.branch(b"\x0f\x84", "native")  # AUIDialog::IsShow
    lookup.emit(bytes.fromhex("8b 44 24 0c"))  # output record
    values = [
        struct.pack("<I", params[k]) if k in ("a", "b", "w", "h") else struct.pack("<f", params[k])
        for k in ("a", "b", "ox", "oy", "w", "h")
    ]
    for i, value in enumerate(values):
        lookup.emit(b"\xc7\x40" + bytes([i * 4]) + value)
    lookup.emit(b"\x5a\xc2\x08\0")
    lookup.label("native")
    lookup.emit(b"\x5a" + bytes.fromhex("55 8b ec 83 e4 f8"))
    lookup.branch(b"\xe9", LOOKUP + 6)
    lookup_bytes = lookup.finish()
    payload = select_bytes + b"\xcc" * (lookup_va - code_va - len(select_bytes)) + lookup_bytes
    if len(payload) > section_align:
        raise ValueError("Поправка не помещается в секцию")
    code_raw = align(len(data), file_align)
    code_size = align(len(payload), file_align)
    state_raw = code_raw + code_size
    data.extend(b"\0" * (state_raw + file_align - len(data)))
    data[code_raw : code_raw + len(payload)] = payload
    struct.pack_into("<II", data, state_raw, 0xFFFFFFFF, 0)
    struct.pack_into(
        "<8sIIIIIIHHI",
        data,
        table + count * 40,
        b".pwmap\0\0",
        len(payload),
        code_rva,
        code_size,
        code_raw,
        0,
        0,
        0,
        0,
        0x60000020,
    )
    struct.pack_into(
        "<8sIIIIIIHHI",
        data,
        table + (count + 1) * 40,
        b".pwstate",
        8,
        state_rva,
        file_align,
        state_raw,
        0,
        0,
        0,
        0,
        0xC0000040,
    )
    struct.pack_into("<H", data, coff + 2, count + 2)
    struct.pack_into("<I", data, opt + 4, struct.unpack_from("<I", data, opt + 4)[0] + code_size)
    struct.pack_into("<I", data, opt + 8, struct.unpack_from("<I", data, opt + 8)[0] + file_align)
    struct.pack_into("<I", data, opt + 56, align(state_rva + 8, section_align))
    struct.pack_into("<I", data, opt + 64, 0)  # unsigned image; loader accepts checksum zero
    for va, dest, length in ((SELECTOR, code_va, 5), (LOOKUP, lookup_va, 6)):
        pos = offset(va)
        data[pos : pos + length] = (
            b"\xe9" + struct.pack("<i", dest - va - 5) + b"\x90" * (length - 5)
        )
    return bytes(data), {
        "native_sha256": SUPPORTED_SHA256,
        "code_rva": code_rva,
        "state_rva": state_rva,
        "lookup_rva": lookup_va - base,
        "code_size": len(payload),
        "projection": params,
        "changed_entry_bytes": 11,
        "changes": "Only normal visible world-map display parameters; native teleport projection is unchanged.",
    }
