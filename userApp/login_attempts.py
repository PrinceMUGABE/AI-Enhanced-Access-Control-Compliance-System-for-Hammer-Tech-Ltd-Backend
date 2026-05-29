# userApp/login_attempts.py

from datetime import timedelta
from django.utils.timezone import now
from django.core.cache import cache
from .utils import ActivityLogger

class LoginAttemptManager:
    """Manager for handling login attempts and account locking"""
    
    @staticmethod
    def check_login_attempts(user):
        """
        Check if user can attempt login
        Returns: (can_attempt, message, remaining_seconds)
        """
        if not user:
            return True, None, 0
        
        # Check if account is locked
        if user.is_account_locked():
            remaining = user.get_lock_remaining_seconds()
            minutes = remaining // 60
            seconds = remaining % 60
            
            if minutes > 0:
                message = f"Account is locked. Please try again in {minutes} minute(s) and {seconds} second(s)."
            else:
                message = f"Account is locked. Please try again in {seconds} second(s)."
            
            return False, message, remaining
        
        return True, None, 0
    
    @staticmethod
    def handle_failed_login(user, request=None):
        """
        Handle failed login attempt
        Returns: (is_locked, message, remaining_seconds)
        """
        if not user:
            return False, None, 0
        
        # Increment attempts and check if locked
        is_now_locked = user.increment_login_attempts()
        remaining_attempts = 3 - user.failed_login_attempts
        
        # Log the failed attempt
        ActivityLogger.log_authentication(
            user=user,
            activity='login_failed',
            description=f'Failed login attempt {user.failed_login_attempts}/3. {remaining_attempts} attempts remaining.',
            request=request,
            is_success=False
        )
        
        if is_now_locked:
            message = f"Account locked due to 3 failed attempts. Please try again in 3 minutes."
            ActivityLogger.log_authentication(
                user=user,
                activity='account_locked',
                description=f'Account locked due to 3 failed login attempts',
                request=request,
                is_success=False
            )
            return True, message, 180
        else:
            message = f"Invalid credentials. {remaining_attempts} attempt(s) remaining before account lock."
            return False, message, 0
    
    @staticmethod
    def handle_successful_login(user, request=None):
        """
        Handle successful login - reset all attempt counters
        """
        if user:
            # Reset login attempts
            previous_attempts = user.failed_login_attempts
            user.reset_login_attempts()
            
            # Log if account was previously locked
            if previous_attempts >= 3:
                ActivityLogger.log_authentication(
                    user=user,
                    activity='account_unlocked',
                    description=f'Account unlocked after successful login (previously had {previous_attempts} failed attempts)',
                    request=request,
                    is_success=True
                )
            
            return True
        return False