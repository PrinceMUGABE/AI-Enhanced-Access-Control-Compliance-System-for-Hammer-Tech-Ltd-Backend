# reportApp/urls.py

from django.urls import path
from . import views

app_name = 'reportApp'

urlpatterns = [
    # ==================== ADMIN URLS ====================
    path('admin/dashboard/', 
         views.admin_dashboard_overview, 
         name='admin_dashboard_overview'),
    
    path('admin/users/analytics/', 
         views.admin_user_analytics, 
         name='admin_user_analytics'),
    
    path('admin/departments/', 
         views.admin_department_report, 
         name='admin_department_report'),
    
    # ==================== HR URLS ====================
    path('hr/dashboard/', 
         views.hr_dashboard_overview, 
         name='hr_dashboard_overview'),
    
    path('hr/onboarding/', 
         views.hr_onboarding_report, 
         name='hr_onboarding_report'),
    
    # ==================== MENTOR URLS ====================
    path('mentor/dashboard/', 
         views.mentor_dashboard_overview, 
         name='mentor_dashboard_overview'),
    
    path('mentor/mentees/progress/', 
         views.mentor_mentee_progress, 
         name='mentor_mentee_progress'),
    
    # ==================== MENTEE URLS ====================
    path('mentee/dashboard/', 
         views.mentee_dashboard_overview, 
         name='mentee_dashboard_overview'),
    
    path('mentee/onboarding/', 
         views.mentee_onboarding_detail, 
         name='mentee_onboarding_detail'),
    
    path('mentee/sessions/', 
         views.mentee_session_history, 
         name='mentee_session_history'),

     path('generate/', 
         views.generate_report, 
         name='generate_report'),
    
    path('export/', 
         views.export_report, 
         name='export_report'),
]