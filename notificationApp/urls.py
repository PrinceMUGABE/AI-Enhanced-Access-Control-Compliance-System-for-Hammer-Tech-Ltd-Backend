from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    # Notification endpoints
    path('', views.NotificationListAPIView.as_view(), name='notification-list'),
    path('<int:id>/', views.NotificationDetailAPIView.as_view(), name='notification-detail'),
    path('counts/', views.get_notification_counts, name='notification-counts'),
    path('mark-read/', views.mark_notifications_read, name='mark-notifications-read'),
    path('mark-all-read/', views.mark_all_notifications_read, name='mark-all-notifications-read'),
    path('preferences/', views.get_preferences, name='get-preferences'),
    path('preferences/update/', views.update_preferences, name='update-preferences'),
    path('generate/', views.generate_notifications, name='generate-notifications'),
    path('trigger/', views.trigger_notification_generation, name='trigger-notification-generation'),
    

    path('clear-all/', views.clear_all_notifications, name='clear-all-notifications'),
    path('<int:notification_id>/delete/', views.delete_notification, name='delete-notification'),
]