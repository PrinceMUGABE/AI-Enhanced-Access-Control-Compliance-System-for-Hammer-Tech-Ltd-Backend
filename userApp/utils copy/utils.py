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
    return ''.join(random.choices(string.digits, k=length))

def store_otp(email, otp, expiry_seconds=30):
    """Store OTP in cache with expiry"""
    cache_key = f"reset_otp_{email}"
    cache_data = {
        'otp': otp,
        'created_at': datetime.now().isoformat(),
        'attempts': 0
    }
    cache.set(cache_key, cache_data, timeout=expiry_seconds)
    logger.info(f"OTP stored in cache with key: {cache_key}")
    return cache_key

def verify_otp(email, user_otp):
    """Verify OTP and increment attempts"""
    cache_key = f"reset_otp_{email}"
    otp_data = cache.get(cache_key)
    
    if not otp_data:
        return False, "OTP has expired or was not found. Please request a new OTP."
    
    # Check attempts (limit to 3 attempts)
    if otp_data.get('attempts', 0) >= 3:
        cache.delete(cache_key)
        return False, "Maximum attempts exceeded. Please request a new OTP."
    
    # Update attempts
    otp_data['attempts'] = otp_data.get('attempts', 0) + 1
    
    # Get remaining TTL to preserve expiry time
    remaining_ttl = cache.ttl(cache_key)
    if remaining_ttl > 0:
        cache.set(cache_key, otp_data, timeout=remaining_ttl)
    
    if otp_data['otp'] != user_otp:
        remaining_attempts = 3 - otp_data['attempts']
        return False, f"Invalid OTP code. {remaining_attempts} attempts remaining."
    
    # OTP is valid - keep it in cache for password reset
    # Don't delete yet, as we need it for the final password reset step
    return True, "OTP verified successfully"


def send_login_otp_to_email(user, otp):
    """Send login OTP email to user"""
    try:
        subject = "Login Verification OTP - TimeSync System"
        message = f"""
Hello {user.full_name},

You have requested to login to the TimeSync System.

Your OTP (One-Time Password) is: {otp}

⏰ This OTP will expire in 30 seconds.

If you did not request this login, please ignore this email or contact support immediately.

Best regards,
TimeSync System Team

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
        
        logger.info(f"Login OTP email sent successfully to {user.email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send login OTP email to {user.email}: {str(e)}")
        return False


def send_otp_email(user, otp):
    """Send OTP email to user"""
    try:
        subject = "Password Reset OTP - TimeSync System"
        message = f"""
Hello {user.full_name},

You have requested to reset your password for the TimeSync System.

Your OTP (One-Time Password) is: {otp}

⏰ This OTP will expire in 30 seconds.

If you did not request this password reset, please ignore this email or contact support immediately.

Best regards,
TimeSync System Team

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
        return True
        
    except Exception as e:
        logger.error(f"Failed to send OTP email to {user.email}: {str(e)}")
        return False
    


