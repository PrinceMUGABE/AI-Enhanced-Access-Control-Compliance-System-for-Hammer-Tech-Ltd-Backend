# userApp/utils.py
import random
import string
from datetime import datetime
from django.core.cache import cache
from django.core.mail import send_mail
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

def generate_otp(length=6):
    """Generate a random OTP of specified length"""
    otp = ''.join(random.choices(string.digits, k=length))
    print(f"\n{'='*60}")
    print(f"OTP GENERATED: {otp}")
    print(f"{'='*60}\n")
    return otp

def store_otp(work_mail, otp, expiry_seconds=30):
    """Store OTP in cache with expiry"""
    cache_key = f"reset_otp_{work_mail}"
    cache_data = {
        'otp': otp,
        'created_at': datetime.now().isoformat(),
        'attempts': 0
    }
    
    print(f"\n{'='*60}")
    print(f"STORING OTP IN CACHE")
    print(f"Cache Key: {cache_key}")
    print(f"OTP Value: {otp}")
    print(f"Expiry: {expiry_seconds} seconds")
    print(f"Full Cache Data: {cache_data}")
    print(f"{'='*60}\n")
    
    cache.set(cache_key, cache_data, timeout=expiry_seconds)
    
    # Verify it was stored correctly
    stored_data = cache.get(cache_key)
    print(f"\n{'='*60}")
    print(f"VERIFICATION - OTP STORED SUCCESSFULLY")
    print(f"Retrieved from cache: {stored_data}")
    print(f"OTP matches: {stored_data.get('otp') == otp if stored_data else 'NOT FOUND'}")
    print(f"{'='*60}\n")
    
    logger.info(f"OTP stored in cache with key: {cache_key}")
    return cache_key

def verify_otp(work_mail, user_otp):
    """Verify OTP and increment attempts"""
    cache_key = f"reset_otp_{work_mail}"
    
    print(f"\n{'='*60}")
    print(f"VERIFYING OTP")
    print(f"Cache Key: {cache_key}")
    print(f"User Submitted OTP: {user_otp}")
    print(f"{'='*60}\n")
    
    otp_data = cache.get(cache_key)
    
    print(f"\n{'='*60}")
    print(f"OTP DATA RETRIEVED FROM CACHE")
    print(f"Cache Data: {otp_data}")
    if otp_data:
        print(f"Stored OTP: {otp_data.get('otp')}")
        print(f"Current Attempts: {otp_data.get('attempts', 0)}")
        print(f"Created At: {otp_data.get('created_at')}")
    else:
        print(f"NO DATA FOUND IN CACHE!")
    print(f"{'='*60}\n")
    
    if not otp_data:
        return False, "OTP has expired or was not found. Please request a new OTP."
    
    # Check attempts (limit to 3 attempts)
    if otp_data.get('attempts', 0) >= 3:
        cache.delete(cache_key)
        print(f"\n⚠️ Maximum attempts exceeded for {work_mail}\n")
        return False, "Maximum attempts exceeded. Please request a new OTP."
    
    # Update attempts
    otp_data['attempts'] = otp_data.get('attempts', 0) + 1
    
    # Get remaining TTL to preserve expiry time
    remaining_ttl = cache.ttl(cache_key)
    if remaining_ttl > 0:
        cache.set(cache_key, otp_data, timeout=remaining_ttl)
    
    print(f"\n{'='*60}")
    print(f"OTP COMPARISON")
    print(f"Stored OTP:    '{otp_data['otp']}'")
    print(f"Submitted OTP: '{user_otp}'")
    print(f"Match: {otp_data['otp'] == user_otp}")
    print(f"Attempt #{otp_data['attempts']}")
    print(f"{'='*60}\n")
    
    if otp_data['otp'] != user_otp:
        remaining_attempts = 3 - otp_data['attempts']
        print(f"\n❌ OTP MISMATCH - {remaining_attempts} attempts remaining\n")
        return False, f"Invalid OTP code. {remaining_attempts} attempts remaining."
    
    # OTP is valid - keep it in cache for password reset
    # Don't delete yet, as we need it for the final password reset step
    print(f"\n✅ OTP VERIFIED SUCCESSFULLY\n")
    return True, "OTP verified successfully"

def send_otp_email(user, otp):
    """Send OTP email to user"""
    try:
        print(f"\n{'='*60}")
        print(f"SENDING OTP EMAIL")
        print(f"Recipient: {user.email}")
        print(f"User Name: {user.full_name}")
        print(f"OTP Being Sent: {otp}")
        print(f"{'='*60}\n")
        
        subject = "Password Reset OTP - Hammer Tech AI-Enhanced Access Control & Compliance System"
        message = f"""
Hello {user.full_name},

You have requested to reset your password for the Hammer Tech AI-Enhanced Access Control & Compliance System.

Your OTP (One-Time Password) is: {otp}

⏰ This OTP will expire in 30 seconds.

If you did not request this password reset, please ignore this email or contact support immediately.

Best regards,
HammerTech Support Team

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This is an automated message. Please do not reply to this email.
        """
        
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        
        logger.info(f"OTP email sent successfully to {user.email}")
        print(f"\n✅ OTP EMAIL SENT SUCCESSFULLY to {user.email}\n")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send OTP email to {user.email}: {str(e)}")
        print(f"\n❌ FAILED TO SEND OTP EMAIL: {str(e)}\n")
        return False
    







# userApp/utils.py - Add or update with ActivityLogger
import time
from django.utils.timezone import now
from .models import UserLog



import time
from django.utils.timezone import now
from .models import UserLog, CustomUser
from rest_framework.response import Response
from datetime import timedelta

class ActivityLogger:
    """Utility class for logging user activities"""
    
    @staticmethod
    def create_log(
        user=None,
        log_type=None,
        activity=None,
        description="",
        request=None,
        response=None,
        target_user=None,
        target_department=None,
        is_success=True,
        is_auto_generated=False,
        start_time=None
    ):
        """
        Create a user activity log entry
        
        Args:
            user: The user performing the action
            log_type: Type of activity (authentication, profile, etc.)
            activity: Specific activity name
            description: Human-readable description
            request: Django request object (optional)
            response: Django response object (optional)
            target_user: User affected by this action (optional)
            target_department: Department affected (optional)
            is_success: Whether action was successful
            is_auto_generated: If log was auto-generated by system
            start_time: Start time for calculating duration
        """
        try:
            log_data = {
                'user': user,
                'log_type': log_type,
                'activity': activity,
                'description': description,
                'is_success': is_success,
                'is_auto_generated': is_auto_generated,
                'timestamp': now(),
            }
            
            # Add user info
            if user:
                log_data['user_email'] = user.email
                log_data['user_role'] = user.role
            elif request and hasattr(request, 'user') and request.user.is_authenticated:
                log_data['user'] = request.user
                log_data['user_email'] = request.user.email
                log_data['user_role'] = request.user.role
            
            # Add target information
            if target_user:
                log_data['target_user'] = target_user
            if target_department:
                log_data['target_department'] = target_department
            
            # Extract request information
            if request:
                log_data['ip_address'] = ActivityLogger.get_client_ip(request)
                log_data['user_agent'] = request.META.get('HTTP_USER_AGENT', '')
                log_data['endpoint'] = request.path
                log_data['http_method'] = request.method
                
                # Store request data (safely, excluding sensitive info)
                if request.method in ['POST', 'PUT', 'PATCH'] and hasattr(request, 'data'):
                    request_data = dict(request.data)
                    # Remove sensitive information
                    sensitive_fields = ['password', 'confirm_password', 'current_password', 
                                       'new_password', 'otp', 'token', 'refresh']
                    for field in sensitive_fields:
                        if field in request_data:
                            request_data[field] = '***HIDDEN***'
                    log_data['request_data'] = request_data
            
            # Extract response information
            if response:
                log_data['status_code'] = response.status_code
                if hasattr(response, 'data'):
                    response_data = dict(response.data)
                    # Hide sensitive information in response
                    sensitive_fields = ['token', 'refresh', 'access', 'password']
                    for field in sensitive_fields:
                        if field in response_data:
                            response_data[field] = '***HIDDEN***'
                    log_data['response_data'] = response_data
            
            # Calculate duration if start_time provided
            if start_time:
                if isinstance(start_time, (int, float)):
                    duration_seconds = time.time() - start_time
                    log_data['duration'] = timedelta(seconds=duration_seconds)
                else:
                    duration = now() - start_time
                    log_data['duration'] = duration
            
            # Create the log entry
            log_entry = UserLog.objects.create(**log_data)
            return log_entry
            
        except Exception as e:
            # Log the error but don't break the application
            print(f"Error creating activity log: {str(e)}")
            return None
    
    @staticmethod
    def get_client_ip(request):
        """Extract client IP address from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @staticmethod
    def log_authentication(user, activity, description, request=None, response=None, **kwargs):
        """Helper for authentication logs"""
        return ActivityLogger.create_log(
            user=user,
            log_type='authentication',
            activity=activity,
            description=description,
            request=request,
            response=response,
            **kwargs
        )
    
    @staticmethod
    def log_profile(user, activity, description, request=None, response=None, **kwargs):
        """Helper for profile-related logs"""
        return ActivityLogger.create_log(
            user=user,
            log_type='profile',
            activity=activity,
            description=description,
            request=request,
            response=response,
            **kwargs
        )
    
    @staticmethod
    def log_user_management(user, activity, description, request=None, response=None, target_user=None, **kwargs):
        """Helper for user management logs"""
        return ActivityLogger.create_log(
            user=user,
            log_type='user_management',
            activity=activity,
            description=description,
            request=request,
            response=response,
            target_user=target_user,
            **kwargs
        )
    
    @staticmethod
    def log_department(user, activity, description, request=None, response=None, target_department=None, **kwargs):
        """Helper for department management logs"""
        return ActivityLogger.create_log(
            user=user,
            log_type='department',
            activity=activity,
            description=description,
            request=request,
            response=response,
            target_department=target_department,
            **kwargs
        )
    
    @staticmethod
    def log_system(user, activity, description, request=None, response=None, **kwargs):
        """Helper for system activity logs"""
        return ActivityLogger.create_log(
            user=user,
            log_type='system',
            activity=activity,
            description=description,
            request=request,
            response=response,
            **kwargs
        )