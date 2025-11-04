import re
import logging
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Tuple
from pathlib import Path
from .base import ParserBase
from ..vendor import derive_vendor

logger = logging.getLogger(__name__)

# Enhanced patterns with multiple fallbacks
# Patterns handle both compact format (Model ID: value) and spaced format with dots (Model ID . . . : value)
SERIAL_PATTERNS = [
    re.compile(r'Hard\s*Disk\s*Serial\s*Number\s*[:\.\s\-]+:\s*([A-Z0-9\-]{8,20})', re.IGNORECASE),
    re.compile(r'\bVPD\s*Serial\s*[:\.\s\-]+:\s*([A-Z0-9\-]{8,20})', re.IGNORECASE),
    re.compile(r'\bSerial\s*Number\s*[:\.\s\-]+:\s*([A-Z0-9\-]{8,20})', re.IGNORECASE),
    re.compile(r'\bSerial\s*[:\.\s\-]+:\s*([A-Z0-9\-]{8,20})', re.IGNORECASE),
]

MODEL_PATTERNS = [
    re.compile(r'Hard\s*Disk\s*Model\s*ID\s*[:\.\s\-]+:\s*(.+)', re.IGNORECASE),
    re.compile(r'\bModel\s*ID\s*[:\.\s\-]+:\s*(.+)', re.IGNORECASE),
    re.compile(r'\bModel\s*[:\.\s\-]+:\s*(.+)', re.IGNORECASE),
    re.compile(r'Hard\s*Disk\s*Model\s*[:\.\s\-]+:\s*(.+)', re.IGNORECASE),
]

VENDOR_INFO_PATTERNS = [
    re.compile(r'Vendor\s*Information\s*[:\.\s\-]+:\s*(.+)', re.IGNORECASE),
    re.compile(r'\bVendor\s*[:\.\s\-]+:\s*(.+)', re.IGNORECASE),
    re.compile(r'\bManufacturer\s*[:\.\s\-]+:\s*(.+)', re.IGNORECASE),
]

HEALTH_PATTERNS = [
    # Matches: "Health : #################### 100 % (Excellent)" or "Health: 100%" or "Health : 100"
    re.compile(r'Health\s*[:\.\s\-]+[:\s]*[#\s]*(\d{1,3})\s*%', re.IGNORECASE),
    re.compile(r'Health\s*Score\s*[:\.\s\-]+:\s*(\d{1,3})\s*%?', re.IGNORECASE),
    re.compile(r'Overall\s*Health\s*[:\.\s\-]+:\s*(\d{1,3})\s*%?', re.IGNORECASE),
]

REALLOC_PATTERNS = [
    re.compile(r'Reallocated\s*Sector\s*Count\s*[:\-]?\s*(\d+)', re.IGNORECASE),
    re.compile(r'Reallocated\s*Sectors?\s*[:\-]?\s*(\d+)', re.IGNORECASE),
    re.compile(r'Allocated\s*Sections\s*[:\-]?\s*(\d+)', re.IGNORECASE),
    re.compile(r'\bReallocated\s*[:\-]?\s*(\d+)', re.IGNORECASE),
]

GROWN_DEFECT_PATTERNS = [
    re.compile(r'Grown\s*Defect(?:\s*Count)?\s*[:\-]?\s*(\d+)', re.IGNORECASE),
    re.compile(r'Grown\s*Defects\s*[:\-]?\s*(\d+)', re.IGNORECASE),
    re.compile(r'\bDefect\s*Count\s*[:\-]?\s*(\d+)', re.IGNORECASE),
]

SECTION_BOUNDARIES = [
    re.compile(r'Hard\s*Disk\s*Serial\s*Number\s*[:\-]?', re.IGNORECASE),
    re.compile(r'\bDrive\s+\d+', re.IGNORECASE),
    re.compile(r'\bDisk\s+\d+', re.IGNORECASE),
    re.compile(r'Hard\s*Disk\s+\d+', re.IGNORECASE),
]


def extract_first(patterns: List[re.Pattern], text: str) -> str:
    """Extract first match from a list of patterns"""
    for pat in patterns:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return ""


def clean_single_line(value: str) -> str:
    """Clean value to single line, removing extra whitespace"""
    if not value:
        return ""
    value = value.splitlines()[0]
    return re.sub(r'\s+', ' ', value).strip()


def split_into_drive_sections(text: str) -> List[str]:
    """Split text into drive sections using boundary patterns"""
    idx = []
    for pat in SECTION_BOUNDARIES:
        idx.extend(m.start() for m in pat.finditer(text))
    idx = sorted(set(idx))
    
    if not idx:
        # Fallback: split by blank lines
        parts = re.split(r'\n\s*\n+', text)
        return [p.strip() for p in parts if p.strip()]
    
    sections = []
    for i, start in enumerate(idx):
        end = idx[i+1] if i+1 < len(idx) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            sections.append(chunk)
    return sections


def try_read_with_encoding(file_path: str) -> Tuple[str, str, List[str]]:
    """Try to read file with multiple encodings"""
    attempts = ["utf-8", "iso-8859-1", "cp1252"]
    last_err = None
    
    for enc in attempts:
        try:
            with open(file_path, "r", encoding=enc, errors="strict") as f:
                return f.read(), enc, attempts
        except Exception as e:
            last_err = e
            continue
    
    # Fallback: read with replace
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    return content, "utf-8 (replace)", attempts


class HTMLParser(ParserBase):
    """Parser for HTML Hard Disk Sentinel reports"""
    
    def parse(self, file_path: str, file_name: str) -> List[Dict[str, Any]]:
        """Parse HTML file and extract drive information"""
        try:
            # Try multiple encodings
            content, used_encoding, attempted = try_read_with_encoding(file_path)
            logger.info(f"Read {file_name} with encoding: {used_encoding}")
            
            soup = BeautifulSoup(content, 'lxml')
            
            # Extract text from HTML
            text = soup.get_text("\n", strip=False)
            
            # Parse using text-based approach
            drives = self._parse_text_blob(text, file_name)
            
            # If no drives found, try BeautifulSoup-based parsing
            if not drives:
                logger.info(f"Text-based parsing failed for {file_name}, trying section-based parsing")
                drive_sections = self._find_drive_sections(soup)
                
                for section in drive_sections:
                    drive_data = self._extract_drive_data(section, file_name)
                    if drive_data and drive_data.get('VPD Serial'):
                        drives.append(drive_data)
            
            return drives if drives else [self._create_error_drive(file_name, "No recognizable drive blocks found")]
            
        except Exception as e:
            logger.error(f"Error parsing HTML file {file_name}: {e}")
            return [self._create_error_drive(file_name, str(e))]
    
    def _parse_text_blob(self, text: str, file_name: str) -> List[Dict[str, Any]]:
        """Parse text blob and extract drive information"""
        rows: List[Dict[str, Any]] = []
        sections = split_into_drive_sections(text)
        
        for sec in sections:
            # Extract all fields using pattern matching
            vpd = extract_first(SERIAL_PATTERNS, sec)
            model = clean_single_line(extract_first(MODEL_PATTERNS, sec))
            vendor_info = clean_single_line(extract_first(VENDOR_INFO_PATTERNS, sec))
            health = extract_first(HEALTH_PATTERNS, sec)
            realloc = extract_first(REALLOC_PATTERNS, sec)
            grown = extract_first(GROWN_DEFECT_PATTERNS, sec)
            
            # Only create a row if we have at least one key field
            if any([vpd, model, health]):
                label = vpd[:8] if vpd else ""
                vendor = derive_vendor(model) if model else "Unknown"
                
                try:
                    health_val = int(health) if health else 0
                except Exception:
                    health_val = 0
                
                try:
                    realloc_val = int(realloc) if realloc else 0
                except Exception:
                    realloc_val = 0
                
                try:
                    grown_val = int(grown) if grown else 0
                except Exception:
                    grown_val = 0
                
                rows.append({
                    "Label Serial": label,
                    "VPD Serial": vpd,
                    "Model Number": model,
                    "Vendor Information": vendor_info,
                    "Vendor": vendor,
                    "File Name": file_name,
                    "Health Score": health_val,
                    "Allocated Sections": realloc_val,
                    "Grown Defects": grown_val,
                })
        
        return rows
    
    def _find_drive_sections(self, soup: BeautifulSoup) -> List[BeautifulSoup]:
        """Find sections containing drive information"""
        sections = []
        
        # First, look for tables containing drive information
        tables = soup.find_all('table')
        for table in tables:
            text = table.get_text().lower()
            if any(keyword in text for keyword in ['serial number', 'model id', 'health']):
                sections.append(table)
        
        # Look for divs with drive-related classes
        drive_divs = soup.find_all('div', class_=lambda x: x and any(
            keyword in x.lower() for keyword in ['drive', 'disk', 'hard', 'section', 'block']
        ))
        for div in drive_divs:
            text = div.get_text().lower()
            if any(keyword in text for keyword in ['serial number', 'model id', 'health']):
                sections.append(div)
        
        # If no specific sections found, try to split by headings
        if not sections:
            headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            for heading in headings:
                heading_text = heading.get_text().lower()
                if any(keyword in heading_text for keyword in ['disk', 'drive', 'hard']):
                    # Get content after this heading until next heading
                    section = self._get_content_until_next_heading(heading)
                    if section:
                        sections.append(section)
        
        # If still no sections, try to find any element containing drive data
        if not sections:
            all_elements = soup.find_all(['div', 'section', 'article', 'main'])
            for element in all_elements:
                text = element.get_text().lower()
                if 'hard disk serial number' in text and 'model id' in text:
                    sections.append(element)
        
        return sections
    
    def _get_content_until_next_heading(self, heading) -> BeautifulSoup:
        """Get content from current heading until next heading"""
        content = []
        current = heading.next_sibling
        
        while current:
            if current.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                break
            if hasattr(current, 'get_text'):
                content.append(current)
            current = current.next_sibling
        
        if content:
            # Create a new soup object with the content
            html_content = ''.join(str(item) for item in content)
            return BeautifulSoup(html_content, 'lxml')
        
        return None
    
    def _extract_drive_data(self, section: BeautifulSoup, file_name: str) -> Dict[str, Any]:
        """Extract drive data from a section using enhanced pattern matching"""
        text = section.get_text()
        
        # Use the improved extraction methods
        vpd = extract_first(SERIAL_PATTERNS, text)
        model = clean_single_line(extract_first(MODEL_PATTERNS, text))
        vendor_info = clean_single_line(extract_first(VENDOR_INFO_PATTERNS, text))
        health = extract_first(HEALTH_PATTERNS, text)
        realloc = extract_first(REALLOC_PATTERNS, text)
        grown = extract_first(GROWN_DEFECT_PATTERNS, text)
        
        label = vpd[:8] if vpd else ""
        vendor = derive_vendor(model) if model else "Unknown"
        
        try:
            health_val = int(health) if health else 0
        except Exception:
            health_val = 0
        
        try:
            realloc_val = int(realloc) if realloc else 0
        except Exception:
            realloc_val = 0
        
        try:
            grown_val = int(grown) if grown else 0
        except Exception:
            grown_val = 0
        
        return {
            "Label Serial": label,
            "VPD Serial": vpd,
            "Model Number": model,
            "Vendor Information": vendor_info,
            "Vendor": vendor,
            "File Name": file_name,
            "Health Score": health_val,
            "Allocated Sections": realloc_val,
            "Grown Defects": grown_val,
        }
    
    def _alternative_parse(self, soup: BeautifulSoup, file_name: str) -> List[Dict[str, Any]]:
        """Alternative parsing method when standard sections aren't found"""
        drives = []
        text = soup.get_text()
        
        # Split text into potential drive sections
        # Look for patterns that indicate drive boundaries
        drive_patterns = [
            r'Hard Disk Serial Number\s*:?\s*[A-Z0-9\-]{8,20}.*?(?=Hard Disk Serial Number|$)',
            r'Model ID\s*:?\s*.+?(?=Model ID|$)',
        ]
        
        for pattern in drive_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
            for match in matches:
                section_text = match.group(0)
                drive_data = self._extract_drive_data_from_text(section_text, file_name)
                if drive_data and drive_data.get('VPD Serial'):
                    drives.append(drive_data)
        
        return drives
    
    def _extract_drive_data_from_text(self, text: str, file_name: str) -> Dict[str, Any]:
        """Extract drive data from raw text"""
        drive_data = self.get_default_drive_data(file_name)
        
        # Extract VPD Serial
        serial_match = re.search(r'Hard Disk Serial Number\s*:?\s*([A-Z0-9\-]{8,20})', text, re.IGNORECASE)
        if serial_match:
            vpd_serial = serial_match.group(1).strip()
            drive_data['VPD Serial'] = vpd_serial
            drive_data['Label Serial'] = vpd_serial[:8] if len(vpd_serial) >= 8 else vpd_serial
        
        # Extract Model Number
        model_match = re.search(r'Hard Disk Model ID\s*:?\s*(.+)', text, re.IGNORECASE)
        if model_match:
            model = model_match.group(1).strip()
            drive_data['Model Number'] = model
            drive_data['Vendor'] = derive_vendor(model)
        
        # Extract other fields using the same patterns as _extract_drive_data
        vendor_info_match = re.search(r'Vendor Information\s*:?\s*(.+)', text, re.IGNORECASE)
        if vendor_info_match:
            drive_data['Vendor Information'] = vendor_info_match.group(1).strip()
        
        health_match = re.search(r'Health\s*:?\s*(\d+)\s*%?', text, re.IGNORECASE)
        if health_match:
            drive_data['Health Score'] = int(health_match.group(1))
        
        realloc_match = re.search(r'Reallocated Sector Count\s*:?\s*(\d+)', text, re.IGNORECASE)
        if realloc_match:
            drive_data['Allocated Sections'] = int(realloc_match.group(1))
        
        grown_match = re.search(r'Grown Defect(?: Count)?\s*:?\s*(\d+)', text, re.IGNORECASE)
        if grown_match:
            drive_data['Grown Defects'] = int(grown_match.group(1))
        
        interface_match = re.search(r'(?:Interface|Connection Type)\s*:?\s*([A-Za-z0-9\-/ ]+)', text, re.IGNORECASE)
        if interface_match:
            drive_data['Connection / Interface Type'] = interface_match.group(1).strip()
        
        return drive_data
    
    def _create_error_drive(self, file_name: str, error_message: str) -> Dict[str, Any]:
        """Create a drive entry for parsing errors"""
        drive_data = self.get_default_drive_data(file_name)
        drive_data['Parsing Error'] = error_message
        return drive_data
