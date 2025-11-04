import os
import zipfile
import tempfile
import logging
from pathlib import Path
from typing import List, Tuple, Dict, Any
import magic

logger = logging.getLogger(__name__)


class FileCollector:
    """Handles file collection, validation, and extraction"""
    
    def __init__(self):
        self.max_single_file_size = 100 * 1024 * 1024  # 100MB
        self.max_total_size = 200 * 1024 * 1024  # 200MB
        self.max_files = 50
        self.supported_extensions = {'.html', '.txt', '.pdf'}
    
    def collect_files(self, uploaded_files: List, temp_dir: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        Collect and validate uploaded files.
        Returns (file_paths, errors)
        """
        errors = []
        collected_files = []
        total_size = 0
        
        # Create temp directory for extraction
        extract_dir = os.path.join(temp_dir, 'extracted')
        os.makedirs(extract_dir, exist_ok=True)
        
        for uploaded_file in uploaded_files:
            try:
                # Check single file size
                if uploaded_file.size > self.max_single_file_size:
                    errors.append({
                        'file_name': uploaded_file.name,
                        'error_message': f'File size {uploaded_file.size / (1024*1024):.1f}MB exceeds limit of 100MB',
                        'encodings_tried': []
                    })
                    continue
                
                total_size += uploaded_file.size
                
                # Save uploaded file to temp directory
                temp_file_path = os.path.join(temp_dir, uploaded_file.name)
                with open(temp_file_path, 'wb') as f:
                    for chunk in uploaded_file.chunks():
                        f.write(chunk)
                
                # Check if it's a zip file
                if self._is_zip_file(temp_file_path):
                    extracted_files = self._extract_zip(temp_file_path, extract_dir)
                    collected_files.extend(extracted_files)
                else:
                    # Check file type
                    file_type = self._get_file_type(temp_file_path)
                    if file_type in self.supported_extensions:
                        collected_files.append(temp_file_path)
                    else:
                        logger.warning(f"Unsupported file type: {file_type} for {uploaded_file.name}")
                
            except Exception as e:
                errors.append({
                    'file_name': uploaded_file.name,
                    'error_message': str(e),
                    'encodings_tried': []
                })
        
        # Check total size
        if total_size > self.max_total_size:
            errors.append({
                'file_name': 'Total upload',
                'error_message': f'Total size {total_size / (1024*1024):.1f}MB exceeds limit of 200MB',
                'encodings_tried': []
            })
            return [], errors
        
        # Check file count
        if len(collected_files) > self.max_files:
            errors.append({
                'file_name': 'File count',
                'error_message': f'Found {len(collected_files)} files, exceeds limit of 50. Please narrow your selection.',
                'encodings_tried': []
            })
            return [], errors
        
        return collected_files, errors
    
    def _is_zip_file(self, file_path: str) -> bool:
        """Check if file is a zip file"""
        try:
            return zipfile.is_zipfile(file_path)
        except:
            return False
    
    def _extract_zip(self, zip_path: str, extract_dir: str) -> List[str]:
        """Recursively extract zip files"""
        extracted_files = []
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    # Skip directories and hidden files
                    if member.endswith('/') or member.startswith('.'):
                        continue
                    
                    # Extract file
                    zip_ref.extract(member, extract_dir)
                    extracted_path = os.path.join(extract_dir, member)
                    
                    # Check if extracted file is another zip
                    if self._is_zip_file(extracted_path):
                        # Recursively extract nested zip
                        nested_files = self._extract_zip(extracted_path, extract_dir)
                        extracted_files.extend(nested_files)
                        # Remove the zip file after extraction
                        os.remove(extracted_path)
                    else:
                        # Check if it's a supported file type
                        file_type = self._get_file_type(extracted_path)
                        if file_type in self.supported_extensions:
                            extracted_files.append(extracted_path)
                        else:
                            # Remove unsupported files
                            os.remove(extracted_path)
        
        except Exception as e:
            logger.error(f"Error extracting zip file {zip_path}: {e}")
        
        return extracted_files
    
    def _get_file_type(self, file_path: str) -> str:
        """Get file type based on extension and content"""
        try:
            # First try to get MIME type
            mime_type = magic.from_file(file_path, mime=True)
            
            if mime_type == 'text/html':
                return '.html'
            elif mime_type == 'text/plain':
                return '.txt'
            elif mime_type == 'application/pdf':
                return '.pdf'
            
            # Fallback to extension
            ext = Path(file_path).suffix.lower()
            if ext in self.supported_extensions:
                return ext
            
            return ext
            
        except Exception as e:
            logger.warning(f"Could not determine file type for {file_path}: {e}")
            # Fallback to extension
            return Path(file_path).suffix.lower()
    
    def deduplicate_drives(self, drives: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate drives by VPD Serial, keeping the first occurrence.
        """
        seen_serials = set()
        unique_drives = []
        
        for drive in drives:
            vpd_serial = drive.get('VPD Serial', '').strip()
            
            if vpd_serial and vpd_serial not in seen_serials:
                seen_serials.add(vpd_serial)
                unique_drives.append(drive)
            elif not vpd_serial:
                # Keep drives without serial numbers (parsing errors, etc.)
                unique_drives.append(drive)
        
        return unique_drives
