# pdf_parser.py

import logging
import re
from typing import List, Dict, Any

from .base import ParserBase
from ..vendor import derive_vendor

logger = logging.getLogger(__name__)


class PDFParser(ParserBase):
    """
    Parser for single-drive PDF diagnostics (e.g., SCSI Toolbox logs).
    - Keeps class + method signatures unchanged.
    - Extracts:
        Serial Number => "VPD Serial" (Label Serial = first 8 chars)
        Product       => "Model Number"
        Vendor Information (exact label only; leave blank if absent)
        Number of Grown Defects => "Grown Defects"
        Health / Reallocated Sectors if present; otherwise None/0
    - Leaves everything else at defaults from ParserBase.
    """

    # --- Regex patterns (tolerant to spacing and separators) ---
    _RE_SERIAL = [
        re.compile(r"Serial\s*Number\s*=\s*([A-Z0-9\-]{8,64})", re.IGNORECASE),
        re.compile(r"\bSerial\s*:\s*([A-Z0-9\-]{8,64})", re.IGNORECASE),
    ]
    _RE_MODEL = [
        re.compile(r"\bProduct\s*=\s*([^\r\n]+)", re.IGNORECASE),
        re.compile(r"\bProduct\s*:\s*([^\r\n]+)", re.IGNORECASE),
        re.compile(r"Hard\s*Disk\s*Model\s*ID\s*[:=]\s*([^\r\n]+)", re.IGNORECASE),
    ]
    # Only the exact "Vendor Information" line; if missing, keep blank (per spec)
    _RE_VENDOR_INFO = [
        re.compile(r"Vendor\s*Information\s*[:=]\s*([^\r\n]+)", re.IGNORECASE),
    ]
    _RE_HEALTH = [
        re.compile(r"Health\s*[:=]\s*(\d{1,3})\s*%?", re.IGNORECASE),
    ]
    _RE_GROWN_DEFECTS = [
        re.compile(r"Number\s+of\s+Grown\s+Defects\s*=\s*(\d+)", re.IGNORECASE),
        re.compile(r"Grown\s*Defect(?:s)?(?:\s*List)?(?:\s*Count)?\s*[:=]\s*(\d+)", re.IGNORECASE),
    ]
    _RE_REALLOC = [
        re.compile(r"Reallocated\s*Sector(?:s)?(?:\s*Count)?\s*[:=]\s*(\d+)", re.IGNORECASE),
    ]

    def parse(self, file_path: str, file_name: str) -> List[Dict[str, Any]]:
        """
        Parse a PDF file and return a list with a single row (one drive per PDF as confirmed).
        Signature preserved for compatibility with the rest of the application.
        """
        try:
            text = self._extract_text_from_pdf(file_path)
            if not text or not text.strip():
                logger.warning("PDFParser: no text extracted from %s", file_name)
                return [self._error_row(file_name, "No text could be extracted from PDF")]

            row = self._extract_row_from_text(text, file_name)
            # If everything is empty, emit a placeholder error row
            if not any([row.get("VPD Serial"), row.get("Model Number"), row.get("Health Score") is not None]):
                return [self._error_row(file_name, "No recognizable fields found")]
            return [row]

        except Exception as e:
            logger.exception("PDFParser: parsing failed for %s", file_name)
            return [self._error_row(file_name, f"Parsing Error: {e}")]

    # --- Helpers --------------------------------------------------------------

    def _error_row(self, file_name: str, msg: str) -> Dict[str, Any]:
        row = self.get_default_drive_data(file_name)
        row["Vendor Information"] = f"Parsing Error: {msg}"
        return row

    def _extract_text_from_pdf(self, file_path: str) -> str:
        """
        Extract text using pdfminer.six if available; else fall back to PyPDF2.
        """
        # Preferred: pdfminer.six
        try:
            from pdfminer.high_level import extract_text  # type: ignore
            return extract_text(file_path)
        except Exception as e:
            logger.info("PDFParser: pdfminer not available or failed (%s); trying PyPDF2", e)

        # Fallback: PyPDF2
        try:
            import PyPDF2  # type: ignore
            chunks = []
            with open(file_path, "rb") as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    chunks.append(page.extract_text() or "")
            return "\n".join(chunks)
        except Exception as e:
            logger.warning("PDFParser: PyPDF2 not available or failed (%s)", e)
            return ""

    def _first(self, patterns, s: str) -> str:
        for pat in patterns:
            m = pat.search(s)
            if m:
                return (m.group(1) or "").strip()
        return ""

    def _trim_serial_suffix(self, serial: str) -> str:
        """
        Trim repeated firmware-like suffixes (e.g., ECE4ECE4ECE4) when serials include
        trailing repeats (seen on some SAS logs/HDS). Keep core if len >= 12.
        """
        if not serial:
            return ""
        s = re.sub(r"\s+", "", serial.strip().upper())
        m = re.search(r"([A-Z0-9]{2,4})\1{1,}$", s)
        return s[:m.start()] if (m and len(s) >= 12) else s

    def _extract_row_from_text(self, text: str, file_name: str) -> Dict[str, Any]:
        row = self.get_default_drive_data(file_name)

        serial = self._first(self._RE_SERIAL, text)
        model = self._first(self._RE_MODEL, text)
        vendor_info = self._first(self._RE_VENDOR_INFO, text)
        health = self._first(self._RE_HEALTH, text)
        grown = self._first(self._RE_GROWN_DEFECTS, text)
        realloc = self._first(self._RE_REALLOC, text)

        serial = self._trim_serial_suffix(serial)

        row["VPD Serial"] = serial
        row["Label Serial"] = serial[:8] if serial else ""
        row["Model Number"] = model
        row["Vendor Information"] = vendor_info  # leave blank if not present
        row["Vendor"] = derive_vendor(model) if model else "Unknown"

        try:
            row["Health Score"] = int(health) if health else None
        except Exception:
            row["Health Score"] = None
        try:
            row["Allocated Sections"] = int(realloc) if realloc else 0
        except Exception:
            row["Allocated Sections"] = 0
        try:
            row["Grown Defects"] = int(grown) if grown else 0
        except Exception:
            row["Grown Defects"] = 0

        return row
