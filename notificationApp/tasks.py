from celery import shared_task
from django.utils.timezone import now
from datetime import timedelta
from django.db.models import Q
import logging

from userApp.models import CustomUser
from incidentApp.models import Incident
from complianceAuditApp.models import ComplianceAudit
from .models import Notification
from .views import NotificationUtils

logger = logging.getLogger(__name__)

DIVIDER = "=" * 70


@shared_task(bind=True, name='notificationApp.tasks.generate_notifications_task')
def generate_notifications_task(self):
    """
    Generate notifications for all users based on their role.
    Runs every minute.
    """
    task_start = now()
    print(f"\n{DIVIDER}")
    print(f"🔔 TASK STARTED: generate_notifications_task")
    print(f"   Task ID  : {self.request.id}")
    print(f"   Started  : {task_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(DIVIDER)

    try:
        # Get all active users
        users = CustomUser.objects.filter(is_active=True)
        print(f"\n📋 Processing notifications for {users.count()} active users")

        total_notifications_created = 0
        total_skipped = 0
        errors = 0

        for user in users:
            try:
                user_start = now()
                print(f"\n👤 Processing user: {user.email} (Role: {user.role})")

                # Generate notifications based on role
                notifications_created = generate_user_notifications(user)
                
                total_notifications_created += notifications_created
                
                # Log user processing time
                user_duration = (now() - user_start).total_seconds()
                print(f"   ✅ Created {notifications_created} notification(s) for {user.email} in {user_duration:.2f}s")

            except Exception as e:
                print(f"   ❌ Error processing user {user.email}: {str(e)}")
                errors += 1
                logger.error(f"Error processing user {user.email}: {str(e)}", exc_info=True)

        # Summary
        task_end = now()
        duration = (task_end - task_start).total_seconds()

        print(f"\n{DIVIDER}")
        print(f"📊 TASK SUMMARY: generate_notifications_task")
        print(f"   ✅ Notifications Created: {total_notifications_created}")
        print(f"   ⏭️  Skipped: {total_skipped}")
        print(f"   ❌ Errors: {errors}")
        print(f"   👥 Users Processed: {users.count()}")
        print(f"   ⏱️  Duration: {duration:.2f}s")
        print(DIVIDER + "\n")

        return {
            'status': 'success',
            'notifications_created': total_notifications_created,
            'users_processed': users.count(),
            'errors': errors,
            'duration': duration
        }

    except Exception as e:
        print(f"\n{DIVIDER}")
        print(f"💥 CRITICAL ERROR in generate_notifications_task")
        print(f"   Error: {str(e)}")
        print(DIVIDER + "\n")
        logger.error(f"Critical error in generate_notifications_task: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'message': str(e)
        }


def generate_user_notifications(user):
    """
    Generate notifications for a specific user based on their role.
    Returns the number of notifications created.
    """
    created_count = 0
    skipped_count = 0

    try:
        if user.role == 'compliance_officer':
            created_count = generate_compliance_officer_notifications(user)
        elif user.role == 'employee':
            created_count = generate_employee_notifications(user)
        elif user.role in ['admin', 'hr_manager', 'security_analyst']:
            created_count = generate_general_notifications(user)
        else:
            # Unknown role, skip
            print(f"   ⚠️ Unknown role: {user.role}, skipping")
            return 0

        return created_count

    except Exception as e:
        logger.error(f"Error generating notifications for {user.email}: {str(e)}", exc_info=True)
        return 0


def generate_compliance_officer_notifications(user):
    """Generate notifications for compliance officers - incidents needing audits"""
    created_count = 0
    now_time = now()
    
    # Get incidents assigned to the user that don't have compliance audits
    incidents_without_audit = Incident.objects.filter(
        assigned_to=user,
        status__in=['assigned', 'in_progress', 'pending', 'investigating']
    ).exclude(
        compliance_audits__isnull=False
    )

    # Also get high severity incidents in the user's departments
    if user.departments.exists():
        dept_incidents = Incident.objects.filter(
            department__in=user.departments.all(),
            severity__in=['critical', 'high'],
            status__in=['assigned', 'in_progress', 'pending', 'investigating']
        ).exclude(
            compliance_audits__isnull=False
        ).distinct()
        incidents = incidents_without_audit | dept_incidents
    else:
        incidents = incidents_without_audit

    # Check for critical incidents in the system (for compliance oversight)
    critical_incidents = Incident.objects.filter(
        severity='critical',
        status__in=['pending', 'investigating', 'assigned', 'in_progress']
    ).exclude(
        compliance_audits__isnull=False
    )

    # Combine and deduplicate
    all_incidents = incidents | critical_incidents
    all_incidents = all_incidents.distinct()

    print(f"   📋 Found {all_incidents.count()} incidents needing audits")

    for incident in all_incidents:
        # Check if notification already exists (within last 24 hours)
        existing = Notification.objects.filter(
            user=user,
            notification_type='audit_required',
            incident=incident,
            created_at__gte=now_time - timedelta(hours=24)
        ).exists()

        if not existing:
            priority = 'urgent' if incident.severity == 'critical' else 'high'
            
            # Create notification
            NotificationUtils.create_audit_required_notification(user, incident)
            created_count += 1
            print(f"      ✅ Created audit_required notification for incident {incident.incident_number}")

    return created_count


def generate_employee_notifications(user):
    """Generate notifications for employees - their assigned incidents"""
    created_count = 0
    now_time = now()

    # Get incidents assigned to the employee
    incidents = Incident.objects.filter(
        assigned_to=user,
        status__in=['pending', 'investigating', 'assigned', 'in_progress']
    )

    print(f"   📋 Found {incidents.count()} assigned incidents for employee")

    for incident in incidents:
        # Check if notification already exists (within last 24 hours)
        existing = Notification.objects.filter(
            user=user,
            incident=incident,
            notification_type='incident_assigned',
            created_at__gte=now_time - timedelta(hours=24)
        ).exists()

        if not existing:
            # Create notification for assigned incident
            priority = 'high' if incident.severity in ['critical', 'high'] else 'medium'
            
            NotificationUtils.create_notification(
                user=user,
                notification_type='incident_assigned',
                title=f"Incident Assigned: {incident.incident_number}",
                message=f"You have been assigned incident {incident.incident_number}: {incident.title}",
                priority=priority,
                incident=incident,
                action_link="/assigned-incidents",
                action_text="View Incident"
            )
            created_count += 1
            print(f"      ✅ Created incident_assigned notification for {incident.incident_number}")

        # Also check SLA violations
        if incident.is_overdue:
            existing_sla = Notification.objects.filter(
                user=user,
                incident=incident,
                notification_type='sla_violation',
                created_at__gte=now_time - timedelta(hours=24)
            ).exists()

            if not existing_sla:
                NotificationUtils.create_notification(
                    user=user,
                    notification_type='sla_violation',
                    title=f"SLA Violation: {incident.incident_number}",
                    message=f"Incident {incident.incident_number} has exceeded its SLA deadline!",
                    priority='urgent',
                    incident=incident,
                    action_link="/assigned-incidents",
                    action_text="View Incident"
                )
                created_count += 1
                print(f"      ✅ Created sla_violation notification for {incident.incident_number}")

    return created_count


def generate_general_notifications(user):
    """Generate general notifications for admins, HR, and security analysts"""
    created_count = 0
    now_time = now()

    # For admins: show critical incidents
    if user.is_admin:
        critical_incidents = Incident.objects.filter(
            severity='critical',
            status__in=['pending', 'investigating', 'assigned']
        ).order_by('-created_at')[:5]

        print(f"   📋 Found {critical_incidents.count()} critical incidents for admin")

        for incident in critical_incidents:
            existing = Notification.objects.filter(
                user=user,
                incident=incident,
                notification_type='system_alert',
                created_at__gte=now_time - timedelta(hours=24)
            ).exists()

            if not existing:
                NotificationUtils.create_notification(
                    user=user,
                    notification_type='system_alert',
                    title=f"Critical Incident Alert: {incident.incident_number}",
                    message=f"Critical incident {incident.incident_number}: {incident.title} requires immediate attention!",
                    priority='urgent',
                    incident=incident,
                    action_link=f"/incidents/{incident.id}",
                    action_text="View Incident"
                )
                created_count += 1
                print(f"      ✅ Created system_alert notification for {incident.incident_number}")

    # For security analysts: show high severity incidents in their departments
    if user.role == 'security_analyst' and user.departments.exists():
        high_severity_incidents = Incident.objects.filter(
            department__in=user.departments.all(),
            severity__in=['critical', 'high'],
            status__in=['pending', 'investigating', 'assigned']
        ).exclude(assigned_to=user).distinct()[:10]

        print(f"   📋 Found {high_severity_incidents.count()} high severity incidents for security analyst")

        for incident in high_severity_incidents:
            existing = Notification.objects.filter(
                user=user,
                incident=incident,
                notification_type='system_alert',
                created_at__gte=now_time - timedelta(hours=24)
            ).exists()

            if not existing:
                NotificationUtils.create_notification(
                    user=user,
                    notification_type='system_alert',
                    title=f"Security Alert: {incident.incident_number}",
                    message=f"High severity incident {incident.incident_number}: {incident.title} in your department",
                    priority='high',
                    incident=incident,
                    action_link=f"/incidents/{incident.id}",
                    action_text="View Incident"
                )
                created_count += 1
                print(f"      ✅ Created security alert notification for {incident.incident_number}")

    return created_count


@shared_task(bind=True, name='notificationApp.tasks.send_daily_notification_digest')
def send_daily_notification_digest(self):
    """
    Send daily notification digest to all users.
    Runs daily at 8 AM.
    """
    task_start = now()
    print(f"\n{DIVIDER}")
    print(f"📊 TASK STARTED: send_daily_notification_digest")
    print(f"   Task ID  : {self.request.id}")
    print(f"   Started  : {task_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(DIVIDER)

    try:
        from django.core.mail import send_mail
        from django.conf import settings

        users = CustomUser.objects.filter(is_active=True)
        emails_sent = 0

        for user in users:
            # Get unread notifications from last 24 hours
            notifications = Notification.objects.filter(
                user=user,
                is_read=False,
                created_at__gte=task_start - timedelta(days=1)
            )

            if notifications.count() == 0:
                continue

            # Build email content
            subject = f"Daily Notification Digest - {task_start.strftime('%Y-%m-%d')}"
            
            body = f"""
            Hello {user.full_name},
            
            You have {notifications.count()} unread notification(s) from the last 24 hours.
            
            Summary:
            """
            
            for notification in notifications:
                body += f"""
                - [{notification.get_priority_display()}] {notification.title}
                  {notification.message}
                  Created: {notification.created_at.strftime('%Y-%m-%d %H:%M')}
                """
            
            body += f"""
            
            Log in to the system to view all notifications and take action.
            
            Best regards,
            Hammer Tech Security Platform
            """

            try:
                send_mail(
                    subject=subject,
                    message=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=True
                )
                emails_sent += 1
                print(f"   ✅ Daily digest sent to {user.email}")
            except Exception as e:
                print(f"   ❌ Failed to send daily digest to {user.email}: {str(e)}")
                logger.error(f"Failed to send daily digest to {user.email}: {str(e)}")

        task_end = now()
        duration = (task_end - task_start).total_seconds()

        print(f"\n{DIVIDER}")
        print(f"📊 TASK SUMMARY: send_daily_notification_digest")
        print(f"   📧 Emails Sent: {emails_sent}")
        print(f"   👥 Users Processed: {users.count()}")
        print(f"   ⏱️  Duration: {duration:.2f}s")
        print(DIVIDER + "\n")

        return {
            'status': 'success',
            'emails_sent': emails_sent
        }

    except Exception as e:
        print(f"\n{DIVIDER}")
        print(f"💥 CRITICAL ERROR in send_daily_notification_digest")
        print(f"   Error: {str(e)}")
        print(DIVIDER + "\n")
        logger.error(f"Critical error in send_daily_notification_digest: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'message': str(e)
        }


@shared_task(bind=True, name='notificationApp.tasks.clean_old_notifications_task')
def clean_old_notifications_task(self):
    """
    Clean old notifications (older than 30 days).
    Runs weekly on Sunday at 3 AM.
    """
    task_start = now()
    print(f"\n{DIVIDER}")
    print(f"🧹 TASK STARTED: clean_old_notifications_task")
    print(f"   Task ID  : {self.request.id}")
    print(f"   Started  : {task_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(DIVIDER)

    try:
        from django.db.models import Q
        
        # Delete read notifications older than 30 days
        cutoff_date = task_start - timedelta(days=30)
        old_read_notifications = Notification.objects.filter(
            is_read=True,
            created_at__lt=cutoff_date
        )
        
        # Also delete unread notifications older than 90 days
        unread_cutoff = task_start - timedelta(days=90)
        old_unread_notifications = Notification.objects.filter(
            is_read=False,
            created_at__lt=unread_cutoff
        )
        
        read_count = old_read_notifications.count()
        unread_count = old_unread_notifications.count()
        total_to_delete = read_count + unread_count
        
        print(f"\n📋 Cleanup Configuration:")
        print(f"   Read notifications older than 30 days: {read_count}")
        print(f"   Unread notifications older than 90 days: {unread_count}")
        print(f"   Total notifications to delete: {total_to_delete}")
        
        if total_to_delete > 0:
            # Delete old notifications
            old_read_notifications.delete()
            old_unread_notifications.delete()
            print(f"\n✅ Successfully deleted {total_to_delete} old notifications")
        else:
            print(f"\n✅ No old notifications to delete")

        task_end = now()
        duration = (task_end - task_start).total_seconds()

        print(f"\n{DIVIDER}")
        print(f"📊 TASK SUMMARY: clean_old_notifications_task")
        print(f"   🗑️  Deleted notifications: {total_to_delete}")
        print(f"   ⏱️  Duration: {duration:.2f}s")
        print(DIVIDER + "\n")

        return {
            'status': 'success',
            'deleted_notifications': total_to_delete,
            'deleted_read': read_count,
            'deleted_unread': unread_count
        }

    except Exception as e:
        print(f"\n{DIVIDER}")
        print(f"💥 CRITICAL ERROR in clean_old_notifications_task")
        print(f"   Error: {str(e)}")
        print(DIVIDER + "\n")
        logger.error(f"Critical error in clean_old_notifications_task: {str(e)}", exc_info=True)
        return {
            'status': 'error',
            'message': str(e)
        }


        
             