import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import HTTPException

from .crypto import urlsafe_b64decode


load_dotenv()


def parse_master_key(value: str) -> bytes:
    if value is None or value == "":
        raise ValueError("Empty key provided")

    try:
        decoded = urlsafe_b64decode(value)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass

    try:
        decoded = bytes.fromhex(value)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass

    raw = value.encode("utf-8")
    if len(raw) == 32:
        return raw

    raise ValueError("Master key must be 32 bytes (base64, hex, or raw 32-char)")


def get_master_key(override_key: Optional[str]) -> bytes:
    if override_key:
        return parse_master_key(override_key)
    env_val = os.getenv("FILE_ENCRYPTION_KEY")
    if not env_val:
        raise HTTPException(status_code=500, detail="FILE_ENCRYPTION_KEY is not set")
    try:
        return parse_master_key(env_val)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))


def ensure_storage_dir() -> str:
    storage_dir = os.getenv(
        "ENCRYPTED_STORAGE_DIR",
        os.path.join(os.getcwd(), "data", "encrypted"),
    )
    os.makedirs(storage_dir, exist_ok=True)
    return storage_dir


