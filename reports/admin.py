from django.contrib import admin
from .models import ParsingJob, UploadBatch, ParseError


@admin.register(ParsingJob)
class ParsingJobAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'total_files', 'total_drives', 'created_at', 'completed_at']
    list_filter = ['status', 'created_at']
    search_fields = ['id', 'task_id']
    readonly_fields = ['id', 'task_id', 'created_at', 'started_at', 'completed_at']
    ordering = ['-created_at']


@admin.register(UploadBatch)
class UploadBatchAdmin(admin.ModelAdmin):
    list_display = ['id', 'created_at', 'total_reports', 'total_drives']
    list_filter = ['created_at']
    search_fields = ['id']
    readonly_fields = ['id', 'created_at']
    ordering = ['-created_at']


@admin.register(ParseError)
class ParseErrorAdmin(admin.ModelAdmin):
    list_display = ['file_name', 'job', 'batch', 'created_at']
    list_filter = ['created_at']
    search_fields = ['file_name', 'error_message']
    readonly_fields = ['created_at']
    ordering = ['-created_at']
