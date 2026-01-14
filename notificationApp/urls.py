from django.urls import path
from . import views

urlpatterns = [
    # Profile Management
    path('profile/', views.get_user_profile, name='get_user_profile'),
    path('profile/update/', views.update_user_profile, name='update_user_profile'),
    
    # Add this missing endpoint for password change
    path('profile/change-password/', views.change_password, name='change_password'),
    
    # Notification Management - Add slash for root
    path('', views.list_user_notifications, name='list_user_notifications'),
    path('delete/', views.delete_notifications, name='delete_notifications'),
    path('<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    
    # Keep existing URLs for backward compatibility
    path('chat/', views.list_chat_notifications, name='list_chat_notifications'),
    path('chat/mark-read/', views.mark_chat_notifications_read, name='mark_chat_notifications_read'),
    path('chat/mark-all-read/', views.mark_all_chat_notifications_read, name='mark_all_chat_notifications_read'),
    path('chat/<int:notification_id>/archive/', views.archive_chat_notification, name='archive_chat_notification'),
    path('chat/archive-all-read/', views.archive_all_read_chat_notifications, name='archive_all_read_chat_notifications'),
    
    # System Notifications (Admin/HR only)
    path('system/', views.list_system_notifications, name='list_system_notifications'),
    path('system/create/', views.create_system_notification, name='create_system_notification'),
    path('system/<int:notification_id>/', views.get_system_notification, name='get_system_notification'),
    path('system/<int:notification_id>/update/', views.update_system_notification, name='update_system_notification'),
    path('system/<int:notification_id>/archive/', views.archive_system_notification, name='archive_system_notification'),
    
    # User Preferences
    path('preferences/', views.get_user_notification_preferences, name='get_user_notification_preferences'),
    path('preferences/update/', views.update_user_notification_preferences, name='update_user_notification_preferences'),
    
    # Notification Statistics (Admin/HR only)
    path('stats/', views.get_notification_statistics, name='get_notification_statistics'),
    path('logs/', views.get_notification_logs, name='get_notification_logs'),
]