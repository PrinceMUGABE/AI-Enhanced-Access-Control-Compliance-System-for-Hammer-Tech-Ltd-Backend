# incidentApp/tasks.py

from celery import shared_task
from django.utils.timezone import now
from datetime import timedelta
from userApp.models import UserLog, CustomUser
from incidentApp.models import Incident
from incidentApp.utils import IncidentUtils, DangerZoneAnalyzer, NotificationUtils
from userApp.utils import ActivityLogger
import logging

logger = logging.getLogger(__name__)

DIVIDER = "=" * 70


# ===========================================================================
# TASK 1: Detect Incidents
# ===========================================================================

@shared_task(bind=True, name='incidentApp.tasks.detect_incidents_task')
def detect_incidents_task(self):
    """
    Detect and create incidents from danger zone logs.
    Runs every minute.
    """
    task_start = now()
    print(f"\n{DIVIDER}")
    print(f"🔍 TASK STARTED: detect_incidents_task")
    print(f"   Task ID  : {self.request.id}")
    print(f"   Started  : {task_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(DIVIDER)

    try:
        # --- Configuration ---
        timeframe_hours = 1
        risk_threshold = 60
        max_incidents_per_run = 20

        print(f"\n📋 Configuration:")
        print(f"   Timeframe  : Last {timeframe_hours} hour(s)")
        print(f"   Risk threshold : {risk_threshold}")
        print(f"   Max incidents  : {max_incidents_per_run}")

        # --- Fetch danger logs ---
        print(f"\n⏳ Fetching danger zone logs...")
        danger_logs = DangerZoneAnalyzer.analyze_logs_for_danger(
            timeframe_hours=timeframe_hours,
            risk_threshold=risk_threshold
        )

        print(f"   → Found {len(danger_logs)} danger zone log(s)")

        if not danger_logs:
            print(f"\n✅ No danger zone activities detected. Task complete.")
            print(DIVIDER + "\n")
            return {
                'status': 'success',
                'message': 'No danger zone activities detected',
                'created_incidents': 0,
                'total_danger_logs': 0
            }

        # --- Show top logs found ---
        print(f"\n📊 Top danger logs (up to 5 shown):")
        for i, log in enumerate(danger_logs[:5], 1):
            print(f"   [{i}] Email: {log.get('user_email')} | "
                  f"Risk: {log.get('risk_score')} | "
                  f"Level: {log.get('danger_level', 'N/A').upper()} | "
                  f"Activity: {log.get('activity')}")

        # --- Process logs ---
        created_count = 0
        skipped_count = 0
        error_count = 0
        created_incidents = []

        print(f"\n🔄 Processing up to {max_incidents_per_run} log(s)...")
        print(DIVIDER)

        for index, log_data in enumerate(danger_logs[:max_incidents_per_run], 1):
            log_id = log_data.get('id')
            print(f"\n  [{index}/{min(len(danger_logs), max_incidents_per_run)}] "
                  f"Processing log ID: {log_id}")
            print(f"   User    : {log_data.get('user_email')}")
            print(f"   Activity: {log_data.get('activity')}")
            print(f"   Risk    : {log_data.get('risk_score')}")

            try:
                # Fetch the log object
                try:
                    log = UserLog.objects.get(id=log_id)
                    print(f"   ✅ UserLog found: {log}")
                except UserLog.DoesNotExist:
                    print(f"   ❌ UserLog with ID {log_id} not found. Skipping.")
                    error_count += 1
                    continue

                # Check if incident already exists
                if log.incidents.exists():
                    existing = log.incidents.first()
                    print(f"   ⏭️  Incident already exists ({existing.incident_number}). Skipping.")
                    skipped_count += 1
                    continue

                # Determine severity and priority
                risk_score = log_data['risk_score']
                if risk_score >= 85:
                    severity, priority = 'critical', 'urgent'
                elif risk_score >= 70:
                    severity, priority = 'high', 'high'
                elif risk_score >= 60:
                    severity, priority = 'medium', 'medium'
                else:
                    severity, priority = 'low', 'low'

                print(f"   Severity: {severity} | Priority: {priority}")

                # Build title
                activity_titles = {
                    'login_failed': 'Failed Login Attempt',
                    'access_denied': 'Unauthorized Access Attempt',
                    'unauthorized_access': 'Unauthorized Access Detected',
                    'data_breach': 'Potential Data Breach',
                    'system_breach': 'System Security Breach',
                    'policy_violation': 'Policy Violation Detected',
                    'suspicious_activity': 'Suspicious Activity Detected',
                }
                base_title = activity_titles.get(log.activity, 'Security Incident')
                danger_level = log_data.get('danger_level', 'medium').upper()
                title = f"[{danger_level}] {base_title}: {log.user_email}"
                print(f"   Title   : {title}")

                # Build description
                description = create_incident_description(log, log_data)

                # Create incident
                print(f"   ⏳ Creating incident...")
                incident = Incident.objects.create(
                    log=log,
                    title=title,
                    description=description,
                    severity=severity,
                    priority=priority,
                    risk_score=risk_score,
                    danger_zone=True,
                    status='pending'
                )
                print(f"   ✅ Incident created: {incident.incident_number}")

                # Auto-assign
                print(f"   ⏳ Auto-assigning incident...")
                assigned_user = IncidentUtils.assign_incident_to_user(incident)
                if assigned_user:
                    print(f"   ✅ Assigned to: {assigned_user.email}")
                else:
                    print(f"   ⚠️  No eligible user found for assignment")

                # Notify for critical/high
                if severity in ['critical', 'high']:
                    print(f"   📧 Sending notification (severity={severity})...")
                    NotificationUtils.send_incident_assignment_notification(incident)
                    print(f"   ✅ Notification sent")

                created_count += 1
                created_incidents.append({
                    'incident_number': incident.incident_number,
                    'title': incident.title,
                    'severity': incident.severity,
                    'risk_score': incident.risk_score,
                    'assigned_to': incident.assigned_to.email if incident.assigned_to else None
                })

            except Exception as e:
                import traceback
                print(f"   ❌ ERROR processing log {log_id}: {str(e)}")
                print(f"   Traceback:\n{traceback.format_exc()}")
                error_count += 1

        # --- Summary ---
        task_end = now()
        duration = (task_end - task_start).total_seconds()

        print(f"\n{DIVIDER}")
        print(f"📊 TASK SUMMARY: detect_incidents_task")
        print(f"   ✅ Created  : {created_count}")
        print(f"   ⏭️  Skipped  : {skipped_count}")
        print(f"   ❌ Errors   : {error_count}")
        print(f"   📋 Total logs analyzed: {len(danger_logs)}")
        print(f"   ⏱️  Duration : {duration:.2f}s")
        print(DIVIDER + "\n")

        return {
            'status': 'success',
            'created_incidents': created_count,
            'skipped_incidents': skipped_count,
            'errors': error_count,
            'total_danger_logs': len(danger_logs),
            'incidents': created_incidents
        }

    except Exception as e:
        import traceback
        print(f"\n{DIVIDER}")
        print(f"💥 CRITICAL ERROR in detect_incidents_task")
        print(f"   Error: {str(e)}")
        print(f"   Traceback:\n{traceback.format_exc()}")
        print(DIVIDER + "\n")
        return {
            'status': 'error',
            'message': str(e),
            'created_incidents': 0
        }


# ===========================================================================
# TASK 2: Check SLA Compliance
# ===========================================================================

@shared_task(bind=True, name='incidentApp.tasks.check_sla_compliance_task')
def check_sla_compliance_task(self):
    """
    Check SLA compliance for all open incidents.
    Runs every 5 minutes.
    """
    task_start = now()
    print(f"\n{DIVIDER}")
    print(f"⏰ TASK STARTED: check_sla_compliance_task")
    print(f"   Task ID : {self.request.id}")
    print(f"   Started : {task_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(DIVIDER)

    try:
        print(f"\n⏳ Checking SLA compliance across all open incidents...")
        violations = IncidentUtils.check_sla_compliance()

        print(f"   → Found {len(violations)} SLA violation(s)")

        if not violations:
            print(f"\n✅ No SLA violations found. Task complete.")
            print(DIVIDER + "\n")
            return {
                'status': 'success',
                'violations': 0,
                'violation_details': []
            }

        # Show violations
        print(f"\n📋 Violations found:")
        for i, v in enumerate(violations, 1):
            print(f"   [{i}] Incident : {v.get('incident_number')}")
            print(f"        Severity : {v.get('severity')}")
            print(f"        Status   : {v.get('status')}")
            print(f"        Overdue  : {v.get('overdue_hours')} hour(s)")
            print(f"        Assigned : {v.get('assigned_to') or 'Unassigned'}")

        # Send notifications
        print(f"\n📧 Sending SLA violation notifications...")
        notify_success = 0
        notify_fail = 0

        for v in violations:
            incident_number = v.get('incident_number')
            print(f"   ⏳ Notifying for {incident_number}...")
            try:
                incident = Incident.objects.get(incident_number=incident_number)
                NotificationUtils.send_sla_violation_notification(incident)
                print(f"   ✅ Notification sent for {incident_number}")
                notify_success += 1
            except Incident.DoesNotExist:
                print(f"   ❌ Incident {incident_number} not found in DB")
                notify_fail += 1
            except Exception as e:
                print(f"   ❌ Failed to notify for {incident_number}: {str(e)}")
                notify_fail += 1

        # Summary
        task_end = now()
        duration = (task_end - task_start).total_seconds()

        print(f"\n{DIVIDER}")
        print(f"📊 TASK SUMMARY: check_sla_compliance_task")
        print(f"   ⚠️  Violations found     : {len(violations)}")
        print(f"   ✅ Notifications sent    : {notify_success}")
        print(f"   ❌ Notification failures : {notify_fail}")
        print(f"   ⏱️  Duration             : {duration:.2f}s")
        print(DIVIDER + "\n")

        return {
            'status': 'success',
            'violations': len(violations),
            'violation_details': violations
        }

    except Exception as e:
        import traceback
        print(f"\n{DIVIDER}")
        print(f"💥 CRITICAL ERROR in check_sla_compliance_task")
        print(f"   Error: {str(e)}")
        print(f"   Traceback:\n{traceback.format_exc()}")
        print(DIVIDER + "\n")
        return {
            'status': 'error',
            'message': str(e)
        }


# ===========================================================================
# TASK 3: Generate Daily Report
# ===========================================================================

@shared_task(bind=True, name='incidentApp.tasks.generate_daily_report_task')
def generate_daily_report_task(self):
    """
    Generate daily incident report.
    Runs daily at 8 AM.
    """
    from datetime import date

    task_start = now()
    print(f"\n{DIVIDER}")
    print(f"📊 TASK STARTED: generate_daily_report_task")
    print(f"   Task ID : {self.request.id}")
    print(f"   Started : {task_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(DIVIDER)

    try:
        from incidentApp.models import Report
        from incidentApp.utils import ReportGenerator, get_incident_data_for_report, save_report_file

        # --- Find admin user ---
        print(f"\n⏳ Looking for an active admin user...")
        admin_user = CustomUser.objects.filter(role='admin', is_active=True).first()

        if not admin_user:
            print(f"   ❌ No active admin user found. Cannot generate report.")
            print(DIVIDER + "\n")
            return {'status': 'error', 'message': 'No admin user found'}

        print(f"   ✅ Admin user found: {admin_user.email}")

        # --- Set report parameters ---
        yesterday = date.today() - timedelta(days=1)
        parameters = {
            'date_from': yesterday.strftime('%Y-%m-%d'),
            'date_to': yesterday.strftime('%Y-%m-%d'),
            'report_type': 'incident'
        }

        print(f"\n📋 Report Parameters:")
        print(f"   Date From   : {parameters['date_from']}")
        print(f"   Date To     : {parameters['date_to']}")
        print(f"   Report Type : {parameters['report_type']}")

        # --- Create report record ---
        report_title = f"Daily Incident Report - {yesterday.strftime('%Y-%m-%d')}"
        print(f"\n⏳ Creating report record in database...")
        print(f"   Title: {report_title}")

        report = Report.objects.create(
            title=report_title,
            description=f"Automated daily incident report for {yesterday.strftime('%Y-%m-%d')}",
            report_type='incident',
            format='pdf',
            generated_by=admin_user,
            parameters=parameters,
            is_scheduled=True,
            is_public=False
        )
        print(f"   ✅ Report record created: {report.report_number}")

        # --- Fetch data ---
        print(f"\n⏳ Fetching incident data for report...")
        report_data = get_incident_data_for_report(parameters)
        print(f"   ✅ Data fetched")
        print(f"   Total incidents  : {report_data.get('total_incidents', 0)}")
        print(f"   Open incidents   : {report_data.get('open_incidents', 0)}")
        print(f"   Resolved         : {report_data.get('resolved_incidents', 0)}")

        # --- Generate PDF ---
        print(f"\n⏳ Generating PDF content...")
        report_generator = ReportGenerator()
        content = report_generator.generate_pdf_report(
            report_data,
            'incident',
            report.title,
            report.description
        )
        print(f"   ✅ PDF content generated ({len(content):,} bytes)")

        # --- Save file ---
        print(f"\n⏳ Saving report file to disk...")
        saved = save_report_file(report, content, 'pdf')

        if saved:
            print(f"   ✅ File saved successfully")
            print(f"   File path : {report.file_path}")
            print(f"   File size : {report.file_size:,} bytes" if report.file_size else "   File size: unknown")
        else:
            print(f"   ❌ File save failed")

        # --- Summary ---
        task_end = now()
        duration = (task_end - task_start).total_seconds()

        print(f"\n{DIVIDER}")
        print(f"📊 TASK SUMMARY: generate_daily_report_task")
        print(f"   ✅ Report Number : {report.report_number}")
        print(f"   ✅ Report ID     : {report.id}")
        print(f"   ✅ File saved    : {saved}")
        print(f"   ⏱️  Duration     : {duration:.2f}s")
        print(DIVIDER + "\n")

        return {
            'status': 'success',
            'report_number': report.report_number,
            'report_id': report.id
        }

    except Exception as e:
        import traceback
        print(f"\n{DIVIDER}")
        print(f"💥 CRITICAL ERROR in generate_daily_report_task")
        print(f"   Error: {str(e)}")
        print(f"   Traceback:\n{traceback.format_exc()}")
        print(DIVIDER + "\n")
        return {
            'status': 'error',
            'message': str(e)
        }


# ===========================================================================
# TASK 4: Clean Old Logs
# ===========================================================================

@shared_task(bind=True, name='incidentApp.tasks.clean_old_logs_task')
def clean_old_logs_task(self):
    """
    Clean old user logs (older than 90 days).
    Runs daily at 2 AM.
    """
    task_start = now()
    print(f"\n{DIVIDER}")
    print(f"🧹 TASK STARTED: clean_old_logs_task")
    print(f"   Task ID : {self.request.id}")
    print(f"   Started : {task_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(DIVIDER)

    try:
        cutoff_date = now() - timedelta(days=90)
        print(f"\n📋 Cleanup Configuration:")
        print(f"   Retention : 90 days")
        print(f"   Cutoff    : {cutoff_date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   (Deleting logs older than this date)")

        # Count before deleting
        print(f"\n⏳ Counting logs to be deleted...")
        old_logs = UserLog.objects.filter(timestamp__lt=cutoff_date)
        count = old_logs.count()
        print(f"   → {count} log(s) found older than 90 days")

        if count == 0:
            print(f"\n✅ No old logs to delete. Task complete.")
            print(DIVIDER + "\n")
            return {
                'status': 'success',
                'deleted_logs': 0
            }

        # Show a sample of what will be deleted
        sample = old_logs.order_by('timestamp')[:3]
        print(f"\n   Sample of logs to be deleted (oldest first):")
        for log in sample:
            print(f"   - [{log.timestamp.strftime('%Y-%m-%d')}] "
                  f"{log.user_email} | {log.activity}")

        # Delete
        print(f"\n⏳ Deleting {count} old log(s)...")
        old_logs.delete()
        print(f"   ✅ Deletion complete")

        # Summary
        task_end = now()
        duration = (task_end - task_start).total_seconds()

        print(f"\n{DIVIDER}")
        print(f"📊 TASK SUMMARY: clean_old_logs_task")
        print(f"   🗑️  Logs deleted : {count}")
        print(f"   ⏱️  Duration     : {duration:.2f}s")
        print(DIVIDER + "\n")

        return {
            'status': 'success',
            'deleted_logs': count
        }

    except Exception as e:
        import traceback
        print(f"\n{DIVIDER}")
        print(f"💥 CRITICAL ERROR in clean_old_logs_task")
        print(f"   Error: {str(e)}")
        print(f"   Traceback:\n{traceback.format_exc()}")
        print(DIVIDER + "\n")
        return {
            'status': 'error',
            'message': str(e)
        }


# ===========================================================================
# TASK 5: Test Task
# ===========================================================================

@shared_task(bind=True, name='incidentApp.tasks.test_task')
def test_task(self):
    """Test task to verify Celery is working"""
    print(f"\n{DIVIDER}")
    print(f"🧪 TASK STARTED: test_task")
    print(f"   Task ID : {self.request.id}")
    print(f"   Time    : {now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   ✅ Celery is working correctly!")
    print(DIVIDER + "\n")
    return {'status': 'success', 'message': 'Celery is working!'}


# ===========================================================================
# Helper: Create Incident Description
# ===========================================================================

def create_incident_description(log, log_data):
    """Create detailed incident description"""
    description = f"""
🚨 AUTOMATED INCIDENT DETECTION
{'='*60}

RISK ASSESSMENT:
- Risk Score: {log_data['risk_score']}/100
- Danger Level: {log_data.get('danger_level', 'medium').upper()}
- Detection Time: {now().strftime('%Y-%m-%d %H:%M:%S')}

USER INFORMATION:
- Email: {log.user_email}
- User Role: {log.user_role or 'N/A'}
- IP Address: {log.ip_address or 'N/A'}

ACTIVITY DETAILS:
- Activity Type: {log.activity}
- Endpoint: {log.endpoint or 'N/A'}
- HTTP Method: {log.http_method or 'N/A'}
- Status Code: {log.status_code or 'N/A'}
- Success: {'Yes' if log.is_success else 'No'}
- Timestamp: {log.timestamp.strftime('%Y-%m-%d %H:%M:%S') if log.timestamp else 'N/A'}

DESCRIPTION:
{log.description}
"""

    user_context = log_data.get('user_context', {})
    if user_context:
        description += "\nUSER CONTEXT:\n"
        if 'full_name' in user_context:
            description += f"• Full Name: {user_context['full_name']}\n"
        if 'role' in user_context:
            description += f"• Role: {user_context['role']}\n"
        if 'department' in user_context:
            description += f"• Department: {user_context['department']}\n"
        if 'recent_failed_logins' in user_context:
            description += f"• Recent Failed Logins: {user_context['recent_failed_logins']}\n"

    ip_context = log_data.get('ip_context', {})
    if ip_context:
        description += "\nIP ADDRESS CONTEXT:\n"
        if 'total_activities' in ip_context:
            description += f"• Total Activities from IP: {ip_context['total_activities']}\n"
        if 'unique_users' in ip_context:
            description += f"• Unique Users: {ip_context['unique_users']}\n"
        if 'failed_attempts' in ip_context:
            description += f"• Failed Attempts: {ip_context['failed_attempts']}\n"

    description += f"\n{'='*60}\n"
    description += f"RECOMMENDED ACTION:\n{log_data.get('recommended_action', 'Review and investigate.')}\n"
    description += f"{'='*60}\n"

    return description.strip()