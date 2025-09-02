import datetime as dt
import json
import os
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, FileResponse

from ..config import ensure_storage_dir, get_master_key
from ..crypto import (
    urlsafe_b64encode,
    urlsafe_b64decode,
    derive_encryption_and_mac_keys,
    key_fingerprint,
    encrypt_fileobj_to_path,
    decrypt_file_to_path,
)


router = APIRouter()


@router.post("/encrypt")
async def encrypt_file(file: UploadFile = File(...), key: Optional[str] = Form(None)):
    try:
        master_key = get_master_key(key)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid key: {e}")

    enc_key, mac_key = derive_encryption_and_mac_keys(master_key)

    storage_dir = ensure_storage_dir()
    file_id = uuid4().hex
    enc_path = os.path.join(storage_dir, f"{file_id}.enc")
    meta_path = os.path.join(storage_dir, f"{file_id}.json")

    # Stream encrypt directly from the UploadFile to disk to support large binaries
    try:
        # Reset file pointer if needed
        try:
            await file.seek(0)
        except Exception:
            pass
        iv, bytes_in, bytes_out, tag = encrypt_fileobj_to_path(file.file, enc_path, enc_key, mac_key)
        metadata = {
            "id": file_id,
            "original_filename": file.filename,
            "content_type": file.content_type,
            "bytes_in": int(bytes_in),
            "bytes_out": int(bytes_out),
            "iv_b64": urlsafe_b64encode(iv),
            "hmac_b64": urlsafe_b64encode(tag),
            "created_at": dt.datetime.utcnow().isoformat() + "Z",
            "enc_path": enc_path,
            "key_fp": key_fingerprint(master_key),
        }
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        try:
            if os.path.exists(enc_path):
                os.remove(enc_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to store encrypted file: {e}")

    return JSONResponse(
        status_code=200,
        content={
            "id": file_id,
            "message": "File encrypted and stored",
            "enc_path": enc_path,
            "meta_path": meta_path,
            "bytes_in": int(bytes_in),
            "bytes_out": int(bytes_out),
        },
    )


@router.get("/files")
def list_files():
    storage_dir = ensure_storage_dir()
    items = []
    for name in os.listdir(storage_dir):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(storage_dir, name), "r", encoding="utf-8") as f:
                meta = json.load(f)
                items.append({
                    "id": meta.get("id"),
                    "original_filename": meta.get("original_filename"),
                    "bytes_out": meta.get("bytes_out"),
                    "created_at": meta.get("created_at"),
                })
        except Exception:
            continue
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"files": items}


@router.get("/files/{file_id}")
def get_metadata(file_id: str):
    storage_dir = ensure_storage_dir()
    meta_path = os.path.join(storage_dir, f"{file_id}.json")
    if not os.path.exists(meta_path):
        raise HTTPException(status_code=404, detail="Not found")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    return meta


@router.get("/files/{file_id}/download")
def download_encrypted(file_id: str):
    storage_dir = ensure_storage_dir()
    enc_path = os.path.join(storage_dir, f"{file_id}.enc")
    if not os.path.exists(enc_path):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(enc_path, media_type="application/octet-stream", filename=f"{file_id}.enc")


@router.post("/files/{file_id}/decrypt")
def decrypt_by_id(file_id: str, key: Optional[str] = Form(None)):
    try:
        master_key = get_master_key(key)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid key: {e}")

    enc_key, mac_key = derive_encryption_and_mac_keys(master_key)
    storage_dir = ensure_storage_dir()
    enc_path = os.path.join(storage_dir, f"{file_id}.enc")
    meta_path = os.path.join(storage_dir, f"{file_id}.json")
    if not (os.path.exists(enc_path) and os.path.exists(meta_path)):
        raise HTTPException(status_code=404, detail="Not found")

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        expected_fp = meta.get("key_fp")
        if expected_fp is not None:
            provided_fp = key_fingerprint(master_key)
            if provided_fp != expected_fp:
                raise HTTPException(status_code=400, detail="Wrong key for this file (fingerprint mismatch)")
        iv = urlsafe_b64decode(meta["iv_b64"])
        tag = urlsafe_b64decode(meta["hmac_b64"])
        filename = meta.get("original_filename") or f"{file_id}.bin"
        tmp_out = os.path.join(storage_dir, f"{file_id}.dec.tmp")
        # Stream verify+decrypt from disk to disk
        decrypt_file_to_path(enc_path, tmp_out, enc_key, mac_key, iv, tag)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Decrypt failed: {e}")

    return FileResponse(tmp_out, media_type="application/octet-stream", filename=filename)


@router.delete("/files/{file_id}")
def delete_by_id(file_id: str):
    storage_dir = ensure_storage_dir()
    enc_path = os.path.join(storage_dir, f"{file_id}.enc")
    meta_path = os.path.join(storage_dir, f"{file_id}.json")
    removed = {"enc": False, "meta": False}
    if os.path.exists(enc_path):
        try:
            os.remove(enc_path)
            removed["enc"] = True
        except Exception:
            pass
    if os.path.exists(meta_path):
        try:
            os.remove(meta_path)
            removed["meta"] = True
        except Exception:
            pass
    if not any(removed.values()):
        raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": removed}


