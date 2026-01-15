from django.urls import path
from . import views

urlpatterns = [
  
    path('modules/', views.get_onboarding_modules, name='get-onboarding-modules'),
    path('modules/create/', views.create_onboarding_module, name='create-onboarding-module'),
    path('modules/<int:pk>/', views.get_onboarding_module_detail, name='get-onboarding-module-detail'),
    path('modules/<int:pk>/update/', views.update_onboarding_module, name='update-onboarding-module'),
    path('modules/<int:pk>/delete/', views.delete_onboarding_module, name='delete-onboarding-module'),
    path('modules/statistics/', views.get_onboarding_statistics, name='get-onboarding-statistics'),
    path('modules/<int:pk>/assign/', views.assign_module_to_mentees, name='assign-module-to-mentees'),
    path('modules/<int:pk>/department-assign/', views.assign_module_to_department, name='assign-module-to-department'),
    path('modules/<int:pk>/mentee-progress/', views.get_module_mentee_progress, name='get-module-mentee-progress'),
    path('modules/by-department/', views.get_modules_by_department, name='get-modules-by-department'),
    path('modules/department/', views.get_department_modules, name='get-department-modules'),
    
    # New Department-focused URLs
    path('departments/summary/', views.get_department_modules_summary, name='get-department-modules-summary'),
    path('departments/<int:department_id>/progress/', views.get_department_progress_detail, name='get-department-progress-detail'),
    path('departments/<int:department_id>/summary/', views.get_department_modules_summary, name='get-department-specific-summary'),
    path('departments/comparison/', views.get_department_comparison, name='get-department-comparison'),
    path('modules/<int:module_id>/department-performance/', views.get_department_module_performance, name='get-department-module-performance'),
    
    path('progress/', views.get_mentee_progress, name='get-mentee-progress'),
    path('progress/<int:pk>/', views.get_mentee_progress_detail, name='get-mentee-progress-detail'),
    path('progress/<int:pk>/start/', views.start_onboarding_module, name='start-onboarding-module'),
    path('progress/<int:pk>/complete/', views.complete_onboarding_module, name='complete-onboarding-module'),
    path('progress/<int:pk>/update-percentage/', views.update_progress_percentage, name='update-progress-percentage'),
    path('progress/<int:pk>/update-details/', views.update_progress_details, name='update-progress-details'),
    path('progress/<int:pk>/update-checklist/', views.update_checklist_item, name='update-checklist-item'),
    path('mentees/<int:mentee_id>/remove/', views.remove_candidate_from_onboarding, name='remove-candidate-from-onboarding'),
    
    # Progress Summary
    path('progress/my-summary/', views.get_my_progress_summary, name='get-my-progress-summary'),
    path('progress/all-summary/', views.get_all_mentees_summary, name='get-all-mentees-summary'),
    path('progress/auto-assign/', views.auto_assign_modules, name='auto-assign-modules'),
    path('progress/upcoming-deadlines/', views.get_upcoming_deadlines, name='get-upcoming-deadlines'),
    path('progress/health/', views.check_progress_health, name='check-progress-health'),
    
    # Deadline Management
    path('progress/<int:progress_id>/extend-deadline/', views.extend_deadline, name='extend-deadline'),
    
    # Notifications
    path('notifications/', views.get_my_notifications, name='get-my-notifications'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark-notification-read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark-all-notifications-read'),

    path('reminder/send/', views.send_reminder, name='send-reminder'),

    path('modules/<int:pk>/upload-files/', views.upload_module_files, name='upload-module-files'),
    path('modules/<int:pk>/files/<str:file_id>/', views.delete_module_file, name='delete-module-file'),
    path('modules/<int:pk>/files/<str:file_id>/download/', views.download_module_file, name='download-module-file'),
]