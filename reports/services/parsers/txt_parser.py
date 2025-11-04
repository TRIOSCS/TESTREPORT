
import re
import logging
from typing import List, Dict, Any, Tuple

from .base import ParserBase
from ..vendor import derive_vendor

logger = logging.getLogger(__name__)


class TXTParser(ParserBase):
    """Parser for TXT Hard Disk Sentinel reports (robust, block-based)."""

    # ----------------------------
    # Public API (keep signatures the same)
    # ----------------------------
    def parse(self, file_path: str, file_name: str) -> List[Dict[str, Any]]:
        """Parse TXT file and extract drive information"""
        try:
            # Prefer project-provided encoding helper if available
            from ..encoding import try_encodings  # type: ignore
            content, used, attempts = try_encodings(file_path, ["utf-8", "iso-8859-1", "cp1252"])
        except Exception as e:
            # Fallback to local implementation
            content, used, attempts = self._fallback_try_encodings(file_path)

        try:
            blocks = self._split_blocks(content)
            drives: List[Dict[str, Any]] = []

            for blk in blocks:
                data = self._extract_drive_data(blk, file_name)
                # Keep entries that have at least Serial/Model/Health
                if any([data.get("VPD Serial"), data.get("Model Number"), data.get("Health Score") is not None]):
                    drives.append(data)

            if not drives:
                # Emit a placeholder error row for this file
                drives.append(self._create_error_drive(file_name, "No recognizable drive blocks found"))
                logger.warning("TXTParser: no drives parsed from %s (encoding=%s)", file_name, used)

            # Attach encoding info to logger (Errors sheet is created by orchestrator)
            logger.info("TXTParser: parsed %d drive(s) from %s with encoding %s; attempts=%s",
                        len(drives), file_name, used, attempts)
            return drives

        except Exception as e:
            logger.exception("TXTParser: parsing failed for %s", file_name)
            return [self._create_error_drive(file_name, f"Parsing Error: {e}")]

    # ----------------------------
    # Internals
    # ----------------------------
    def _fallback_try_encodings(self, path: str) -> Tuple[str, str, List[str]]:
        attempts = ["utf-8", "iso-8859-1", "cp1252"]
        last_err = None
        for enc in attempts:
            try:
                with open(path, "r", encoding=enc, errors="strict") as f:
                    return f.read(), enc, attempts
            except Exception as e:
                last_err = e
                continue
        # final permissive fallback
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(), "utf-8 (replace)", attempts

    # Disk block delimiter: start at a "Hard Disk Summary" header
    _BLOCK_START = re.compile(r"^\s*Hard\s+Disk\s+Summary\s*\n[-\s]+\n", re.IGNORECASE | re.MULTILINE)

    # Field regexes (scoped within a block)
    _RE_SERIALS = [
        re.compile(r"Hard\s*Disk\s*Serial\s*Number\s*(?:\s*\.\s*)*:\s*([A-Z0-9\-\s]{6,40})", re.IGNORECASE),
        re.compile(r"\bVPD\s*Serial\s*(?:\s*\.\s*)*:\s*([A-Z0-9\-\s]{6,40})", re.IGNORECASE),
        re.compile(r"\bSerial\s*Number\s*(?:\s*\.\s*)*:\s*([A-Z0-9\-\s]{6,40})", re.IGNORECASE),
    ]
    _RE_MODEL = [
        re.compile(r"Hard\s*Disk\s*Model\s*ID\s*(?:\s*\.\s*)*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"\bModel\s*ID\s*(?:\s*\.\s*)*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"\bModel\s*(?:\s*\.\s*)*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    ]
    _RE_VENDOR_INFO = [
        re.compile(r"Vendor\s*Information\s*(?:\s*\.\s*)*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"\bVendor\s*(?:\s*\.\s*)*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
        re.compile(r"\bManufacturer\s*(?:\s*\.\s*)*:\s*(.+)$", re.IGNORECASE | re.MULTILINE),
    ]
    _RE_HEALTH = [
        re.compile(r"Health\s*(?:\s*\.\s*)*:\s*[#\s\-\u2588]*\s*(\d{1,3})\s*%?", re.IGNORECASE),
        re.compile(r"Health\s*Score\s*(?:\s*\.\s*)*:\s*(\d{1,3})\s*%?", re.IGNORECASE),
        re.compile(r"Overall\s*Health\s*(?:\s*\.\s*)*:\s*(\d{1,3})\s*%?", re.IGNORECASE),
    ]
    # Accept truncations like "Reallocated Sectors Co.." produced by fixed-width renderings
    _RE_REALLOC = [
        re.compile(r"Reallocated\s*Sector(?:s)?\s*(?:Count|Co\.\.)\s*(?:\s*\.\s*)*:\s*(\d+)", re.IGNORECASE),
        re.compile(r"\bReallocated\s*Sectors?\s*(?:\s*\.\s*)*:\s*(\d+)", re.IGNORECASE),
        re.compile(r"\bReallocated\s*(?:\s*\.\s*)*:\s*(\d+)", re.IGNORECASE),
    ]
    _RE_GROWN = [
        re.compile(r"Grown\s*Defect(?:s)?(?:\s*List)?(?:\s*Count)?\s*(?:\s*\.\s*)*:\s*(\d+)", re.IGNORECASE),
        re.compile(r"\bGrown\s*Defects?\s*(?:\s*\.\s*)*:\s*(\d+)", re.IGNORECASE),
        re.compile(r"\bDefect\s*Count\s*(?:\s*\.\s*)*:\s*(\d+)", re.IGNORECASE),
    ]

    def _split_blocks(self, text: str) -> List[str]:
        """Split the report into per-disk blocks based on the 'Hard Disk Summary' header."""
        starts = [m.start() for m in self._BLOCK_START.finditer(text)]
        if not starts:
            # fallback: try very large blank-line splits
            parts = re.split(r"\n\s*\n{2,}", text)
            return [p for p in (s.strip() for s in parts) if p]
        blocks = []
        for i, s in enumerate(starts):
            e = starts[i + 1] if i + 1 < len(starts) else len(text)
            blk = text[s:e].strip()
            if blk:
                blocks.append(blk)
        return blocks

    def _first(self, patterns: List[re.Pattern], s: str) -> str:
        for pat in patterns:
            m = pat.search(s)
            if m:
                return m.group(1).strip()
        return ""

    def _clean_single_line(self, s: str) -> str:
        if not s:
            return ""
        return re.sub(r"\s+", " ", s.strip())

    def _trim_repeating_suffix(self, serial: str) -> str:
        """
        Some HDS prints end with repeated 4-char groups (e.g., ECE4ECE4ECE4).
        If we detect a repeated suffix (group of 2-4 uppercase chars repeated >=2),
        trim it but keep the leading core. Only apply when it lengthens the serial
        beyond ~12 chars to avoid over-trimming short serials.
        """
        s = (serial or "").strip().upper()
        s = re.sub(r"\s+", "", s)  # remove spaces
        m = re.search(r"([A-Z0-9]{2,4})\1{1,}$", s)
        if m and len(s) >= 12:
            core = s[:m.start()]
            result = core if core else s
        else:
            result = s
        result = result.replace("TOTALSIZE", "")
        return result

    def _extract_drive_data(self, block: str, file_name: str) -> Dict[str, Any]:
        """
        Extract required fields from a single disk block.
        Keep this method name/signature for compatibility with existing code.
        """
        serial_raw = self._first(self._RE_SERIALS, block)
        model = self._first(self._RE_MODEL, block)
        vendor_info = self._first(self._RE_VENDOR_INFO, block)
        health = self._first(self._RE_HEALTH, block)
        realloc = self._first(self._RE_REALLOC, block)
        grown = self._first(self._RE_GROWN, block)

        serial = self._trim_repeating_suffix(serial_raw) if serial_raw else ""
        model = self._clean_single_line(model)
        vendor_info = self._clean_single_line(vendor_info)

        # Prepare default structure (from ParserBase if available)
        try:
            drive = self.get_default_drive_data(file_name)  # Provided by ParserBase
        except Exception:
            # Fallback shape to match orchestrator columns
            drive = {
                "Label Serial": "",
                "VPD Serial": "",
                "Model Number": "",
                "Vendor Information": "",
                "Vendor": "Unknown",
                "File Name": file_name,
                "Health Score": None,
                "Allocated Sections": 0,
                "Grown Defects": 0,
            }

        drive["VPD Serial"] = serial
        drive["Label Serial"] = serial[:8] if serial else ""
        drive["Model Number"] = model
        drive["Vendor Information"] = vendor_info
        drive["Vendor"] = derive_vendor(model) if model else "Unknown"

        try:
            drive["Health Score"] = int(health) if health else None
        except Exception:
            drive["Health Score"] = None
        try:
            drive["Allocated Sections"] = int(realloc) if realloc else 0
        except Exception:
            drive["Allocated Sections"] = 0
        try:
            drive["Grown Defects"] = int(grown) if grown else 0
        except Exception:
            drive["Grown Defects"] = 0

        return drive

    def _create_error_drive(self, file_name: str, error_message: str) -> Dict[str, Any]:
        """Create a drive entry for parsing errors (keep signature)."""
        try:
            drive_data = self.get_default_drive_data(file_name)
        except Exception:
            drive_data = {
                "Label Serial": "",
                "VPD Serial": "",
                "Model Number": "",
                "Vendor Information": "",
                "Vendor": "Unknown",
                "File Name": file_name,
                "Health Score": None,
                "Allocated Sections": 0,
                "Grown Defects": 0,
            }
        drive_data["Vendor Information"] = f"Parsing Error: {error_message}"
        return drive_data
