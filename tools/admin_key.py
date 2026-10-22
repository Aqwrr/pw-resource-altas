"""Create the owner's private key and commit only its one-way verifier."""

from pathlib import Path
import base64
import hashlib
import secrets

PROJECT = Path(__file__).resolve().parents[1]
PRIVATE = PROJECT / ".private/admin-key.txt"
POLICY = PROJECT / "src/atlas_access_policy.py"


def create():
    if PRIVATE.exists() or POLICY.exists():
        raise ValueError("Ключ уже создан. Автоматическая замена отключена.")
    characters = base64.b32encode(secrets.token_bytes(20)).decode("ascii")
    key = "PWA-ADMIN-" + "-".join(characters[i : i + 4] for i in range(0, len(characters), 4))
    salt = secrets.token_hex(16)
    normalized = key.replace("-", "")
    digest = hashlib.scrypt(
        normalized.encode("ascii"), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32
    ).hex()
    PRIVATE.parent.mkdir(exist_ok=True)
    with PRIVATE.open("x", encoding="utf-8") as output:
        output.write(key + "\n")
    POLICY.write_text(
        '"""Public verifier only. The access key is never bundled."""\n\nSALT = '
        + repr(salt)
        + "\nDIGEST = "
        + repr(digest)
        + "\n",
        encoding="utf-8",
    )
    print("Ключ создан. Локальный файл: " + str(PRIVATE))


if __name__ == "__main__":
    create()
