from django.urls import path
from . import views

urlpatterns = [
    # Standards
    path('standards/', views.ComplianceStandardViewSet.as_view(), name='compliance-standards'),
    path('standards/<int:standard_id>/', views.standard_detail, name='compliance-standard-detail'),
    
    # Audits
    path('audits/', views.ComplianceAuditViewSet.as_view(), name='compliance-audits'),
    path('audits/<int:audit_id>/', views.audit_detail, name='compliance-audit-detail'),
    path('audits/from-incident/', views.create_incident_based_audit, name='create-incident-audit'),
    
    # Findings
    path('findings/', views.AuditFindingViewSet.as_view(), name='compliance-findings'),
    
    # Control Assessments
    path('controls/', views.ControlAssessmentViewSet.as_view(), name='compliance-controls'),
    
    # Dashboard & Statistics
    path('dashboard/', views.compliance_dashboard, name='compliance-dashboard'),
    
    # Incident-related endpoints
    path('incidents/<int:incident_id>/audits/', views.get_incident_audits, name='incident-audits'),
    
    # Report generation endpoints - FIXED: Use the actual function names
    
    path('reports/', views.list_reports, name='list-reports'),
    path('reports/generate/', views.generate_report, name='generate-report'),
    path('reports/<int:report_id>/download/', views.download_report, name='download-report'),
    path('reports/delete/<str:report_id>/', views.delete_report, name='delete_report'),
]