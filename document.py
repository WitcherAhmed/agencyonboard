"""Text extraction from uploaded documents. Never invents content."""
import io
from pathlib import Path

TEXT_EXT = {".txt", ".md", ".csv", ".json"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
MAX_CHARS = 12000


def extract(path: Path) -> dict:
    """Return {'kind': 'text'|'image'|'empty', 'text': str, 'chars': int, 'note': str}."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXT:
        return {"kind": "image", "text": "", "chars": 0,
                "note": "Image file. The agent must read it visually itself."}
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            parts = [(p.extract_text() or "") for p in reader.pages]
            text, note = "\n".join(parts), f"{len(reader.pages)} page(s)"
        elif ext in (".docx", ".doc"):
            import docx2txt
            text, note = docx2txt.process(str(path)) or "", "docx"
        elif ext in (".xlsx", ".xls"):
            import openpyxl  # optional
            wb = openpyxl.load_workbook(str(path), data_only=True)
            rows = []
            for ws in wb.worksheets:
                for row in ws.iter_rows(values_only=True):
                    rows.append(" | ".join("" if c is None else str(c) for c in row))
            text, note = "\n".join(rows), "xlsx"
        elif ext in TEXT_EXT:
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            note = "plain text"
        else:
            raw = path.read_bytes()
            text = raw.decode("utf-8", errors="replace")
            note = f"unknown extension {ext}, read as bytes"
    except Exception as exc:  # never crash the demo on a bad file
        return {"kind": "empty", "text": "", "chars": 0,
                "note": f"Extraction failed: {type(exc).__name__}: {exc}"}

    text = " ".join(text.split()) if len(text) > MAX_CHARS else text.strip()
    if not text:
        return {"kind": "empty", "text": "", "chars": 0,
                "note": f"No text layer found ({note})"}
    return {"kind": "text", "text": text[:MAX_CHARS], "chars": len(text), "note": note}