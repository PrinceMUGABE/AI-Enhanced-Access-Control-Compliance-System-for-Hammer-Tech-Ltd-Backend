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


@shared_task(bind=True, name='incidentApp.tasks.detect_incidents_task')
def detect_incidents_task(self):
    """
    Detect and create incidents from danger zone logs
    Runs every minute
    """
    try:
        logger.info("🔍 Starting incident detection task...")
        
        # Configuration
        timeframe_hours = 1  # Check last hour
        risk_threshold = 60
        max_incidents_per_run = 20
        
        # Get danger zone logs
        danger_logs = DangerZoneAnalyzer.analyze_logs_for_danger(
            timeframe_hours=timeframe_hours,
            risk_threshold=risk_threshold
        )
        
        logger.info(f"📊 Found {len(danger_logs)} danger zone logs")
        
        if not danger_logs:
            logger.info("✅ No danger zone activities detected")
            return {
                'status': 'success',
                'message': 'No danger zone activities detected',
                'created_incidents': 0,
                'total_danger_logs': 0
            }
        
        # Create incidents
        created_count = 0
        skipped_count = 0
        error_count = 0
        created_incidents = []
        
        for log_data in danger_logs[:max_incidents_per_run]:
            try:
                log = UserLog.objects.get(id=log_data['id'])
                
                # Check if incident already exists
                if log.incidents.exists():
                    skipped_count += 1
                    continue
                
                # Determine severity and priority
                risk_score = log_data['risk_score']
                if risk_score >= 85:
                    severity = 'critical'
                    priority = 'urgent'
                elif risk_score >= 70:
                    severity = 'high'
                    priority = 'high'
                elif risk_score >= 60:
                    severity = 'medium'
                    priority = 'medium'
                else:
                    severity = 'low'
                    priority = 'low'
                
                # Create incident title
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
                
                # Create detailed description
                description = create_incident_description(log, log_data)
                
                # Create incident
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
                
                # Auto-assign incident
                IncidentUtils.assign_incident_to_user(incident)
                
                # Send notification for critical incidents
                if severity in ['critical', 'high']:
                    NotificationUtils.send_incident_assignment_notification(incident)
                
                created_count += 1
                created_incidents.append({
                    'incident_number': incident.incident_number,
                    'title': incident.title,
                    'severity': incident.severity,
                    'risk_score': incident.risk_score,
                    'assigned_to': incident.assigned_to.email if incident.assigned_to else None
                })
                
                logger.info(
                    f"✅ Created incident {incident.incident_number} "
                    f"(Risk: {risk_score}, Severity: {severity})"
                )
                
            except UserLog.DoesNotExist:
                logger.error(f"❌ Log {log_data['id']} not found")
                error_count += 1
            except Exception as e:
                logger.error(f"❌ Error creating incident: {str(e)}")
                error_count += 1
        
        # Log summary
        logger.info(f"📊 Incident Detection Summary:")
        logger.info(f"   ✅ Created: {created_count}")
        logger.info(f"   ⏭️  Skipped: {skipped_count}")
        logger.info(f"   ❌ Errors: {error_count}")
        
        return {
            'status': 'success',
            'created_incidents': created_count,
            'skipped_incidents': skipped_count,
            'errors': error_count,
            'total_danger_logs': len(danger_logs),
            'incidents': created_incidents
        }
        
    except Exception as e:
        logger.error(f"❌ Critical error in detect_incidents_task: {str(e)}")
        return {
            'status': 'error',
            'message': str(e),
            'created_incidents': 0
        }


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
    
    # Add user context
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
    
    # Add IP context
    ip_context = log_data.get('ip_context', {})
    if ip_context:
        description += "\nIP ADDRESS CONTEXT:\n"
        if 'total_activities' in ip_context:
            description += f"• Total Activities from IP: {ip_context['total_activities']}\n"
        if 'unique_users' in ip_context:
            description += f"• Unique Users: {ip_context['unique_users']}\n"
        if 'failed_attempts' in ip_context:
            description += f"• Failed Attempts: {ip_context['failed_attempts']}\n"
    
    # Add recommendation
    description += f"\n{'='*60}\n"
    description += f"RECOMMENDED ACTION:\n{log_data.get('recommended_action', 'Review and investigate.')}\n"
    description += f"{'='*60}\n"
    
    return description.strip()


@shared_task(bind=True, name='incidentApp.tasks.check_sla_compliance_task')
def check_sla_compliance_task(self):
    """
    Check SLA compliance for all open incidents
    Runs every 5 minutes
    """
    try:
        logger.info("⏰ Starting SLA compliance check...")
        
        violations = IncidentUtils.check_sla_compliance()
        
        logger.info(f"📊 Found {len(violations)} SLA violations")
        
        # Send notifications for violations
        for violation in violations:
            try:
                incident = Incident.objects.get(incident_number=violation['incident_number'])
                NotificationUtils.send_sla_violation_notification(incident)
            except Exception as e:
                logger.error(f"Error sending SLA notification: {str(e)}")
        
        return {
            'status': 'success',
            'violations': len(violations),
            'violation_details': violations
        }
        
    except Exception as e:
        logger.error(f"❌ Error in check_sla_compliance_task: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }


@shared_task(bind=True, name='incidentApp.tasks.generate_daily_report_task')
def generate_daily_report_task(self):
    """
    Generate daily incident report
    Runs daily at 8 AM
    """
    try:
        logger.info("📊 Generating daily incident report...")
        
        from incidentApp.models import Report
        from incidentApp.utils import ReportGenerator, get_incident_data_for_report, save_report_file
        from datetime import date
        
        # Get admin user for report generation
        admin_user = CustomUser.objects.filter(role='admin', is_active=True).first()
        
        if not admin_user:
            logger.error("No admin user found for report generation")
            return {'status': 'error', 'message': 'No admin user found'}
        
        # Set parameters for yesterday's report
        yesterday = date.today() - timedelta(days=1)
        parameters = {
            'date_from': yesterday,
            'date_to': yesterday,
            'report_type': 'incident'
        }
        
        # Create report
        report = Report.objects.create(
            title=f"Daily Incident Report - {yesterday.strftime('%Y-%m-%d')}",
            description=f"Automated daily incident report for {yesterday.strftime('%Y-%m-%d')}",
            report_type='incident',
            format='pdf',
            generated_by=admin_user,
            parameters=parameters,
            is_scheduled=True,
            is_public=False
        )
        
        # Generate report content
        report_data = get_incident_data_for_report(parameters)
        report_generator = ReportGenerator()
        
        content = report_generator.generate_pdf_report(
            report_data,
            'incident',
            report.title,
            report.description
        )
        
        # Save file
        save_report_file(report, content, 'pdf')
        
        logger.info(f"✅ Generated daily report: {report.report_number}")
        
        return {
            'status': 'success',
            'report_number': report.report_number,
            'report_id': report.id
        }
        
    except Exception as e:
        logger.error(f"❌ Error in generate_daily_report_task: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }


@shared_task(bind=True, name='incidentApp.tasks.clean_old_logs_task')
def clean_old_logs_task(self):
    """
    Clean old user logs (older than 90 days)
    Runs daily at 2 AM
    """
    try:
        logger.info("🧹 Starting old logs cleanup...")
        
        # Delete logs older than 90 days
        cutoff_date = now() - timedelta(days=90)
        old_logs = UserLog.objects.filter(timestamp__lt=cutoff_date)
        
        count = old_logs.count()
        old_logs.delete()
        
        logger.info(f"✅ Deleted {count} old logs")
        
        return {
            'status': 'success',
            'deleted_logs': count
        }
        
    except Exception as e:
        logger.error(f"❌ Error in clean_old_logs_task: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }


@shared_task(bind=True, name='incidentApp.tasks.test_task')
def test_task(self):
    """Test task to verify Celery is working"""
    logger.info("🧪 Test task executed successfully!")
    return {'status': 'success', 'message': 'Celery is working!'}