"""
OCR a scanned PDF using PyMuPDF (page → PNG) + Apple Vision (ocr binary).

Used as a fallback when pdfplumber returns < 5000 chars from a PDF — meaning
it's a scanned-image PDF with no text layer.

Output: writes the full OCR'd text to {pdf_path}.txt (cached for re-runs).
"""
import os
import subprocess
import sys
import tempfile
import time

import fitz  # PyMuPDF

OCR_BIN = "/Users/jasperlasser/actprep-crackab/ocr"


def ocr_pdf(pdf_path, out_path=None, dpi=200, max_pages=None):
    """Render each PDF page → PNG → Vision OCR → concatenate."""
    out_path = out_path or pdf_path + ".txt"
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        return out_path
    doc = fitz.open(pdf_path)
    n_pages = doc.page_count
    if max_pages:
        n_pages = min(n_pages, max_pages)
    print(f"  OCR: {os.path.basename(pdf_path)} ({n_pages} pages @ {dpi}dpi)", flush=True)
    parts = []
    t0 = time.time()
    with tempfile.TemporaryDirectory() as td:
        for i in range(n_pages):
            page = doc.load_page(i)
            mat = fitz.Matrix(dpi/72, dpi/72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            png_path = os.path.join(td, f"p{i:03d}.png")
            pix.save(png_path)
            # Call ocr binary
            try:
                r = subprocess.run([OCR_BIN, png_path], capture_output=True,
                                   text=True, timeout=30)
                parts.append(f"\n--- page {i+1} ---\n{r.stdout}")
            except subprocess.TimeoutExpired:
                parts.append(f"\n--- page {i+1} TIMEOUT ---\n")
            if (i+1) % 20 == 0 or i+1 == n_pages:
                elapsed = int(time.time() - t0)
                print(f"    {i+1}/{n_pages} pages ({elapsed}s)", flush=True)
    doc.close()
    full = "".join(parts)
    with open(out_path, "w") as f:
        f.write(full)
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: ocr_pdf.py <pdf-path> [--max N]")
        sys.exit(1)
    pdf = sys.argv[1]
    max_pages = None
    if "--max" in sys.argv:
        max_pages = int(sys.argv[sys.argv.index("--max") + 1])
    out = ocr_pdf(pdf, max_pages=max_pages)
    sz = os.path.getsize(out)
    print(f"DONE: {out} ({sz} bytes)")
