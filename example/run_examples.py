import json
import os
import sys
from pathlib import Path
from typing import List

import requests


API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
INPUT_DIR = Path(os.environ.get("EXAMPLE_INPUT", "example/input"))
OUTPUT_DIR = Path(os.environ.get("EXAMPLE_OUTPUT", "example/output"))
PREFIX = os.environ.get("EXAMPLE_PREFIX", "bilgee")


def find_input_files(prefix: str) -> List[Path]:
    files: List[Path] = []
    for p in sorted(INPUT_DIR.iterdir()):
        if p.is_file() and p.name.startswith(prefix):
            files.append(p)
    return files


def ensure_output() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def encrypt_file(path: Path) -> dict:
    with path.open("rb") as f:
        resp = requests.post(f"{API_BASE}/encrypt", files={"file": (path.name, f)})
    resp.raise_for_status()
    return resp.json()


def decrypt_to_file(file_id: str, out_path: Path) -> None:
    with requests.post(f"{API_BASE}/files/{file_id}/decrypt", stream=True) as r:
        r.raise_for_status()
        with out_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)


def main() -> int:
    ensure_output()
    files = find_input_files(PREFIX)
    if not files:
        print(f"No files found in {INPUT_DIR} with prefix '{PREFIX}'")
        return 1

    for path in files:
        print(f"Processing: {path}")
        meta = encrypt_file(path)
        file_id = meta["id"]
        # Save metadata for reference
        (OUTPUT_DIR / f"{path.name}.encrypt.json").write_text(json.dumps(meta, indent=2))
        # Decrypt to output folder
        out_path = OUTPUT_DIR / f"{path.stem}.roundtrip{path.suffix}"
        decrypt_to_file(file_id, out_path)
        print(f"  -> decrypted to {out_path}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


