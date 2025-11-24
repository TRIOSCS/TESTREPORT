from django.urls import path
from . import views

urlpatterns = [
    # Main upload view
    path('', views.upload_view, name='upload'),
    
    # Job management
    path('jobs/', views.job_list_view, name='job_list'),
    path('jobs/<uuid:job_id>/', views.job_status_view, name='job_status'),
    path('jobs/<uuid:job_id>/status/', views.job_status_api, name='job_status_api'),
    path('download/<uuid:job_id>/', views.download_job_result, name='download_job'),
    
    # Legacy endpoints (backward compatibility)
    path('parse/', views.parse_files, name='parse'),
    path('download-batch/<uuid:batch_id>/', views.download_view, name='download'),
]
