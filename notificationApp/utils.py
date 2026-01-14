# mentorshipApp/utils/notifications.py
from django.utils import timezone
from datetime import timedelta
from notificationApp.models import ChatNotification
from chatApp.models import ChatRoom
from userApp.models import CustomUser
import logging

logger = logging.getLogger(__name__)

def send_session_scheduled_notification(session):
    """Send notification about scheduled session"""
    try:
        # Create notification for mentee
        ChatNotification.objects.create(
            recipient=session.mentorship.mentee,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_scheduled',
            title='New Session Scheduled',
            message=f'Session {session.program_session_number}: {session.session_template.title} scheduled for {session.scheduled_date.strftime("%Y-%m-%d %H:%M")}',
            metadata={
                'session_id': session.id,
                'mentorship_id': session.mentorship.id,
                'scheduled_date': session.scheduled_date.isoformat(),
                'program_name': session.program.name if session.program else 'Unknown Program',
                'session_title': session.session_template.title if session.session_template else 'Session'
            }
        )
        
        # Also send to mentor for confirmation
        ChatNotification.objects.create(
            recipient=session.mentorship.mentor,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_scheduled',
            title='Session Scheduled',
            message=f'You scheduled Session {session.program_session_number} with {session.mentorship.mentee.full_name} for {session.scheduled_date.strftime("%Y-%m-%d %H:%M")}',
            metadata={
                'session_id': session.id,
                'mentee_name': session.mentorship.mentee.full_name,
                'scheduled_date': session.scheduled_date.isoformat(),
                'program_name': session.program.name if session.program else 'Unknown Program'
            }
        )
        
        logger.info(f"Session scheduled notification sent for session {session.id}")
        
    except Exception as e:
        logger.error(f"Error sending session scheduled notification: {str(e)}")


def send_session_completed_notification(session):
    """Send notification about completed session"""
    try:
        # Notification for mentee
        ChatNotification.objects.create(
            recipient=session.mentorship.mentee,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_completed',
            title='Session Completed',
            message=f'Session {session.program_session_number}: {session.session_template.title} has been marked as completed',
            metadata={
                'session_id': session.id,
                'mentorship_id': session.mentorship.id,
                'completed_by': session.completed_by.full_name if session.completed_by else 'System',
                'program_name': session.program.name if session.program else 'Unknown Program',
                'program_progress': get_program_progress_percentage(session.mentorship, session.program)
            }
        )
        
        # Notification for mentor
        ChatNotification.objects.create(
            recipient=session.mentorship.mentor,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_completed',
            title='Session Completed',
            message=f'Session {session.program_session_number} with {session.mentorship.mentee.full_name} has been marked as completed',
            metadata={
                'session_id': session.id,
                'mentee_name': session.mentorship.mentee.full_name,
                'program_progress': get_program_progress_percentage(session.mentorship, session.program),
                'total_sessions_completed': get_total_sessions_completed(session.mentorship)
            }
        )
        
        logger.info(f"Session completed notification sent for session {session.id}")
        
    except Exception as e:
        logger.error(f"Error sending session completed notification: {str(e)}")


def send_session_cancelled_notification(session, reason):
    """Send notification about cancelled session"""
    try:
        # Determine who cancelled
        cancelled_by = session.completed_by.full_name if session.completed_by else 'System'
        
        # Notification for mentee
        ChatNotification.objects.create(
            recipient=session.mentorship.mentee,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_cancelled',
            title='Session Cancelled',
            message=f'Session {session.program_session_number}: {session.session_template.title} has been cancelled by {cancelled_by}',
            metadata={
                'session_id': session.id,
                'mentorship_id': session.mentorship.id,
                'cancelled_by': cancelled_by,
                'reason': reason,
                'original_date': session.scheduled_date.isoformat(),
                'program_name': session.program.name if session.program else 'Unknown Program'
            }
        )
        
        # Notification for mentor
        ChatNotification.objects.create(
            recipient=session.mentorship.mentor,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_cancelled',
            title='Session Cancelled',
            message=f'Session {session.program_session_number} with {session.mentorship.mentee.full_name} has been cancelled',
            metadata={
                'session_id': session.id,
                'mentee_name': session.mentorship.mentee.full_name,
                'reason': reason,
                'cancelled_by': cancelled_by
            }
        )
        
        logger.info(f"Session cancelled notification sent for session {session.id}")
        
    except Exception as e:
        logger.error(f"Error sending session cancelled notification: {str(e)}")


def send_session_rescheduled_notification(session, old_date):
    """Send notification about rescheduled session"""
    try:
        # Calculate time difference
        time_diff = session.scheduled_date - old_date
        days_diff = time_diff.days
        hours_diff = time_diff.seconds // 3600
        
        time_change_text = ""
        if days_diff != 0:
            time_change_text = f"{abs(days_diff)} day(s) {'later' if days_diff > 0 else 'earlier'}"
        elif hours_diff != 0:
            time_change_text = f"{abs(hours_diff)} hour(s) {'later' if hours_diff > 0 else 'earlier'}"
        else:
            time_change_text = "at the same time"
        
        # Notification for mentee
        ChatNotification.objects.create(
            recipient=session.mentorship.mentee,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_rescheduled',
            title='Session Rescheduled',
            message=f'Session {session.program_session_number}: {session.session_template.title} has been rescheduled to {session.scheduled_date.strftime("%Y-%m-%d %H:%M")}',
            metadata={
                'session_id': session.id,
                'mentorship_id': session.mentorship.id,
                'old_date': old_date.isoformat(),
                'new_date': session.scheduled_date.isoformat(),
                'time_change': time_change_text,
                'program_name': session.program.name if session.program else 'Unknown Program',
                'session_title': session.session_template.title if session.session_template else 'Session'
            }
        )
        
        # Notification for mentor
        ChatNotification.objects.create(
            recipient=session.mentorship.mentor,
            chat_room=get_chat_room(session.mentorship),
            notification_type='session_rescheduled',
            title='Session Rescheduled',
            message=f'Session {session.program_session_number} with {session.mentorship.mentee.full_name} has been rescheduled',
            metadata={
                'session_id': session.id,
                'mentee_name': session.mentorship.mentee.full_name,
                'old_date': old_date.strftime("%Y-%m-%d %H:%M"),
                'new_date': session.scheduled_date.strftime("%Y-%m-%d %H:%M"),
                'time_change': time_change_text
            }
        )
        
        logger.info(f"Session rescheduled notification sent for session {session.id}")
        
    except Exception as e:
        logger.error(f"Error sending session rescheduled notification: {str(e)}")


def send_upcoming_session_reminder(session):
    """Send reminder for upcoming session (24 hours before)"""
    try:
        # Calculate time until session
        time_until = session.scheduled_date - timezone.now()
        hours_until = time_until.total_seconds() / 3600
        
        if 23 <= hours_until <= 25:  # Send 24 hour reminder
            # Notification for mentee
            ChatNotification.objects.create(
                recipient=session.mentorship.mentee,
                chat_room=get_chat_room(session.mentorship),
                notification_type='session_reminder',
                title='Session Reminder - Tomorrow',
                message=f'Reminder: Session {session.program_session_number}: {session.session_template.title} is scheduled for tomorrow at {session.scheduled_date.strftime("%H:%M")}',
                metadata={
                    'session_id': session.id,
                    'mentorship_id': session.mentorship.id,
                    'scheduled_date': session.scheduled_date.isoformat(),
                    'session_title': session.session_template.title if session.session_template else 'Session',
                    'meeting_link': session.meeting_link or '',
                    'location': session.location or ''
                }
            )
            
            # Notification for mentor
            ChatNotification.objects.create(
                recipient=session.mentorship.mentor,
                chat_room=get_chat_room(session.mentorship),
                notification_type='session_reminder',
                title='Session Reminder - Tomorrow',
                message=f'Reminder: Session {session.program_session_number} with {session.mentorship.mentee.full_name} is scheduled for tomorrow at {session.scheduled_date.strftime("%H:%M")}',
                metadata={
                    'session_id': session.id,
                    'mentee_name': session.mentorship.mentee.full_name,
                    'scheduled_date': session.scheduled_date.isoformat(),
                    'meeting_link': session.meeting_link or '',
                    'location': session.location or ''
                }
            )
            
            logger.info(f"24-hour reminder sent for session {session.id}")
            
        elif 0.5 <= hours_until <= 1.5:  # Send 1 hour reminder
            # Notification for mentee
            ChatNotification.objects.create(
                recipient=session.mentorship.mentee,
                chat_room=get_chat_room(session.mentorship),
                notification_type='session_reminder',
                title='Session Starting Soon',
                message=f'Session {session.program_session_number}: {session.session_template.title} starts in 1 hour',
                metadata={
                    'session_id': session.id,
                    'mentorship_id': session.mentorship.id,
                    'scheduled_date': session.scheduled_date.isoformat(),
                    'meeting_link': session.meeting_link or '',
                    'location': session.location or ''
                }
            )
            
            # Notification for mentor
            ChatNotification.objects.create(
                recipient=session.mentorship.mentor,
                chat_room=get_chat_room(session.mentorship),
                notification_type='session_reminder',
                title='Session Starting Soon',
                message=f'Session {session.program_session_number} with {session.mentorship.mentee.full_name} starts in 1 hour',
                metadata={
                    'session_id': session.id,
                    'mentee_name': session.mentorship.mentee.full_name,
                    'scheduled_date': session.scheduled_date.isoformat(),
                    'meeting_link': session.meeting_link or '',
                    'location': session.location or ''
                }
            )
            
            logger.info(f"1-hour reminder sent for session {session.id}")
        
    except Exception as e:
        logger.error(f"Error sending session reminder: {str(e)}")


def send_program_completed_notification(mentorship, program):
    """Send notification when a program is completed"""
    try:
        # Get program progress
        from .models import MentorshipProgramProgress
        progress = MentorshipProgramProgress.objects.filter(
            mentorship=mentorship,
            program=program
        ).first()
        
        if not progress:
            return
        
        # Notification for mentee
        ChatNotification.objects.create(
            recipient=mentorship.mentee,
            chat_room=get_chat_room(mentorship),
            notification_type='program_completed',
            title='Program Completed! 🎉',
            message=f'Congratulations! You have completed the {program.name} program',
            metadata={
                'program_id': program.id,
                'program_name': program.name,
                'mentorship_id': mentorship.id,
                'completed_at': progress.completed_at.isoformat() if progress.completed_at else timezone.now().isoformat(),
                'sessions_completed': progress.sessions_completed,
                'total_sessions': progress.total_sessions
            }
        )
        
        # Notification for mentor
        ChatNotification.objects.create(
            recipient=mentorship.mentor,
            chat_room=get_chat_room(mentorship),
            notification_type='program_completed',
            title='Program Completed',
            message=f'{mentorship.mentee.full_name} has completed the {program.name} program',
            metadata={
                'program_id': program.id,
                'program_name': program.name,
                'mentee_name': mentorship.mentee.full_name,
                'completed_at': progress.completed_at.isoformat() if progress.completed_at else timezone.now().isoformat(),
                'progress_percentage': progress.progress_percentage
            }
        )
        
        logger.info(f"Program completed notification sent for program {program.id}")
        
    except Exception as e:
        logger.error(f"Error sending program completed notification: {str(e)}")


def send_mentorship_completed_notification(mentorship):
    """Send notification when mentorship is completed"""
    try:
        # Notification for mentee
        ChatNotification.objects.create(
            recipient=mentorship.mentee,
            chat_room=get_chat_room(mentorship),
            notification_type='mentorship_completed',
            title='Mentorship Completed! 🎓',
            message=f'Congratulations on completing your mentorship journey!',
            metadata={
                'mentorship_id': mentorship.id,
                'completed_at': mentorship.actual_end_date.isoformat() if mentorship.actual_end_date else timezone.now().isoformat(),
                'start_date': mentorship.start_date.isoformat() if mentorship.start_date else '',
                'duration_days': (mentorship.actual_end_date - mentorship.start_date).days if mentorship.actual_end_date and mentorship.start_date else 0,
                'total_programs': mentorship.programs.count(),
                'rating': mentorship.rating or 0
            }
        )
        
        # Notification for mentor
        ChatNotification.objects.create(
            recipient=mentorship.mentor,
            chat_room=get_chat_room(mentorship),
            notification_type='mentorship_completed',
            title='Mentorship Completed',
            message=f'Your mentorship with {mentorship.mentee.full_name} has been completed',
            metadata={
                'mentorship_id': mentorship.id,
                'mentee_name': mentorship.mentee.full_name,
                'completed_at': mentorship.actual_end_date.isoformat() if mentorship.actual_end_date else timezone.now().isoformat(),
                'duration_days': (mentorship.actual_end_date - mentorship.start_date).days if mentorship.actual_end_date and mentorship.start_date else 0,
                'rating': mentorship.rating or 0
            }
        )
        
        # Notification for admin/HR if mentorship has high rating
        if mentorship.rating and mentorship.rating >= 4.5:
            admins = CustomUser.objects.filter(
                role__in=['admin', 'hr'],
                is_active=True
            )
            
            for admin in admins:
                ChatNotification.objects.create(
                    recipient=admin,
                    notification_type='mentorship_success',
                    title='High-Rated Mentorship Completed',
                    message=f'Mentorship between {mentorship.mentor.full_name} and {mentorship.mentee.full_name} completed with rating: {mentorship.rating}/5',
                    metadata={
                        'mentorship_id': mentorship.id,
                        'mentor_name': mentorship.mentor.full_name,
                        'mentee_name': mentorship.mentee.full_name,
                        'rating': mentorship.rating,
                        'department': mentorship.department.name if mentorship.department else 'Unknown'
                    }
                )
        
        logger.info(f"Mentorship completed notification sent for mentorship {mentorship.id}")
        
    except Exception as e:
        logger.error(f"Error sending mentorship completed notification: {str(e)}")


# Helper functions
def get_chat_room(mentorship):
    """Get or create chat room for mentorship"""
    try:
        if hasattr(mentorship, 'chat_room') and mentorship.chat_room:
            return mentorship.chat_room
        
        # Try to find existing chat room
        chat_room = ChatRoom.objects.filter(
            participants=mentorship.mentor
        ).filter(
            participants=mentorship.mentee
        ).first()
        
        if chat_room:
            return chat_room
        
        # Create new chat room
        chat_room = ChatRoom.objects.create(
            name=f'Mentorship: {mentorship.mentor.full_name} - {mentorship.mentee.full_name}',
            room_type='mentorship'
        )
        chat_room.participants.add(mentorship.mentor, mentorship.mentee)
        chat_room.save()
        
        return chat_room
        
    except Exception as e:
        logger.error(f"Error getting chat room: {str(e)}")
        return None


def get_program_progress_percentage(mentorship, program):
    """Get program progress percentage"""
    try:
        from .models import MentorshipProgramProgress
        progress = MentorshipProgramProgress.objects.filter(
            mentorship=mentorship,
            program=program
        ).first()
        
        return progress.progress_percentage if progress else 0
        
    except Exception as e:
        logger.error(f"Error getting program progress: {str(e)}")
        return 0


def get_total_sessions_completed(mentorship):
    """Get total sessions completed in mentorship"""
    try:
        from .models import MentorshipSession
        return MentorshipSession.objects.filter(
            mentorship=mentorship,
            status='completed'
        ).count()
        
    except Exception as e:
        logger.error(f"Error getting total sessions completed: {str(e)}")
        return 0


# Background task to send session reminders
def send_all_upcoming_session_reminders():
    """Send reminders for all upcoming sessions"""
    try:
        from .models import MentorshipSession
        
        # Get all scheduled sessions in the next 25 hours
        time_threshold = timezone.now() + timedelta(hours=25)
        
        upcoming_sessions = MentorshipSession.objects.filter(
            status='scheduled',
            scheduled_date__gte=timezone.now(),
            scheduled_date__lte=time_threshold
        ).select_related('mentorship', 'mentorship__mentor', 'mentorship__mentee', 'session_template')
        
        logger.info(f"Checking {upcoming_sessions.count()} upcoming sessions for reminders")
        
        for session in upcoming_sessions:
            send_upcoming_session_reminder(session)
        
        logger.info("Session reminder check completed")
        
    except Exception as e:
        logger.error(f"Error sending session reminders: {str(e)}")





import logging
from functools import wraps
import traceback
import json

logger = logging.getLogger(__name__)

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def log_request(view_func):
    """Decorator to log API requests and responses"""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Log request
        print(f"\n{Colors.HEADER}{'='*80}{Colors.ENDC}")
        print(f"{Colors.OKBLUE}{Colors.BOLD}API REQUEST: {view_func.__name__}{Colors.ENDC}")
        print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")
        print(f"{Colors.OKCYAN}Method:{Colors.ENDC} {request.method}")
        print(f"{Colors.OKCYAN}Path:{Colors.ENDC} {request.path}")
        print(f"{Colors.OKCYAN}User:{Colors.ENDC} {request.user if hasattr(request, 'user') else 'Anonymous'}")
        
        # Log request data
        if request.method in ['POST', 'PUT', 'PATCH']:
            print(f"{Colors.OKCYAN}Data:{Colors.ENDC}")
            try:
                # Mask sensitive fields
                data = dict(request.data)
                sensitive_fields = ['password', 'current_password', 'new_password', 'confirm_password', 'token']
                for field in sensitive_fields:
                    if field in data:
                        data[field] = '***MASKED***'
                print(json.dumps(data, indent=2))
            except:
                print(request.data)
        
        # Call the view
        try:
            response = view_func(request, *args, **kwargs)
            
            # Log response
            status_color = Colors.OKGREEN if 200 <= response.status_code < 300 else Colors.FAIL
            print(f"\n{status_color}Response Status:{Colors.ENDC} {response.status_code}")
            
            if hasattr(response, 'data'):
                print(f"{status_color}Response Data:{Colors.ENDC}")
                print(json.dumps(response.data, indent=2, default=str))
            
            print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}\n")
            
            return response
        except Exception as e:
            print(f"\n{Colors.FAIL}{Colors.BOLD}ERROR in {view_func.__name__}:{Colors.ENDC}")
            print(f"{Colors.FAIL}{str(e)}{Colors.ENDC}")
            print(f"{Colors.FAIL}Traceback:{Colors.ENDC}")
            print(traceback.format_exc())
            print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}\n")
            raise
    
    return wrapper


def log_error(message, exception=None, extra_data=None):
    """Helper function to log errors with context"""
    print(f"\n{Colors.FAIL}{'='*80}{Colors.ENDC}")
    print(f"{Colors.FAIL}{Colors.BOLD}ERROR: {message}{Colors.ENDC}")
    print(f"{Colors.FAIL}{'='*80}{Colors.ENDC}")
    
    if exception:
        print(f"{Colors.FAIL}Exception: {str(exception)}{Colors.ENDC}")
        print(f"{Colors.FAIL}Traceback:{Colors.ENDC}")
        print(traceback.format_exc())
    
    if extra_data:
        print(f"{Colors.WARNING}Extra Data:{Colors.ENDC}")
        print(json.dumps(extra_data, indent=2, default=str))
    
    print(f"{Colors.FAIL}{'='*80}{Colors.ENDC}\n")
    
    # Also log to logger
    logger.error(message, exc_info=exception is not None, extra={'extra_data': extra_data})


def log_success(message, data=None):
    """Helper function to log success messages"""
    print(f"\n{Colors.OKGREEN}{'='*80}{Colors.ENDC}")
    print(f"{Colors.OKGREEN}{Colors.BOLD}SUCCESS: {message}{Colors.ENDC}")
    print(f"{Colors.OKGREEN}{'='*80}{Colors.ENDC}")
    
    if data:
        print(f"{Colors.OKCYAN}Data:{Colors.ENDC}")
        print(json.dumps(data, indent=2, default=str))
    
    print(f"{Colors.OKGREEN}{'='*80}{Colors.ENDC}\n")
    
    # Also log to logger
    logger.info(message, extra={'data': data})


def log_warning(message, data=None):
    """Helper function to log warnings"""
    print(f"\n{Colors.WARNING}{'='*80}{Colors.ENDC}")
    print(f"{Colors.WARNING}{Colors.BOLD}WARNING: {message}{Colors.ENDC}")
    print(f"{Colors.WARNING}{'='*80}{Colors.ENDC}")
    
    if data:
        print(f"{Colors.WARNING}Data:{Colors.ENDC}")
        print(json.dumps(data, indent=2, default=str))
    
    print(f"{Colors.WARNING}{'='*80}{Colors.ENDC}\n")
    
    # Also log to logger
    logger.warning(message, extra={'data': data})