from django.urls import path
from . import views

app_name = 'incidents'

urlpatterns = [
    # Incident URLs
    path('', views.IncidentListCreateAPIView.as_view(), name='incident-list-create'),
    path('<int:id>/', views.IncidentDetailAPIView.as_view(), name='incident-detail'),
    path('from-log/', views.create_incident_from_log, name='create-incident-from-log'),
    path('my/', views.get_user_incidents, name='my-incidents'),
    path('danger-zone/', views.get_danger_zone_logs, name='danger-zone-logs'),
    path('<int:incident_id>/comments/', views.add_incident_comment, name='add-incident-comment'),
    path('<int:incident_id>/comments/all/', views.get_incident_comments, name='get-incident-comments'),
    path('<int:incident_id>/attachments/', views.get_incident_attachments, name='get-incident-attachments'),
    path('<int:incident_id>/attachments/upload/', views.upload_incident_attachment, name='upload-incident-attachment'),
    path('<int:incident_id>/escalate/', views.escalate_incident, name='escalate-incident'),
    path('<int:incident_id>/timeline/', views.get_incident_timeline, name='get-incident-timeline'),
    path('statistics/', views.get_incident_statistics, name='incident-statistics'),
    
    # Report URLs
    path('reports/', views.ReportListCreateAPIView.as_view(), name='report-list-create'),
    path('reports/generate/', views.generate_report, name='generate-report'),
    path('reports/<int:report_id>/download/', views.download_report, name='download-report'),
    path('reports/types/', views.get_report_types, name='report-types'),
    path('reports/<int:report_id>/file/', views.download_report_file, name='download-report-file'),
    
    # Export URLs
    path('export/', views.export_incidents, name='export-incidents'),
    
    # Notification URLs
    path('<int:incident_id>/notify/', views.send_incident_notification, name='send-incident-notification'),
    
    # Danger zone URLs
    path('danger-zone/summary/', views.get_danger_zone_summary, name='danger-zone-summary'),
    
    # Manual assignment and SLA URLs
    path('incidents/manual-assign/', views.manual_assign_incident, name='incident-manual-assign'),
    path('<int:incident_id>/update-sla/', views.update_incident_sla, name='incident-update-sla'),
    
    # Assignable users URLs (two versions - with and without incident_id)
    path('assignable-users/', views.get_assignable_users, name='assignable-users'),
    path('incidents/<int:incident_id>/assignable-users/', views.get_assignable_users, name='incident-assignable-users'),
    
    # Tracking endpoints
    path('<int:incident_id>/tracking/', views.get_incident_tracking, name='incident-tracking'),
    
    # Trigger detection
    path('trigger-detection/', views.trigger_incident_detection, name='trigger-incident-detection'),


    path('assigned/check/', views.check_assigned_incidents, name='check-assigned-incidents'),
    path('assigned/update-status/', views.update_assigned_incident_status, name='update-assigned-incident-status'),
    path('assigned/my-incidents/', views.get_my_assigned_incidents, name='get-my-assigned-incidents'),
]