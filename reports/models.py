import uuid
from django.db import models
from django.contrib.postgres.fields import JSONField


class ParsingJob(models.Model):
    """Track async parsing jobs"""
    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Input files
    uploaded_files = models.JSONField(default=list)  # List of file names
    
    # Results
    result_excel = models.FileField(upload_to='results/', max_length=500, null=True, blank=True)
    result_csv = models.FileField(upload_to='results/', max_length=500, null=True, blank=True)
    total_files = models.IntegerField(default=0)
    total_drives = models.IntegerField(default=0)
    duplicates_removed = models.IntegerField(default=0)
    
    # Error tracking
    error_message = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Job {self.id} - {self.status}"


class UploadBatch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    original_names = models.JSONField(default=list)
    result_file = models.FileField(upload_to='results/', null=True, blank=True)
    error_file = models.FileField(upload_to='errors/', null=True, blank=True)
    total_reports = models.IntegerField(default=0)
    total_drives = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-created_at']


class ParseError(models.Model):
    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE, related_name='errors', null=True, blank=True)
    job = models.ForeignKey(ParsingJob, on_delete=models.CASCADE, related_name='errors', null=True, blank=True)
    file_name = models.CharField(max_length=255)
    error_message = models.TextField()
    encodings_tried = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']