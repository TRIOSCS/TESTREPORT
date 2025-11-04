import logging
from typing import Tuple, List


logger = logging.getLogger(__name__)


def try_encodings(file_path: str) -> Tuple[str, str, List[str]]:
    """
    Try different encodings to read a file.
    Returns (content, successful_encoding, attempted_encodings)
    """
    encodings_to_try = ['utf-8', 'iso-8859-1', 'cp1252']
    attempted = []
    
    for encoding in encodings_to_try:
        attempted.append(encoding)
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            logger.info(f"Successfully read {file_path} with encoding: {encoding}")
            return content, encoding, attempted
        except UnicodeDecodeError:
            logger.warning(f"Failed to read {file_path} with encoding: {encoding}")
            continue
    
    # If all encodings fail, try with errors='replace'
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        logger.warning(f"Read {file_path} with UTF-8 and error replacement")
        return content, 'utf-8-with-replacement', attempted
    except Exception as e:
        logger.error(f"Failed to read {file_path} with any encoding: {e}")
        raise
