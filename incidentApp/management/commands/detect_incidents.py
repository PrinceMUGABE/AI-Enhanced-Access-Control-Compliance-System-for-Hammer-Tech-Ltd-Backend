# incidentApp/management/commands/detect_incidents.py

from django.core.management.base import BaseCommand
from django.utils.timezone import now
from datetime import timedelta
from userApp.models import UserLog
from incidentApp.models import Incident
from incidentApp.utils import IncidentUtils, DangerZoneAnalyzer
from userApp.utils import ActivityLogger

class Command(BaseCommand):
    help = 'Detect and create incidents from danger zone logs'

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeframe',
            type=int,
            default=24,
            help='Timeframe in hours to analyze (default: 24)'
        )
        parser.add_argument(
            '--risk-threshold',
            type=int,
            default=60,
            help='Risk score threshold for incident creation (default: 60)'
        )
        parser.add_argument(
            '--max-incidents',
            type=int,
            default=50,
            help='Maximum number of incidents to create (default: 50)'
        )

    def handle(self, *args, **kwargs):
        timeframe = kwargs['timeframe']
        risk_threshold = kwargs['risk_threshold']
        max_incidents = kwargs['max_incidents']
        
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(self.style.SUCCESS(
            f"🔍 DANGER ZONE INCIDENT DETECTION STARTED"
        ))
        self.stdout.write(f"{'='*80}\n")
        
        self.stdout.write(f"⏰ Timeframe: Last {timeframe} hours")
        self.stdout.write(f"📊 Risk Threshold: {risk_threshold}")
        self.stdout.write(f"🎯 Max Incidents: {max_incidents}\n")
        
        # Get danger zone logs
        self.stdout.write("🔎 Analyzing logs for danger zone activities...")
        danger_logs = DangerZoneAnalyzer.analyze_logs_for_danger(
            timeframe_hours=timeframe,
            risk_threshold=risk_threshold
        )
        
        self.stdout.write(self.style.WARNING(
            f"⚠️  Found {len(danger_logs)} danger zone logs\n"
        ))
        
        if not danger_logs:
            self.stdout.write(self.style.SUCCESS(
                "✅ No danger zone activities detected. System is secure!\n"
            ))
            return
        
        # Create incidents from high-risk logs
        created_count = 0
        skipped_count = 0
        error_count = 0
        
        for i, log_data in enumerate(danger_logs[:max_incidents], 1):
            try:
                log = UserLog.objects.get(id=log_data['id'])
                
                # Check if incident already exists for this log
                if log.incidents.exists():
                    self.stdout.write(
                        f"⏭️  Log {log.id}: Incident already exists - skipping"
                    )
                    skipped_count += 1
                    continue
                
                # Determine severity based on risk score
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
                
                # Create detailed description
                description = self._create_incident_description(log, log_data)
                
                # Create incident
                incident = Incident.objects.create(
                    log=log,
                    title=self._create_incident_title(log, log_data),
                    description=description,
                    severity=severity,
                    priority=priority,
                    risk_score=risk_score,
                    danger_zone=True,
                    status='pending'
                )
                
                # Auto-assign incident
                IncidentUtils.assign_incident_to_user(incident)
                
                created_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f"✅ [{i}/{len(danger_logs[:max_incidents])}] Created incident {incident.incident_number} "
                    f"(Risk: {risk_score}, Severity: {severity.upper()})"
                ))
                
                # Show incident details
                self.stdout.write(f"   📧 User: {log.user_email}")
                self.stdout.write(f"   🎯 Activity: {log.activity}")
                self.stdout.write(f"   👤 Assigned to: {incident.assigned_to.email if incident.assigned_to else 'Unassigned'}")
                self.stdout.write("")
                
            except UserLog.DoesNotExist:
                self.stdout.write(self.style.ERROR(
                    f"❌ Error: Log {log_data['id']} not found"
                ))
                error_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"❌ Error creating incident from log {log_data['id']}: {str(e)}"
                ))
                error_count += 1
        
        # Print summary
        self.stdout.write(f"\n{'='*80}")
        self.stdout.write(self.style.SUCCESS(
            f"📊 INCIDENT DETECTION SUMMARY"
        ))
        self.stdout.write(f"{'='*80}\n")
        
        self.stdout.write(f"✅ Incidents Created: {created_count}")
        self.stdout.write(f"⏭️  Skipped (already exists): {skipped_count}")
        self.stdout.write(f"❌ Errors: {error_count}")
        self.stdout.write(f"📊 Total Danger Logs: {len(danger_logs)}")
        
        if created_count > 0:
            self.stdout.write(self.style.SUCCESS(
                f"\n🎉 Successfully created {created_count} new incidents!"
            ))
        
        self.stdout.write(f"\n{'='*80}\n")
    
    def _create_incident_title(self, log, log_data):
        """Create a descriptive incident title"""
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
        
        return f"[{danger_level}] {base_title}: {log.user_email}"
    
    def _create_incident_description(self, log, log_data):
        """Create a detailed incident description"""
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

USER CONTEXT:
"""
        
        # Add user context
        user_context = log_data.get('user_context', {})
        if user_context:
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
            description += f"\nIP ADDRESS CONTEXT:\n"
            if 'total_activities' in ip_context:
                description += f"• Total Activities from this IP: {ip_context['total_activities']}\n"
            if 'unique_users' in ip_context:
                description += f"• Unique Users: {ip_context['unique_users']}\n"
            if 'failed_attempts' in ip_context:
                description += f"• Failed Attempts: {ip_context['failed_attempts']}\n"
        
        # Add recommendation
        description += f"\n{'='*60}\n"
        description += f"RECOMMENDED ACTION:\n{log_data.get('recommended_action', 'Review and investigate this incident.')}\n"
        description += f"{'='*60}\n"
        
        return description.strip()