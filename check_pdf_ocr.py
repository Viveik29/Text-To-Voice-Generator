"""Verify PDF OCR dependencies (pdfplumber + Tesseract)."""

from pathlib import Path

print("Checking PDF extraction dependencies...\n")

try:
    import pdfplumber
    print(f"  pdfplumber: OK ({pdfplumber.__version__})")
except ImportError:
    print("  pdfplumber: MISSING — run: pip install pdfplumber")

try:
    import pytesseract
    from PIL import Image
    print(f"  pytesseract: OK ({pytesseract.__version__})")
    print(f"  Pillow: OK ({Image.__version__})")
except ImportError as exc:
    print(f"  pytesseract/Pillow: MISSING — {exc}")

from dotenv import load_dotenv
load_dotenv()

from pipeline.pdf_extract import tesseract_available
import os

if tesseract_available():
    cmd = os.getenv("TESSERACT_CMD") or "tesseract (on PATH)"
    print(f"  Tesseract OCR: OK ({cmd})")
else:
    print("  Tesseract OCR: NOT FOUND")
    print("    Install: https://github.com/UB-Mannheim/tesseract/wiki")
    print('    Then add to .env: TESSERACT_CMD="C:\\Program Files\\Tesseract-OCR\\tesseract.exe"')

print("\nDone.")
