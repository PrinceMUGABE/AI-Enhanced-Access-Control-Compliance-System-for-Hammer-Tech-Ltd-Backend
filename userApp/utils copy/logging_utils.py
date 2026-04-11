# userApp/utils/logging_utils.py
import socket
from django.utils import timezone
from userApp.models import UserLog, CustomUser
from shiftApp.models import Shift

def get_client_ip(request):
    """Get client IP address from request"""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip

def get_device_info(request):
    """Get device information from request"""
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    return user_agent[:255]  # Truncate if too long

def create_user_log(user, log_type, activity, status='on_time', 
                   scheduled_time=None, shift=None, break_log=None, 
                   request=None, is_auto=False, notes=None):
    """Create a user log entry"""
    
    # Generate system reason based on context
    system_reason = _generate_system_reason(user, log_type, scheduled_time)
    
    # Get IP and device info if request is provided
    ip_address = None
    device_info = None
    if request:
        ip_address = get_client_ip(request)
        device_info = get_device_info(request)
    
    log = UserLog.objects.create(
        user=user,
        log_type=log_type,
        status=status,
        activity=activity,
        system_generated_reason=system_reason,
        scheduled_time=scheduled_time,
        shift=shift,
        break_log=break_log,
        ip_address=ip_address,
        device_info=device_info,
        is_auto_generated=is_auto,
        notes=notes
    )
    
    return log

def _generate_system_reason(user, log_type, scheduled_time=None):
    """Generate system reason for log entry"""
    reasons = []
    
    # Check day off
    today = timezone.now().strftime('%A').lower()
    if user.day_off.lower() == today:
        reasons.append(f"User's scheduled day off ({user.day_off})")
    
    # Check if shift is assigned
    if user.current_shift:
        reasons.append(f"Assigned shift: {user.current_shift.name}")
    
    # Add timing information if scheduled_time is provided
    if scheduled_time:
        now = timezone.now()
        diff = (now - scheduled_time).total_seconds() / 60
        
        if abs(diff) > 1:  # If more than 1 minute difference
            if diff > 0:
                reasons.append(f"{abs(diff):.1f} minutes after scheduled time")
            else:
                reasons.append(f"{abs(diff):.1f} minutes before scheduled time")
    
    # Log type specific reasons
    if log_type == 'login':
        # Check if user should be working based on shift
        if user.current_shift:
            shift_start, shift_end = user.current_shift.get_datetime_range(timezone.now().date())
            
            if now < shift_start:
                reasons.append(f"Logging in before shift start ({shift_start.strftime('%H:%M')})")
            elif shift_start <= now <= shift_end:
                reasons.append("Logging in during shift hours")
            else:
                reasons.append(f"Logging in after shift end ({shift_end.strftime('%H:%M')})")
    
    return "; ".join(reasons) if reasons else "System recorded activity"

def calculate_login_status(user, login_time):
    """Calculate login status based on shift timing"""
    if not user.current_shift:
        return 'system_auto'
    
    shift_start, shift_end = user.current_shift.get_datetime_range(login_time.date())
    
    # Calculate time difference
    diff_minutes = (login_time - shift_start).total_seconds() / 60
    
    # Determine status
    if diff_minutes < -15:  # More than 15 minutes early
        return 'early'
    elif -15 <= diff_minutes <= 5:  # 15 minutes early to 5 minutes late
        return 'on_time'
    elif 5 < diff_minutes <= 30:  # 5-30 minutes late
        return 'late'
    else:  # More than 30 minutes late
        return 'very_late'

def auto_record_break_start(break_log):
    """Automatically record break start with system-generated logs"""
    from django.utils import timezone
    
    # Check if it's user's day off
    user = break_log.user
    today = timezone.now().strftime('%A').lower()
    
    if user.day_off.lower() == today:
        # User is on day off
        break_log.status = 'missed'
        break_log.system_generated_reason = f"User's scheduled day off ({user.day_off})"
        break_log.is_auto_recorded = True
        break_log.save()
        
        # Create user log
        create_user_log(
            user=user,
            log_type='break_start',
            activity=f"Break missed - {break_log.break_template.name}",
            status='day_off',
            scheduled_time=break_log.scheduled_start,
            break_log=break_log,
            is_auto=True,
            notes="Automatically recorded as missed due to day off"
        )
    else:
        # User should be working
        # Check if user is logged in
        # You need to implement a way to check if user is currently logged in
        # This could be done by checking active sessions or last activity
        
        # For now, we'll assume we can check from UserLog
        last_login = UserLog.objects.filter(
            user=user,
            log_type='login'
        ).order_by('-actual_time').first()
        
        last_logout = UserLog.objects.filter(
            user=user,
            log_type='logout'
        ).order_by('-actual_time').first()
        
        user_logged_in = False
        if last_login and last_logout:
            user_logged_in = last_login.actual_time > last_logout.actual_time
        elif last_login:
            user_logged_in = True
        
        # Update break log
        break_log.was_user_logged_in = user_logged_in
        
        # Determine break status
        now = timezone.now()
        scheduled_start = break_log.scheduled_start
        
        if now > scheduled_start + timezone.timedelta(minutes=30):
            # Break was missed
            break_log.status = 'missed'
            status = 'absent'
        elif scheduled_start <= now <= scheduled_start + timezone.timedelta(minutes=5):
            # Break is on time
            break_log.status = 'started'
            status = 'on_time'
            break_log.actual_start = now
        else:
            # Break is late
            break_log.status = 'started'
            status = 'late'
            break_log.actual_start = now
        
        break_log.save()
        
        # Create user log
        activity_status = "present" if user_logged_in else "absent"
        create_user_log(
            user=user,
            log_type='break_start',
            activity=f"Break {break_log.status} - User {activity_status}",
            status=status,
            scheduled_time=break_log.scheduled_start,
            break_log=break_log,
            is_auto=True,
            notes=f"User was {'logged in' if user_logged_in else 'not logged in'}"
        )