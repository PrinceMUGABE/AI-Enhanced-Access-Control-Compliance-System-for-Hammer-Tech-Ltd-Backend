from django.urls import path
from . import views

urlpatterns = [
    # Department risk assessments
    path('departments/', views.get_department_risk_assessments, name='department-risk-assessments'),
    path('departments/<int:department_id>/', views.get_department_risk_detail, name='department-risk-detail'),
    
    # User risk profiles
    path('users/profiles/', views.get_user_risk_profiles, name='user-risk-profiles'),
    path('users/<int:user_id>/risk/', views.get_user_risk_profile_detail, name='user-risk-profile-detail'),
    
    # Security metrics
    path('metrics/', views.get_security_metrics, name='security-metrics'),
    
    # Risk trends
    path('trends/', views.get_risk_trends, name='risk-trends'),
    
    # Vulnerability assessment
    path('vulnerabilities/', views.get_vulnerability_assessment, name='vulnerability-assessment'),
    
    # Run comprehensive assessment
    path('run-assessment/', views.run_risk_assessment, name='run-risk-assessment'),
    
    # Dashboard data (for frontend)
    path('dashboard-data/', views.get_risk_dashboard_data, name='risk-dashboard-data'),
    
    # Summary and heatmap
    path('summary/', views.get_risk_summary, name='risk-summary'),
    path('heatmap/', views.get_risk_heatmap_data, name='risk-heatmap'),
]