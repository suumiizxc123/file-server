import base64
import os
from typing import Tuple

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, hmac, padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8")


def urlsafe_b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data.encode("utf-8"))


def derive_encryption_and_mac_keys(master_key: bytes) -> Tuple[bytes, bytes]:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=64,
        salt=None,
        info=b"file-server:aes256cbc+mac",
        backend=default_backend(),
    )
    okm = hkdf.derive(master_key)
    return okm[:32], okm[32:64]


def encrypt_bytes_aes256_cbc(plaintext: bytes, enc_key: bytes) -> Tuple[bytes, bytes]:
    if len(enc_key) != 32:
        raise ValueError("Encryption key must be 32 bytes")
    iv = os.urandom(16)
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    cipher = Cipher(algorithms.AES(enc_key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return iv, ciphertext


def decrypt_bytes_aes256_cbc(ciphertext: bytes, enc_key: bytes, iv: bytes) -> bytes:
    if len(enc_key) != 32:
        raise ValueError("Encryption key must be 32 bytes")
    cipher = Cipher(algorithms.AES(enc_key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded) + unpadder.finalize()


def hmac_sha256(mac_key: bytes, *parts: bytes) -> bytes:
    if len(mac_key) == 0:
        raise ValueError("MAC key must not be empty")
    h = hmac.HMAC(mac_key, hashes.SHA256(), backend=default_backend())
    for p in parts:
        h.update(p)
    return h.finalize()


def verify_hmac_sha256(mac_key: bytes, tag: bytes, *parts: bytes) -> None:
    h = hmac.HMAC(mac_key, hashes.SHA256(), backend=default_backend())
    for p in parts:
        h.update(p)
    h.verify(tag)


def key_fingerprint(master_key: bytes) -> str:
    enc_key, mac_key = derive_encryption_and_mac_keys(master_key)
    tag = hmac_sha256(mac_key, b"file-server:key-fingerprint:v1")
    return tag.hex()[:16]


def encrypt_fileobj_to_path(
    in_file,
    out_path: str,
    enc_key: bytes,
    mac_key: bytes,
    chunk_size: int = 1024 * 64,
) -> Tuple[bytes, int, int, bytes]:
    """Encrypts from file-like to out_path using AES-256-CBC with PKCS7, streaming.

    Returns (iv, bytes_in, bytes_out, tag).
    """
    if len(enc_key) != 32:
        raise ValueError("Encryption key must be 32 bytes")
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(enc_key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padder = padding.PKCS7(128).padder()
    h = hmac.HMAC(mac_key, hashes.SHA256(), backend=default_backend())
    h.update(iv)

    total_in = 0
    total_out = 0
    with open(out_path, "wb") as out_f:
        while True:
            chunk = in_file.read(chunk_size)
            if not chunk:
                break
            total_in += len(chunk)
            padded = padder.update(chunk)
            if padded:
                ct = encryptor.update(padded)
                if ct:
                    h.update(ct)
                    out_f.write(ct)
                    total_out += len(ct)
        # finalize padding and encryption
        padded_final = padder.finalize()
        ct_final = encryptor.update(padded_final) + encryptor.finalize()
        if ct_final:
            h.update(ct_final)
            out_f.write(ct_final)
            total_out += len(ct_final)

    tag = h.finalize()
    return iv, total_in, total_out, tag


def decrypt_file_to_path(
    enc_path: str,
    out_path: str,
    enc_key: bytes,
    mac_key: bytes,
    iv: bytes,
    expected_tag: bytes,
    chunk_size: int = 1024 * 64,
) -> Tuple[int, int]:
    """Decrypts ciphertext at enc_path to out_path, verifying HMAC while streaming.

    Raises ValueError if HMAC does not verify. Returns (bytes_in, bytes_out).
    """
    if len(enc_key) != 32:
        raise ValueError("Encryption key must be 32 bytes")
    cipher = Cipher(algorithms.AES(enc_key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    unpadder = padding.PKCS7(128).unpadder()
    h = hmac.HMAC(mac_key, hashes.SHA256(), backend=default_backend())
    h.update(iv)

    total_in = 0
    total_out = 0
    try:
        with open(enc_path, "rb") as in_f, open(out_path, "wb") as out_f:
            while True:
                chunk = in_f.read(chunk_size)
                if not chunk:
                    break
                total_in += len(chunk)
                h.update(chunk)
                padded_pt = decryptor.update(chunk)
                if padded_pt:
                    pt = unpadder.update(padded_pt)
                    if pt:
                        out_f.write(pt)
                        total_out += len(pt)
            # finalize decrypt and unpad
            padded_final = decryptor.finalize()
            if padded_final:
                pt_final = unpadder.update(padded_final)
                if pt_final:
                    out_f.write(pt_final)
                    total_out += len(pt_final)
            unpadded_tail = unpadder.finalize()
            if unpadded_tail:
                out_f.write(unpadded_tail)
                total_out += len(unpadded_tail)

        # Verify HMAC after full read
        h.verify(expected_tag)
    except Exception:
        # Clean up partial output if verification fails or any error
        try:
            if os.path.exists(out_path):
                os.remove(out_path)
        except Exception:
            pass
        raise

    return total_in, total_out


