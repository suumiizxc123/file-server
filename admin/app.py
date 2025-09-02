import io
import json
import os
import mimetypes
from typing import Optional, Tuple

import requests
import streamlit as st


def get_api_base() -> str:
    val = st.session_state.get("api_base") or os.environ.get("API_BASE", "http://127.0.0.1:8000")
    return val.rstrip("/")


def set_api_base(value: str) -> None:
    # Safe set only if not yet created by a widget
    if "api_base" not in st.session_state:
        st.session_state.api_base = value.rstrip("/")


def api_get(path: str) -> requests.Response:
    return requests.get(f"{get_api_base()}{path}", timeout=60)


def api_post(path: str, *, files=None, data=None, stream=False) -> requests.Response:
    return requests.post(f"{get_api_base()}{path}", files=files, data=data, stream=stream, timeout=600)


def api_delete(path: str) -> requests.Response:
    return requests.delete(f"{get_api_base()}{path}", timeout=60)


def try_json(resp: requests.Response) -> str:
    try:
        return json.dumps(resp.json(), indent=2)
    except Exception:
        return resp.text


def upload_encrypt_ui():
    st.subheader("Upload and Encrypt")
    with st.form("upload_form", clear_on_submit=False):
        uploaded = st.file_uploader("Choose a file to encrypt", type=None)
        override_key = st.text_input("Optional key override (base64/hex/raw 32)")
        submitted = st.form_submit_button("Encrypt")
    if submitted:
        if not uploaded:
            st.warning("Please choose a file first.")
            return
        files = {"file": (uploaded.name, uploaded.getvalue())}
        data = {"key": override_key} if override_key else None
        with st.spinner("Encrypting..."):
            resp = api_post("/encrypt", files=files, data=data)
        if resp.ok:
            st.success("Encrypted successfully")
            st.code(try_json(resp), language="json")
        else:
            st.error(f"Encrypt failed: {resp.status_code}")
            st.code(try_json(resp), language="json")


def list_files() -> list:
    resp = api_get("/files")
    resp.raise_for_status()
    return resp.json().get("files", [])


def get_metadata(file_id: str) -> dict:
    resp = api_get(f"/files/{file_id}")
    resp.raise_for_status()
    return resp.json()


def fetch_download(file_id: str) -> Tuple[bytes, str]:
    resp = api_get(f"/files/{file_id}/download")
    resp.raise_for_status()
    return resp.content, f"{file_id}.enc"


def fetch_decrypt(file_id: str, override_key: Optional[str]) -> Tuple[bytes, str]:
    data = {"key": override_key} if override_key else None
    resp = api_post(f"/files/{file_id}/decrypt", data=data, stream=True)
    resp.raise_for_status()
    content = b"".join(resp.iter_content(1024 * 64))
    # Try to use original filename
    try:
        meta = get_metadata(file_id)
        fname = meta.get("original_filename") or f"{file_id}.bin"
    except Exception:
        fname = f"{file_id}.bin"
    return content, fname


def files_admin_ui():
    st.subheader("Files")
    try:
        items = list_files()
    except Exception as e:
        st.error(f"Failed to fetch files: {e}")
        return

    # Filters
    colf1, colf2 = st.columns([2, 1])
    with colf1:
        query = st.text_input("Filter by name or id contains", "")
    with colf2:
        limit = st.number_input("Limit", min_value=1, max_value=1000, value=100)

    filtered = []
    q = query.lower().strip()
    for it in items:
        if q and not ((it.get("original_filename") or "").lower().__contains__(q) or (it.get("id") or "").lower().__contains__(q)):
            continue
        filtered.append(it)
        if len(filtered) >= limit:
            break

    st.write(f"Showing {len(filtered)} of {len(items)}")
    st.dataframe(filtered, use_container_width=True)

    file_id = st.text_input("Select file id", value=(filtered[0]["id"] if filtered else ""))
    if not file_id:
        return

    # Metadata
    try:
        meta = get_metadata(file_id)
        with st.expander("Metadata", expanded=True):
            st.code(json.dumps(meta, indent=2), language="json")
    except Exception as e:
        st.error(f"Failed to fetch metadata: {e}")
        return

    # Shared override key for both preview and download
    override_key = st.text_input("Decrypt key override (optional)", value="", key="dec_key_override")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if st.button("Download encrypted .enc"):
            try:
                content, name = fetch_download(file_id)
                st.download_button("Save encrypted", data=content, file_name=name, mime="application/octet-stream")
            except Exception as e:
                st.error(f"Download failed: {e}")

    with col2:
        if st.button("Download decrypted"):
            try:
                content, name = fetch_decrypt(file_id, override_key if override_key else None)
                st.download_button("Save decrypted", data=content, file_name=name, mime="application/octet-stream")
            except Exception as e:
                st.error(f"Decrypt failed: {e}")

    with col3:
        if st.button("Delete file", type="primary"):
            try:
                resp = api_delete(f"/files/{file_id}")
                if resp.ok:
                    st.success("Deleted.")
                else:
                    st.error(f"Delete failed: {resp.status_code}")
                    st.code(try_json(resp), language="json")
            except Exception as e:
                st.error(f"Delete failed: {e}")

    with col4:
        if st.button("Preview decrypted"):
            try:
                content, name = fetch_decrypt(file_id, override_key if override_key else None)
            except Exception as e:
                st.error(f"Preview fetch failed: {e}")
            else:
                ctype = (meta.get("content_type") or mimetypes.guess_type(meta.get("original_filename") or "")[0] or "application/octet-stream")
                size = len(content)
                st.caption(f"Content-Type: {ctype} • Size: {size} bytes")
                try:
                    if ctype.startswith("image/"):
                        st.image(content, caption=name, use_column_width=True)
                    elif ctype.startswith("video/"):
                        try:
                            import tempfile
                            import pathlib
                            # Save to a temp file and let the browser stream it
                            suffix = pathlib.Path(name).suffix or ".mp4"
                            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tf:
                                tf.write(content)
                                tmp_path = tf.name
                            st.video(tmp_path)
                            st.caption(f"Temporary preview file: {tmp_path}")
                        except Exception as e:
                            st.error(f"Video preview failed: {e}")
                            st.download_button("Download decrypted", data=content, file_name=name)
                    elif ctype in ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-excel") or (name.lower().endswith(".xlsx") or name.lower().endswith(".xls")):
                        try:
                            import pandas as pd
                            with io.BytesIO(content) as bio:
                                df = pd.read_excel(bio)
                            st.dataframe(df, use_container_width=True)
                        except ImportError:
                            st.warning("Excel preview requires pandas and openpyxl. Install with: pip install pandas openpyxl")
                            st.download_button("Download decrypted", data=content, file_name=name)
                        except Exception as e:
                            st.error(f"Excel preview failed: {e}")
                            st.download_button("Download decrypted", data=content, file_name=name)
                    elif ctype.startswith("text/") or name.lower().endswith((".txt", ".csv", ".md", ".json")):
                        try:
                            text = content.decode("utf-8", errors="replace")
                            st.text_area("Preview", value=text, height=300)
                        except Exception as e:
                            st.error(f"Text preview failed: {e}")
                            st.download_button("Download decrypted", data=content, file_name=name)
                    else:
                        st.info("No inline preview available for this type. Download instead.")
                        st.download_button("Download decrypted", data=content, file_name=name)
                    # Raw bytes fallback
                    with st.expander("Raw bytes preview"):
                        snippet = content[:1024]
                        st.write(f"Showing first {len(snippet)} bytes")
                        st.code(snippet.hex(" "), language="text")
                except Exception as e:
                    st.error(f"Render error: {e}")


def main():
    st.set_page_config(page_title="File Server Admin", layout="wide")
    st.title("File Server Admin")

    with st.sidebar:
        # Initialize default before creating widget to avoid Streamlit mutation error
        if "api_base" not in st.session_state:
            st.session_state.api_base = os.environ.get("API_BASE", "http://127.0.0.1:8000").rstrip("/")
        st.text_input("API base URL", key="api_base")
        st.caption("Change to match where the FastAPI server is running.")

    tabs = st.tabs(["Upload", "Files"])
    with tabs[0]:
        upload_encrypt_ui()
    with tabs[1]:
        files_admin_ui()


if __name__ == "__main__":
    main()


