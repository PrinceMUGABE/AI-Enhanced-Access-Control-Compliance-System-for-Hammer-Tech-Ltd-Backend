from django.urls import path
from . import views

urlpatterns = [
    # Standards
    path('standards/', views.ComplianceStandardViewSet.as_view(), name='compliance-standards'),
    path('standards/<int:standard_id>/', views.standard_detail, name='compliance-standard-detail'),
    
    # Audits
    path('audits/', views.ComplianceAuditViewSet.as_view(), name='compliance-audits'),
    path('audits/<int:audit_id>/', views.audit_detail, name='compliance-audit-detail'),
    path('audits/<int:audit_id>/check-completion/', views.check_audit_completion_readiness, name='check-audit-completion'),
    
    # Findings
    path('findings/', views.AuditFindingViewSet.as_view(), name='compliance-findings'),
    path('findings/<int:finding_id>/', views.finding_detail, name='finding-detail'),
    
    # Control Assessments
    path('controls/', views.ControlAssessmentViewSet.as_view(), name='compliance-controls'),
    path('controls/<int:control_id>/', views.control_detail, name='control-detail'),
    
    # Dashboard & Statistics
    path('dashboard/', views.compliance_dashboard, name='compliance-dashboard'),
    
    # Incident-related endpoints
    path('incidents/for-audit/', views.get_incidents_for_audit, name='incidents-for-audit'),
    path('incidents/<int:incident_id>/audits/', views.get_incident_audits, name='incident-audits'),
    path('incidents/completed/<int:incident_id>/delete/', views.delete_completed_incident, name='delete-completed-incident'),
    
    # Report endpoints
    path('reports/', views.list_reports, name='list-reports'),
    path('reports/by-role/', views.get_reports_by_role, name='reports-by-role'),
    path('reports/generate/', views.generate_report, name='generate-report'),
    path('reports/<int:report_id>/download/', views.download_report, name='download-report'),
    path('reports/delete/<str:report_id>/', views.delete_report, name='delete_report'),
]