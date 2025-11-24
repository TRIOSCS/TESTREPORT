import os
import tempfile
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
from pathlib import Path
from .models import UploadBatch, ParseError, ParsingJob
from .services import FileCollector, ExcelWriter, HTMLParser, TXTParser, PDFParser
from .tasks import process_files_task

logger = logging.getLogger(__name__)


def upload_view(request):
    """Display upload form"""
    error_message = None
    
    if request.method == 'POST':
        # Handle multiple files from request.FILES.getlist()
        uploaded_files = request.FILES.getlist('files')
        if uploaded_files:
            return submit_parsing_job(request, uploaded_files)
        else:
            error_message = 'Please select at least one file to upload.'
    
    return render(request, 'reports/upload.html', {'error_message': error_message})


def submit_parsing_job(request, uploaded_files):
    """Submit files for background processing"""
    try:
        # Create upload directory
        upload_dir = os.path.join(settings.MEDIA_ROOT, 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        
        # Save uploaded files temporarily
        file_paths = []
        file_names = []
        
        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name
            file_names.append(file_name)
            
            # Save file
            file_path = os.path.join(upload_dir, f"{os.urandom(8).hex()}_{file_name}")
            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            file_paths.append(file_path)
        
        # Create job record
        job = ParsingJob.objects.create(
            uploaded_files=file_names,
            status='PENDING',
            total_files=len(file_names)
        )
        
        # Submit task to Celery
        process_files_task.delay(str(job.id), file_paths)
        
        logger.info(f"Submitted job {job.id} with {len(file_names)} files")
        
        # Redirect to job status page
        return redirect('job_status', job_id=job.id)
        
    except Exception as e:
        logger.error(f"Error submitting job: {e}")
        return render(request, 'reports/upload.html', {
            'error_message': f'Failed to submit job: {str(e)}'
        })


def job_list_view(request):
    """Display list of all parsing jobs"""
    jobs = ParsingJob.objects.all()[:50]  # Last 50 jobs
    
    context = {
        'jobs': jobs
    }
    
    return render(request, 'reports/job_list.html', context)


def job_status_view(request, job_id):
    """Display status of a specific job"""
    job = get_object_or_404(ParsingJob, id=job_id)
    errors = job.errors.all()
    
    context = {
        'job': job,
        'errors': errors
    }
    
    return render(request, 'reports/job_status.html', context)


def job_status_api(request, job_id):
    """API endpoint to check job status (for polling)"""
    try:
        job = ParsingJob.objects.get(id=job_id)
        
        data = {
            'id': str(job.id),
            'status': job.status,
            'created_at': job.created_at.isoformat(),
            'total_files': job.total_files,
            'total_drives': job.total_drives,
            'duplicates_removed': job.duplicates_removed,
            'error_message': job.error_message
        }
        
        if job.status == 'COMPLETED':
            data['result_excel_url'] = f"/reports/download/{job.id}/?type=xlsx"
            data['result_csv_url'] = f"/reports/download/{job.id}/?type=csv"
        
        return JsonResponse(data)
    
    except ParsingJob.DoesNotExist:
        return JsonResponse({'error': 'Job not found'}, status=404)


def download_job_result(request, job_id):
    """Download result files from a completed job"""
    job = get_object_or_404(ParsingJob, id=job_id)
    
    if job.status != 'COMPLETED':
        raise Http404("Job not completed yet")
    
    file_type = request.GET.get('type', 'xlsx')
    
    if file_type == 'xlsx' and job.result_excel:
        file_path = job.result_excel.path
        filename = os.path.basename(file_path)
        
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                response = HttpResponse(
                    f.read(), 
                    content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                )
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
    
    elif file_type == 'csv' and job.result_csv:
        file_path = job.result_csv.path
        filename = os.path.basename(file_path)
        
        if os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
    
    raise Http404("File not found")


# Legacy views (keep for backward compatibility if needed)
def parse_files(request, uploaded_files):
    """Process uploaded files and generate reports (LEGACY - synchronous)"""
    try:
        # Create temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Collect and validate files
            collector = FileCollector()
            collected_files, collection_errors = collector.collect_files(uploaded_files, temp_dir)
            
            if collection_errors:
                return render(request, 'reports/result.html', {
                    'error': 'File validation failed',
                    'errors': collection_errors,
                    'files_processed': 0,
                    'drives_parsed': 0,
                    'duplicates_removed': 0
                })
            
            # Parse files
            all_drives = []
            parse_errors = []
            
            for file_path in collected_files:
                try:
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
            original_count = len(all_drives)
            unique_drives = collector.deduplicate_drives(all_drives)
            duplicates_removed = original_count - len(unique_drives)
            
            # Generate output files
            first_file_name = uploaded_files[0].name.split('.')[0] if uploaded_files else 'report'
            output_base = f"{first_file_name}_summary"
            
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
            
            # Create batch record
            batch = UploadBatch.objects.create(
                original_names=[f.name for f in uploaded_files],
                result_file=excel_path,
                total_reports=len(collected_files),
                total_drives=len(unique_drives)
            )
            
            # Save parse errors to database
            for error in parse_errors:
                ParseError.objects.create(
                    batch=batch,
                    file_name=error['file_name'],
                    error_message=error['error_message'],
                    encodings_tried=error['encodings_tried']
                )
            
            return render(request, 'reports/result.html', {
                'batch_id': batch.id,
                'files_processed': len(collected_files),
                'drives_parsed': len(unique_drives),
                'duplicates_removed': duplicates_removed,
                'errors': parse_errors,
                'excel_filename': f"{output_base}.xlsx",
                'csv_filename': f"{output_base}.csv"
            })
    
    except Exception as e:
        logger.error(f"Error processing files: {e}")
        return render(request, 'reports/result.html', {
            'error': f'Processing failed: {str(e)}',
            'files_processed': 0,
            'drives_parsed': 0,
            'duplicates_removed': 0
        })


def download_view(request, batch_id):
    """Download generated files (LEGACY)"""
    batch = get_object_or_404(UploadBatch, id=batch_id)
    file_type = request.GET.get('type', 'xlsx')
    
    if file_type == 'xlsx' and batch.result_file:
        file_path = batch.result_file.path
        filename = os.path.basename(file_path)
        
        with open(file_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response
    
    elif file_type == 'csv':
        # Generate CSV filename from Excel filename
        excel_filename = os.path.basename(batch.result_file.path)
        csv_filename = excel_filename.replace('.xlsx', '.csv')
        csv_path = os.path.join(os.path.dirname(batch.result_file.path), csv_filename)
        
        if os.path.exists(csv_path):
            with open(csv_path, 'rb') as f:
                response = HttpResponse(f.read(), content_type='text/csv')
                response['Content-Disposition'] = f'attachment; filename="{csv_filename}"'
                return response
    
    raise Http404("File not found")
