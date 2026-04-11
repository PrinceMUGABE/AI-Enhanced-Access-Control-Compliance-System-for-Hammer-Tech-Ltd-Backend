# userApp/middleware.py

import time
from django.utils.deprecation import MiddlewareMixin
from .utils import ActivityLogger

class ActivityLoggingMiddleware(MiddlewareMixin):
    """Middleware to log all user activities"""
    
    def process_view(self, request, view_func, view_args, view_kwargs):
        # Attach start time to request for duration calculation
        request._activity_start_time = time.time()
        return None
    
    def process_response(self, request, response):
        # Skip logging for certain paths
        excluded_paths = ['/admin/', '/static/', '/media/', '/favicon.ico']
        if any(request.path.startswith(path) for path in excluded_paths):
            return response
        
        # Skip if user is not authenticated (except for auth endpoints)
        if not request.user.is_authenticated and not request.path.startswith('/api/auth/'):
            return response
        
        # Calculate duration
        duration = None
        if hasattr(request, '_activity_start_time'):
            duration = time.time() - request._activity_start_time
        
        # Map view to activity type
        activity_type = self._get_activity_type(request.path, request.method)
        
        if activity_type:
            ActivityLogger.create_log(
                user=request.user if request.user.is_authenticated else None,
                log_type=activity_type['log_type'],
                activity=activity_type['activity'],
                description=activity_type['description'],
                request=request,
                response=response,
                is_success=response.status_code < 400,
                start_time=getattr(request, '_activity_start_time', None)
            )
        
        return response
    
    def _get_activity_type(self, path, method):
        """Map API endpoints to activity types"""
        activity_map = {
            # Authentication
            '/api/auth/login/otp/request/': {
                'log_type': 'authentication',
                'activity': 'login_otp_request',
                'description': 'Requested OTP for login'
            },
            '/api/auth/login/otp/verify/': {
                'log_type': 'authentication',
                'activity': 'login_otp_verify',
                'description': 'Verified OTP for login'
            },
            '/api/auth/login/': {
                'log_type': 'authentication',
                'activity': 'login',
                'description': 'User login'
            },
            '/api/auth/logout/': {
                'log_type': 'authentication',
                'activity': 'logout',
                'description': 'User logout'
            },
            '/api/auth/register/': {
                'log_type': 'authentication',
                'activity': 'register',
                'description': 'User registration'
            },
            
            # Password management
            '/api/auth/password/reset/request/': {
                'log_type': 'profile',
                'activity': 'password_reset_request',
                'description': 'Requested password reset'
            },
            '/api/auth/password/reset/verify/': {
                'log_type': 'profile',
                'activity': 'password_reset_complete',
                'description': 'Completed password reset'
            },
            '/api/auth/password/change/': {
                'log_type': 'profile',
                'activity': 'password_change',
                'description': 'Changed password'
            },
            
            # Profile
            '/api/users/profile/': {
                'GET': {
                    'log_type': 'profile',
                    'activity': 'profile_view',
                    'description': 'Viewed profile'
                },
                'PUT': {
                    'log_type': 'profile',
                    'activity': 'profile_update',
                    'description': 'Updated profile'
                }
            },
            
            # User management
            '/api/users/': {
                'GET': {
                    'log_type': 'user_management',
                    'activity': 'user_list',
                    'description': 'Listed users'
                },
                'POST': {
                    'log_type': 'user_management',
                    'activity': 'user_create',
                    'description': 'Created user'
                }
            },
            
            # Contact us
            '/api/contact/': {
                'log_type': 'system',
                'activity': 'contact_us',
                'description': 'Submitted contact form'
            },
        }
        
        # Check exact path matches
        if path in activity_map:
            mapping = activity_map[path]
            if isinstance(mapping, dict) and method in mapping:
                return mapping[method]
            return mapping
        
        # Check pattern matches for user-specific endpoints
        if path.startswith('/api/users/'):
            parts = path.split('/')
            if len(parts) >= 4:
                user_id = parts[3]
                if user_id.isdigit():
                    if method == 'GET':
                        return {
                            'log_type': 'user_management',
                            'activity': 'user_view',
                            'description': f'Viewed user ID {user_id}'
                        }
                    elif method == 'PUT':
                        return {
                            'log_type': 'user_management',
                            'activity': 'user_update',
                            'description': f'Updated user ID {user_id}'
                        }
                    elif method == 'DELETE':
                        return {
                            'log_type': 'user_management',
                            'activity': 'user_delete',
                            'description': f'Deleted user ID {user_id}'
                        }
        
        return None