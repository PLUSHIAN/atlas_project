"""Protege o histórico persistido em artefatos do GitHub Actions com criptografia autenticada."""
import base64
import hashlib
import os
from pathlib import Path
import secrets
import sys
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"ATLASSTATE1"

def key_from_secret(secret: str, salt: bytes) -> bytes:
    if len(secret) < 32:
        raise ValueError("ATLAS_STATE_KEY deve ter pelo menos 32 caracteres aleatórios")
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, 300_000, dklen=32)

def encrypt(source: Path, target: Path, secret: str):
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    data = MAGIC + salt + nonce + AESGCM(key_from_secret(secret, salt)).encrypt(nonce, source.read_bytes(), MAGIC)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)

def decrypt(source: Path, target: Path, secret: str):
    data = source.read_bytes()
    if len(data) < len(MAGIC) + 16 + 12 + 16 or not data.startswith(MAGIC):
        raise ValueError("Artefato do ATLAS inválido")
    salt, nonce = data[len(MAGIC):len(MAGIC)+16], data[len(MAGIC)+16:len(MAGIC)+28]
    content = AESGCM(key_from_secret(secret, salt)).decrypt(nonce, data[len(MAGIC)+28:], MAGIC)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(content)
    tmp.replace(target)

if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in ("encrypt", "decrypt"):
        raise SystemExit("Uso: python -m backend.app.state_artifact encrypt|decrypt entrada saída")
    token = os.environ.get("ATLAS_STATE_KEY", "")
    if not token:
        raise SystemExit("ATLAS_STATE_KEY não configurado")
    src, dest = Path(sys.argv[2]), Path(sys.argv[3])
    if sys.argv[1] == "encrypt":
        encrypt(src, dest, token)
    else:
        decrypt(src, dest, token)
    print("Estado do ATLAS processado com segurança")
