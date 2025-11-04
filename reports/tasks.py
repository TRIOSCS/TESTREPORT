import os
import logging
import zipfile
import tempfile
import shutil
from pathlib import Path
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from celery import shared_task
from .models import ParsingJob, ParseError
from .services import FileCollector, ExcelWriter, HTMLParser, TXTParser, PDFParser

logger = logging.getLogger(__name__)


def _is_zip_file(file_path: str) -> bool:
    """Check if file is a zip file"""
    try:
        return zipfile.is_zipfile(file_path)
    except:
        return False


def _extract_zip(zip_path: str, extract_dir: str) -> list:
    """Recursively extract zip files"""
    extracted_files = []
    supported_extensions = {'.html', '.txt', '.pdf'}
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            for member in zip_ref.namelist():
                # Skip directories and hidden files
                if member.endswith('/') or member.startswith('.') or member.startswith('__MACOSX'):
                    continue
                
                # Extract file
                zip_ref.extract(member, extract_dir)
                extracted_path = os.path.join(extract_dir, member)
                
                # Check if extracted file is another zip
                if _is_zip_file(extracted_path):
                    # Recursively extract nested zip
                    nested_files = _extract_zip(extracted_path, extract_dir)
                    extracted_files.extend(nested_files)
                    # Remove the zip file after extraction
                    os.remove(extracted_path)
                else:
                    # Check if it's a supported file type
                    file_ext = Path(extracted_path).suffix.lower()
                    if file_ext in supported_extensions:
                        extracted_files.append(extracted_path)
                    else:
                        # Remove unsupported files
                        logger.debug(f"Removing unsupported file: {extracted_path}")
                        os.remove(extracted_path)
    
    except Exception as e:
        logger.error(f"Error extracting zip file {zip_path}: {e}")
    
    return extracted_files


@shared_task(bind=True, max_retries=3)
def process_files_task(self, job_id, file_paths):
    """
    Background task to process uploaded files.
    
    Args:
        job_id: UUID of the ParsingJob
        file_paths: List of absolute paths to uploaded files
    """
    try:
        # Get the job
        job = ParsingJob.objects.get(id=job_id)
        job.status = 'PROCESSING'
        job.started_at = timezone.now()
        job.task_id = self.request.id
        job.save()
        
        logger.info(f"Starting processing for job {job_id}")
        
        # Create temp directory for ZIP extraction
        extract_dir = tempfile.mkdtemp()
        
        # Initialize error tracking
        parse_errors = []
        
        # Extract ZIP files first
        files_to_process = []
        for file_path in file_paths:
            try:
                if not os.path.exists(file_path):
                    logger.warning(f"File not found: {file_path}")
                    continue
                
                if _is_zip_file(file_path):
                    logger.info(f"Extracting ZIP file: {os.path.basename(file_path)}")
                    extracted = _extract_zip(file_path, extract_dir)
                    files_to_process.extend(extracted)
                    logger.info(f"Extracted {len(extracted)} file(s) from {os.path.basename(file_path)}")
                    # Remove the ZIP file after extraction
                    os.remove(file_path)
                else:
                    files_to_process.append(file_path)
            except Exception as e:
                logger.error(f"Error processing {file_path}: {e}")
                parse_errors.append({
                    'file_name': os.path.basename(file_path),
                    'error_message': f'Failed to process: {str(e)}',
                    'encodings_tried': []
                })
        
        logger.info(f"Processing {len(files_to_process)} file(s) total")
        
        # Parse files
        all_drives = []
        
        for file_path in files_to_process:
            try:
                if not os.path.exists(file_path):
                    logger.warning(f"File not found: {file_path}")
                    continue
                    
                file_name = os.path.basename(file_path)
                file_ext = Path(file_path).suffix.lower()
                
                # Choose parser based on file extension
                if file_ext == '.html':
                    parser = HTMLParser()
                elif file_ext == '.txt':
                    parser = TXTParser()
                elif file_ext == '.pdf':
                    parser = PDFParser()
                else:
                    logger.warning(f"Unknown file extension: {file_ext}")
                    continue
                
                # Parse file
                drives = parser.parse(file_path, file_name)
                all_drives.extend(drives)
                
            except Exception as e:
                logger.error(f"Error parsing file {file_path}: {e}")
                parse_errors.append({
                    'file_name': os.path.basename(file_path),
                    'error_message': str(e),
                    'encodings_tried': []
                })
        
        # Deduplicate drives
        collector = FileCollector()
        original_count = len(all_drives)
        unique_drives = collector.deduplicate_drives(all_drives)
        duplicates_removed = original_count - len(unique_drives)
        
        # Generate output files
        first_file_name = os.path.basename(file_paths[0]).split('.')[0] if file_paths else 'report'
        output_base = f"{first_file_name}_summary_{job_id}"
        
        # Create output directory
        output_dir = os.path.join(settings.MEDIA_ROOT, 'results')
        os.makedirs(output_dir, exist_ok=True)
        
        excel_path = os.path.join(output_dir, f"{output_base}.xlsx")
        csv_path = os.path.join(output_dir, f"{output_base}.csv")
        
        # Write Excel file
        excel_writer = ExcelWriter()
        excel_writer.write_excel(unique_drives, excel_path, parse_errors)
        
        # Write CSV file
        excel_writer.write_csv(unique_drives, csv_path)
        
        # Update job with results
        job.result_excel = f"results/{output_base}.xlsx"
        job.result_csv = f"results/{output_base}.csv"
        job.total_files = len(file_paths)
        job.total_drives = len(unique_drives)
        job.duplicates_removed = duplicates_removed
        job.status = 'COMPLETED'
        job.completed_at = timezone.now()
        job.save()
        
        # Save parse errors to database
        for error in parse_errors:
            ParseError.objects.create(
                job=job,
                file_name=error['file_name'],
                error_message=error['error_message'],
                encodings_tried=error['encodings_tried']
            )
        
        # Clean up uploaded and extracted files
        for file_path in files_to_process:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logger.warning(f"Failed to delete temp file {file_path}: {e}")
        
        # Clean up extraction directory
        try:
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)
        except Exception as e:
            logger.warning(f"Failed to delete extraction directory {extract_dir}: {e}")
        
        logger.info(f"Successfully completed job {job_id}")
        return {
            'job_id': str(job_id),
            'status': 'COMPLETED',
            'total_drives': len(unique_drives),
            'duplicates_removed': duplicates_removed
        }
        
    except ParsingJob.DoesNotExist:
        logger.error(f"Job {job_id} not found")
        raise
        
    except Exception as e:
        logger.exception(f"Error processing job {job_id}: {e}")
        try:
            job = ParsingJob.objects.get(id=job_id)
            job.status = 'FAILED'
            job.error_message = str(e)
            job.completed_at = timezone.now()
            job.save()
        except Exception as save_error:
            logger.error(f"Failed to save error status: {save_error}")
        
        # Retry the task if it hasn't exceeded max retries
        raise self.retry(exc=e, countdown=60)

