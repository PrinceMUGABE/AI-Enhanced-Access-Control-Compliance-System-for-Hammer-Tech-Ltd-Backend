# urls.py (RESTful version)

from django.urls import path
from . import views
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    # Authentication
    path('auth/register/', views.register_user, name='auth-register'),
    path('auth/login/', views.login_user, name='auth-login'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    
    
    # Users resource (admin/HR)
    path('users/', views.users_list_create, name='users-list-create'),
    path('users/<int:user_id>/', views.get_user_by_id, name='users-detail'),
    path('users/<int:user_id>/update/', views.update_user, name='users-update'),
    path('users/<int:user_id>/delete/', views.delete_or_deactivate_user, name='users-delete'),
    path('users/search/email/', views.get_user_by_email, name='users-search-email'),
    path('users/search/phone/', views.get_user_by_phone, name='users-search-phone'),
    path('users/mentors/', views.get_all_mentors, name='users-mentors'),
    path('users/mentees/', views.get_all_mentees, name='users-mentees'),
    
    # User status management
    path('users/<int:user_id>/activate/', views.activate_user, name='users-activate'),
    path('users/<int:user_id>/deactivate/', views.deactivate_user, name='users-deactivate'),
    path('users/<int:user_id>/status/', views.update_user_status, name='users-status'),
    
    # Current user profile
    path('profile/', views.get_current_user, name='profile-detail'),
    path('profile/update/', views.update_profile, name='profile-update'),
    
    # Contact
    path('contact/', views.contact_us, name='contact'),


    path('auth/password-reset/request-otp/', views.request_password_reset_otp, name='request-password-reset-otp'),
    path('auth/password-reset/verify-otp/', views.verify_reset_otp, name='verify-reset-otp'),
    path('auth/password-reset/confirm/', views.reset_password_with_otp, name='reset-password-with-otp'),
    path('profile/change-password/', views.change_password, name='profile-change-password'),

    path('auth/logout/', views.logout_user, name='auth-logout'),
    path('auth/verify-token/', views.verify_token, name='verify-token'),
]