from abc import ABC, abstractmethod
from typing import List, Dict, Any


class ParserBase(ABC):
    """Base class for all file parsers"""
    
    @abstractmethod
    def parse(self, file_path: str, file_name: str) -> List[Dict[str, Any]]:
        """
        Parse a file and return a list of drive dictionaries.
        Each dictionary should contain all required fields.
        """
        pass
    
    def get_default_drive_data(self, file_name: str) -> Dict[str, Any]:
        """Return default drive data structure"""
        return {
            'Label Serial': '',
            'VPD Serial': '',
            'Model Number': '',
            'Vendor Information': '',
            'Vendor': 'Unknown',
            'File Name': file_name,
            'Health Score': 0,
            'Allocated Sections': 0,
            'Grown Defects': 0,
        }
