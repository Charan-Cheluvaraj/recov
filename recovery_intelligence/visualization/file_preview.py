import os
import io
import sqlite3
import zipfile
from pathlib import Path
from typing import Optional, List, Dict, Any
import streamlit as st


def render_hex_preview(data: bytes, max_bytes: int = 512) -> str:
    """Format binary data into standard forensic hex dump view (16 bytes per line)."""
    if not data:
        return "Empty data stream (0 bytes)."
    
    view_data = data[:max_bytes]
    lines = []
    for offset in range(0, len(view_data), 16):
        chunk = view_data[offset:offset + 16]
        hex_bytes = " ".join(f"{b:02X}" for b in chunk)
        ascii_chars = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"{offset:08X}  {hex_bytes:<48}  |{ascii_chars}|")
    
    if len(data) > max_bytes:
        lines.append(f"... [{len(data) - max_bytes:,} additional bytes truncated for display]")
    return "\n".join(lines)


def render_file_preview(output_path: Optional[str], file_type: str = "unknown") -> None:
    """
    Render safe, robust forensic preview for recovered candidate artifacts across all supported formats.
    Never crashes on corrupted data or unsupported formats; safely falls back to hex view.
    """
    if not output_path:
        st.info("No artifact output path recorded for this candidate.")
        return

    path = Path(output_path)
    if not path.is_file():
        st.warning(f"Artifact file not found on disk at: `{output_path}`")
        return

    try:
        file_size = path.stat().st_size
    except Exception:
        file_size = 0

    if file_size == 0:
        st.warning("Artifact exists on disk but is 0 bytes.")
        return

    ftype = (file_type or "unknown").lower()

    # Read binary bytes safely
    try:
        with open(path, "rb") as f:
            raw_bytes = f.read()
    except Exception as e:
        st.error(f"Failed to read artifact bytes: {e}")
        return

    st.markdown("##### Artifact Preview")

    # 1. Images (JPEG, PNG, etc.)
    if ftype in ("jpeg", "jpg", "png", "image"):
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(raw_bytes))
            st.image(img, caption=f"Recovered Image ({img.width}x{img.height}, format={img.format})", use_container_width=True)
            return
        except Exception as e:
            st.warning(f"Image parser failed to decode raster stream: {e}")
            st.caption("Falling back to raw binary hex preview below:")
            st.code(render_hex_preview(raw_bytes), language="text")
            return

    # 2. PDF Documents
    elif ftype == "pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw_bytes))
            num_pages = len(reader.pages)
            st.markdown(f"**PDF Document Structure:** `{num_pages}` page(s) detected")
            if num_pages > 0:
                first_page_text = reader.pages[0].extract_text() or ""
                if first_page_text.strip():
                    st.text_area("Extracted Page 1 Text", first_page_text[:4000], height=180)
                else:
                    st.info("Page 1 contains no extractable text stream (may be scanned image/raster content).")
            return
        except Exception:
            try:
                import PyPDF2
                reader = PyPDF2.PdfReader(io.BytesIO(raw_bytes))
                num_pages = len(reader.pages)
                st.markdown(f"**PDF Document Structure:** `{num_pages}` page(s) detected")
                if num_pages > 0:
                    first_page_text = reader.pages[0].extract_text() or ""
                    if first_page_text.strip():
                        st.text_area("Extracted Page 1 Text", first_page_text[:4000], height=180)
                return
            except Exception as e:
                st.warning(f"PDF parser encountered structural syntax errors: {e}")
                st.caption("Falling back to raw binary hex preview:")
                st.code(render_hex_preview(raw_bytes), language="text")
                return

    # 3. Plain Text / Logs
    elif ftype in ("text", "txt", "log", "json", "csv"):
        try:
            text_content = raw_bytes.decode("utf-8", errors="replace")
            st.text_area("Recovered Text Excerpt", text_content[:15000], height=240)
            return
        except Exception as e:
            st.warning(f"Text decoding failed: {e}")

    # 4. DOCX Documents
    elif ftype in ("docx", "doc"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(raw_bytes))
            paras = [p.text for p in doc.paragraphs if p.text.strip()]
            if paras:
                st.markdown(f"**DOCX Paragraphs:** Found `{len(paras)}` paragraph(s)")
                st.text_area("Extracted Document Text", "\n\n".join(paras[:50]), height=220)
            else:
                st.info("DOCX archive parsed successfully, but contains no textual body paragraphs.")
            return
        except Exception as e:
            st.warning(f"DOCX parser failed: {e}")

    # 5. SQLite Databases
    elif ftype in ("sqlite", "sqlite3", "db"):
        try:
            conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            if tables:
                table_names = [t[0] for t in tables]
                st.markdown(f"**Database Tables Detected:** `{len(tables)}` ({', '.join(table_names)})")
                selected_t = st.selectbox("Inspect Table Schema & Sample", options=table_names)
                schema_sql = next((t[1] for t in tables if t[0] == selected_t), "")
                if schema_sql:
                    st.code(schema_sql, language="sql")
                try:
                    cursor.execute(f"SELECT * FROM \"{selected_t}\" LIMIT 5;")
                    rows = cursor.fetchall()
                    col_names = [desc[0] for desc in cursor.description]
                    if rows:
                        import pandas as pd
                        df = pd.DataFrame(rows, columns=col_names)
                        st.dataframe(df, use_container_width=True)
                    else:
                        st.info(f"Table '{selected_t}' contains 0 rows.")
                except Exception as query_err:
                    st.warning(f"Could not read records from '{selected_t}': {query_err}")
            else:
                st.info("SQLite file is valid, but sqlite_master contains no user tables.")
            conn.close()
            return
        except Exception as e:
            st.warning(f"SQLite parser could not open database: {e}")

    # 6. ZIP Archives
    elif ftype == "zip":
        try:
            with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
                infolist = zf.infolist()
                st.markdown(f"**ZIP Archive Entries:** `{len(infolist)}` files/directories found")
                zip_entries = [
                    {
                        "Filename": info.filename,
                        "Uncompressed Size": f"{info.file_size:,} B",
                        "Compressed Size": f"{info.compress_size:,} B",
                    }
                    for info in infolist
                ]
                st.dataframe(zip_entries, use_container_width=True)
            return
        except Exception as e:
            st.warning(f"ZIP archive parser failed: {e}")

    # Fallback to hex viewer for all other binary or failed formats
    st.info("Preview unavailable; artifact recovered as raw binary.")
    st.code(render_hex_preview(raw_bytes), language="text")
