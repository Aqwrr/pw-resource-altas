"""Offline key verification and Windows-protected activation storage."""

from pathlib import Path
from ctypes import wintypes
import ctypes
import hashlib
import os
import re
import secrets

import atlas_access_policy as policy

ACTIVATION_FILE = "activation.dat"
MAGIC = b"PWA-ACT1\0"
ENTROPY = b"PW Resource Atlas activation v1"


class ActivationRequired(ValueError):
    pass


def normalize_key(key):
    if not isinstance(key, str) or len(key) > 256:
        return ""
    text = re.sub(r"[\s-]", "", key).upper()
    return text if re.fullmatch(r"PWAADMIN[A-Z2-7]{32}", text) else ""


def key_digest(key, salt):
    return hashlib.scrypt(
        key.encode("ascii"), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32
    ).hex()


def valid_key(key):
    normalized = normalize_key(key)
    return bool(normalized) and secrets.compare_digest(
        key_digest(normalized, policy.SALT), policy.DIGEST
    )


class DataBlob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    if os.name != "nt":
        raise OSError("Активация поддерживается в Windows.")
    incoming_buffer = ctypes.create_string_buffer(data)
    entropy_buffer = ctypes.create_string_buffer(ENTROPY)
    incoming = DataBlob(len(data), ctypes.cast(incoming_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    entropy = DataBlob(len(ENTROPY), ctypes.cast(entropy_buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = DataBlob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [
        ctypes.POINTER(DataBlob),
        ctypes.c_void_p if decrypt else wintypes.LPCWSTR,
        ctypes.POINTER(DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DataBlob),
    ]
    function.restype = wintypes.BOOL
    description = None if decrypt else "PW Resource Atlas activation"
    if not function(
        ctypes.byref(incoming),
        description,
        ctypes.byref(entropy),
        None,
        None,
        1,
        ctypes.byref(outgoing),
    ):
        raise OSError(
            "Не удалось прочитать активацию Windows."
            if decrypt
            else "Не удалось сохранить активацию Windows."
        )
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        kernel.LocalFree(ctypes.cast(outgoing.data, ctypes.c_void_p))


def is_activated(root):
    try:
        with (Path(root) / ACTIVATION_FILE).open("rb") as stored:
            data = stored.read(65537)
        if len(data) > 65536 or not data.startswith(MAGIC):
            return False
        return valid_key(protect(data[len(MAGIC) :], decrypt=True).decode("ascii"))
    except (OSError, ValueError, UnicodeError):
        return False


def activate(root, key):
    if not valid_key(key):
        raise ActivationRequired("Ключ не подошёл. Проверьте код и попробуйте ещё раз.")
    data = MAGIC + protect(normalize_key(key).encode("ascii"))
    path = Path(root) / ACTIVATION_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def require_activated(root):
    if not is_activated(root):
        raise ActivationRequired("Для работы атласа нужен ключ доступа.")
