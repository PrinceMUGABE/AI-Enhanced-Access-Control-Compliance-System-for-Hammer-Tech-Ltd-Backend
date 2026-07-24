from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView

app_name = 'userApp'

urlpatterns = [
    # ============================================================
    # AUTHENTICATION ENDPOINTS
    # ============================================================
    path('auth/register/', views.register_user, name='auth-register'),
    path('auth/login-with-otp/request/', views.login_with_otp_request, name='auth-login-request'),
    path('auth/login-with-otp/verify/', views.login_with_otp_verify, name='auth-login-verify'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('auth/check-lock-status/', views.check_account_lock_status, name='check-lock-status'),
    path('auth/logout/', views.logout_user, name='auth-logout'),
    path('auth/verify-token/', views.verify_token, name='verify-token'),
    
    # Password Reset
    path('auth/password-reset/request-otp/', views.request_password_reset_otp, name='request-password-reset-otp'),
    path('auth/password-reset/verify-otp/', views.verify_reset_otp, name='verify-reset-otp'),
    path('auth/password-reset/confirm/', views.reset_password_with_otp, name='reset-password-with-otp'),
    path('profile/change-password/', views.change_password, name='profile-change-password'),
    
    # ============================================================
    # USER MANAGEMENT ENDPOINTS (Admin/HR only)
    # ============================================================
    path('users/', views.users_list_create, name='users-list-create'),
    path('users/<int:user_id>/', views.get_user_by_id, name='users-detail'),
    path('users/<int:user_id>/update/', views.update_user, name='users-update'),
    path('users/<int:user_id>/delete/', views.delete_or_deactivate_user, name='users-delete'),
    path('users/search/email/', views.get_user_by_email, name='users-search-email'),
    path('users/search/phone/', views.get_user_by_phone, name='users-search-phone'),
    path('users/mentors/', views.get_all_mentors, name='users-mentors'),
    path('users/mentees/', views.get_all_mentees, name='users-mentees'),
    path('users/<int:user_id>/activate/', views.activate_user, name='users-activate'),
    path('users/<int:user_id>/deactivate/', views.deactivate_user, name='users-deactivate'),
    path('users/<int:user_id>/status/', views.update_user_status, name='users-status'),
    
    # ============================================================
    # PROFILE ENDPOINTS
    # ============================================================
    path('profile/', views.get_current_user, name='profile-detail'),
    path('profile/update/', views.update_profile, name='profile-update'),
    
    # ============================================================
    # ACCESS CONTROL ENDPOINTS
    # ============================================================
    path('get_access_control_stats/', views.get_access_control_stats, name='access-control-stats'),
    path('access-control/users/', views.get_users_for_access_control, name='access-control-users'),
    path('access-control/users/<int:user_id>/logs/', views.get_user_activity_logs, name='user-activity-logs'),
    path('get_user_activity_logs/<int:user_id>/', views.get_user_activity_logs, name='get-user-activity-logs'),  # <-- added
    path('get_users_for_access_control/', views.get_users_for_access_control, name='get_users_for_access_control'),
        # ============================================================
    # ACTIVITY LOGS ENDPOINTS
    # ============================================================
    path('logs/', views.UserLogListAPIView.as_view(), name='user-logs-list'),
    path('logs/<int:pk>/', views.UserLogDetailAPIView.as_view(), name='user-log-detail'),
    path('logs/my/', views.get_my_activity_logs, name='my-activity-logs'),
    path('log_activity/', views.log_activity, name='log-activity'),
    
    # ============================================================
    # CONTACT ENDPOINT
    # ============================================================
    path('contact/', views.contact_us, name='contact'),
    
    # ============================================================
    # DEPARTMENT ENDPOINT
    # ============================================================
    path('my-departments/', views.get_my_departments, name='my-departments'),
    path('health/', views.health_check, name='health-check'),

]