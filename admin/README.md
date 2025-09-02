## Admin (Streamlit)

Lightweight web UI to manage files via the FastAPI backend.

### Install

```bash
pip install -r requirements.txt
```

This uses the same venv as the API.

### Run

```bash
API_BASE=http://127.0.0.1:8000 streamlit run admin/app.py
```

Environment:

- `API_BASE` (default `http://127.0.0.1:8000`)

Features:

- Upload and encrypt a file
- Browse files, view metadata
- Download encrypted bytes or decrypted file (optional key override)
- Delete file

