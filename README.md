## AES-256-CBC File Encryption API (FastAPI)

This service accepts file uploads, encrypts them with AES-256-CBC, and stores the encrypted file along with metadata.

### Features

- AES-256-CBC with PKCS7 padding and per-file random IV
- Integrity via HMAC-SHA256 over `IV || ciphertext`
- HKDF key derivation (separate encryption and MAC keys from a master key)
- Sidecar metadata (`.json`) including IV, HMAC, sizes, created time, and key fingerprint
- Endpoints to upload, list, fetch metadata, download encrypted bytes, decrypt, and delete
- `.env` support to keep configuration stable across restarts
 - Streaming encryption/decryption for large files

### Quickstart

1) Create and activate a virtualenv (optional but recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2) Install dependencies:

```bash
pip install -r requirements.txt
```

3) Generate a 32-byte encryption key and export it (or save to .env):

```bash
python scripts/generate_key.py
# Example output: bP9wZ5uQ5CkL3nBV2SFX3GxjO_8dM8YokFvO6H5m7tQ=
export FILE_ENCRYPTION_KEY="bP9wZ5uQ5CkL3nBV2SFX3GxjO_8dM8YokFvO6H5m7tQ="

# Optional: persist key in .env so decrypt works across restarts
cat > .env <<EOF
FILE_ENCRYPTION_KEY=bP9wZ5uQ5CkL3nBV2SFX3GxjO_8dM8YokFvO6H5m7tQ=
ENCRYPTED_STORAGE_DIR=$(pwd)/data/encrypted
EOF
```

4) (Optional) Choose storage directory for encrypted files:

```bash
export ENCRYPTED_STORAGE_DIR="/absolute/path/to/data/encrypted"
```

5) Run the server:

```bash
# If using virtualenv:
uvicorn app.main:app --reload

# Or absolute uvicorn binary if PATH doesn’t include venv:
$(pwd)/.venv/bin/uvicorn app.main:app --reload
```

### Configuration

Environment variables (set in shell or `.env`):

- `FILE_ENCRYPTION_KEY` (required): 32-byte key (base64/hex/raw). Used to derive AES and HMAC keys via HKDF.
- `ENCRYPTED_STORAGE_DIR` (optional): path to store `.enc` and `.json`. Default: `$(pwd)/data/encrypted`.

Keep the key stable to decrypt existing files. Rotating the key prevents decrypting older files unless you re-encrypt.

### API

- POST `/encrypt`
  - Form-data:
    - `file`: the file to upload (required)
    - `key`: optional base64 or hex-encoded master key (overrides env)
  - Response JSON includes the stored file id, paths, and metadata.

- GET `/files`
  - Lists stored encrypted files (basic metadata only)

- GET `/files/{id}`
  - Returns metadata for a stored file id

- GET `/files/{id}/download`
  - Downloads the encrypted bytes (`.enc`)

- POST `/files/{id}/decrypt`
  - Form-data:
    - `key`: optional base64/hex key; uses env `FILE_ENCRYPTION_KEY` if omitted
  - Returns the decrypted file as a download (original filename when available)

- DELETE `/files/{id}`
  - Deletes both encrypted file and its metadata

#### Examples

```bash
# Upload and encrypt using env key
curl -s -X POST -F "file=@/path/to/file" http://127.0.0.1:8000/encrypt

# List files
curl -s http://127.0.0.1:8000/files | jq

# Pick an id
ID=REPLACE_WITH_ID

# Get metadata
curl -s http://127.0.0.1:8000/files/$ID | jq

# Download encrypted bytes
curl -s -o file.enc http://127.0.0.1:8000/files/$ID/download

# Decrypt (POST!) using the server env key
curl -s -X POST -o file.dec http://127.0.0.1:8000/files/$ID/decrypt

# Decrypt with an explicit key override (base64/hex)
curl -s -X POST -F key=$(python scripts/generate_key.py) -o file.dec \
  http://127.0.0.1:8000/files/$ID/decrypt

# Delete when done
curl -s -X DELETE http://127.0.0.1:8000/files/$ID
```

### Notes

- Uses AES-256-CBC with PKCS7 padding. A fresh random IV is generated per file.
- An HMAC-SHA256 tag is computed over `IV || ciphertext` using a key derived from the master key for integrity.
- Metadata is stored alongside the encrypted file in a `.json` file.
- The service creates the storage directory if it does not exist.

### Internals

- Master key parsing tries base64, then hex, else raw string bytes; must be exactly 32 bytes.
- HKDF-SHA256 expands the master key to 64 bytes: first 32 bytes for AES, next 32 for HMAC.
- HMAC authenticates `IV || ciphertext`. Decrypt verifies HMAC before unpadding and returning data.
- Metadata includes `key_fp` (fingerprint) to detect wrong keys early before HMAC verify.

### Troubleshooting

- "ModuleNotFoundError: No module named 'app'": run uvicorn via venv or from repo root:
  - `$(pwd)/.venv/bin/uvicorn app.main:app --reload`
- "Decrypt failed: Signature did not match digest.": the key changed; use the original `FILE_ENCRYPTION_KEY`.
- "Wrong key for this file (fingerprint mismatch)": provided key does not match the file's key fingerprint.
 - Large files: encryption/decryption is streaming; if uploads fail, check client limits and Uvicorn/NGINX size limits (e.g., set `--limit-max-requests` in proxies or client-side `--max-time`).

### Security notes

- Keep `FILE_ENCRYPTION_KEY` secret (use a secrets manager/KMS in production).
- CBC with random IV and PKCS7 is safe when combined with HMAC (encrypt-then-MAC).
- Consider streaming uploads and AES-GCM for very large files or if AEAD is preferred.

# file-server
