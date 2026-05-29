import json
import csv
import io
import pandas as pd
from datetime import datetime, timedelta
from django.db.models import Q, Count, Avg, F, Sum
from django.utils.timezone import now as timezone_now, localtime
from django.http import HttpResponse
from django.core.exceptions import ValidationError
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import logging
from io import BytesIO
import os
from django.conf import settings
import uuid

from .models import Incident, Report
from departmentApp.models import Department
from userApp.models import CustomUser, UserLog
from userApp.models import CustomUser as User
from userApp.utils import ActivityLogger

logger = logging.getLogger(__name__)


# incidentApp/utils.py - Update IncidentUtils

class IncidentUtils:
    """Utility class for incident-related operations"""
    
    @staticmethod
    def track_incident_progress(incident):
        """Track incident progress and check SLA violations"""
        # Replace now() with timezone_now()
        current_time = timezone_now() 
        
        # Check if SLA is violated
        if incident.sla_due_date and current_time > incident.sla_due_date:
            if not incident.sla_violated:
                incident.sla_violated = True
                incident.save()
                
                # Send SLA violation notification
                NotificationUtils.send_sla_violation_notification(incident)
                
                return {
                    'status': 'sla_violated',
                    'message': f'SLA violated for incident {incident.incident_number}',
                    'overdue_hours': (current_time - incident.sla_due_date).total_seconds() / 3600
                }
        
        # Check if incident is approaching SLA deadline (within 1 hour)
        if incident.sla_due_date and not incident.sla_violated:
            time_to_deadline = (incident.sla_due_date - current_time).total_seconds() / 3600
            if 0 < time_to_deadline <= 1:
                return {
                    'status': 'sla_approaching',
                    'message': f'SLA deadline approaching for incident {incident.incident_number}',
                    'hours_remaining': time_to_deadline
                }
        
        return {'status': 'on_track'}
    
    @staticmethod
    def get_incident_statistics(user=None, timeframe_days=30):
        """
        Get comprehensive incident statistics
        """
        # Replace now() with timezone_now()
        cutoff_date = timezone_now() - timedelta(days=timeframe_days)
        # ... rest of the code
    
    @staticmethod
    def check_sla_compliance():
        """
        Check SLA compliance across all incidents
        """
        # Replace now() with timezone_now()
        current_time = timezone_now()
        
        # Find incidents with violated SLAs
        violated_incidents = Incident.objects.filter(
            sla_due_date__lt=current_time,
            status__in=['pending', 'investigating', 'assigned', 'in_progress']
        ).select_related('assigned_to', 'department')
        # ... rest of the code
    
    @staticmethod
    def calculate_risk_score(log):
        """
        Calculate risk score for a UserLog
        """
        # Replace now() with timezone_now()
        current_time = timezone_now()
        
        risk_score = 0
        
        # Base risk by activity type
        activity_risks = {
            'login_failed': 20,
            'unauthorized_access': 40,
            'suspicious_activity': 50,
            'data_access_violation': 60,
            'policy_violation': 45,
            'security_breach': 80,
            'multiple_failed_logins': 35,
            'unusual_hour_access': 25,
            'suspicious_ip': 30,
        }
        
        # Get base risk
        base_risk = activity_risks.get(log.activity, 10)
        risk_score += base_risk
        
        # Increase risk if not successful
        if not log.is_success:
            risk_score += 15
        
        # Check for repeated failures
        if hasattr(log, 'user_email') and log.user_email:
            recent_failures = UserLog.objects.filter(
                user_email=log.user_email,
                is_success=False,
                timestamp__gte=current_time - timedelta(hours=1)
            ).count()
            
            if recent_failures > 5:
                risk_score += 20
            elif recent_failures > 3:
                risk_score += 10
        
        # Check for unusual patterns
        if log.ip_address:
            # Check if IP has multiple users
            ip_users = UserLog.objects.filter(
                ip_address=log.ip_address,
                timestamp__gte=current_time - timedelta(hours=24)
            ).values('user_email').distinct().count()
            
            if ip_users > 5:
                risk_score += 15
        
        # Cap at 100
        return min(risk_score, 100)

class ReportGenerator:
    """Class for generating various types of reports"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.setup_custom_styles()
    
    def setup_custom_styles(self):
        """Setup custom styles for PDF generation"""
        # Title style
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Title'],
            fontSize=24,
            textColor=colors.HexColor('#1e40af'),
            spaceAfter=30,
            alignment=1  # Center
        ))
        
        # Subtitle style
        self.styles.add(ParagraphStyle(
            name='ReportSubtitle',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=colors.gray,
            spaceAfter=20,
            alignment=1
        ))
        
        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#1e40af'),
            spaceBefore=20,
            spaceAfter=10,
            leftIndent=10
        ))
        
        # Table header style
        self.styles.add(ParagraphStyle(
            name='TableHeader',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.white,
            alignment=1
        ))
        
        # Table cell style
        self.styles.add(ParagraphStyle(
            name='TableCell',
            parent=self.styles['Normal'],
            fontSize=9,
            alignment=1
        ))
    
    def generate_pdf_report(self, report_data, report_type, title, description):
        """
        Generate PDF report
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        elements = []
        
        # Add title
        elements.append(Paragraph(title, self.styles['ReportTitle']))
        elements.append(Paragraph(description, self.styles['ReportSubtitle']))
        
        # Add generation info
        info_table = Table([
            ['Generated By:', report_data.get('generated_by', 'System')],
            ['Generated At:', now().strftime('%Y-%m-%d %H:%M:%S')],
            ['Report Type:', report_type.replace('_', ' ').title()],
            ['Time Period:', report_data.get('time_period', 'Custom')]
        ], colWidths=[100, 300])
        
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#e5e7eb')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('BACKGROUND', (1, 0), (1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        
        elements.append(info_table)
        elements.append(Spacer(1, 20))
        
        # Add content based on report type
        if report_type == 'incident':
            elements.extend(self.generate_incident_pdf_content(report_data))
        elif report_type == 'user_activity':
            elements.extend(self.generate_user_activity_pdf_content(report_data))
        elif report_type == 'security':
            elements.extend(self.generate_security_pdf_content(report_data))
        elif report_type == 'compliance':
            elements.extend(self.generate_compliance_pdf_content(report_data))
        
        # Build PDF
        doc.build(elements)
        
        buffer.seek(0)
        return buffer.getvalue()
    
    def generate_incident_pdf_content(self, report_data):
        """Generate PDF content for incident reports"""
        elements = []
        
        # Summary statistics
        elements.append(Paragraph("Summary Statistics", self.styles['SectionHeader']))
        
        stats_data = [
            ['Total Incidents', str(report_data.get('total_incidents', 0))],
            ['Open Incidents', str(report_data.get('open_incidents', 0))],
            ['Resolved Incidents', str(report_data.get('resolved_incidents', 0))],
            ['Resolution Rate', f"{report_data.get('resolution_rate', 0)}%"],
            ['Average Resolution Time', f"{report_data.get('avg_resolution_hours', 0)} hours"],
            ['Overdue Incidents', str(report_data.get('overdue_incidents', 0))]
        ]
        
        stats_table = Table(stats_data, colWidths=[200, 100])
        stats_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#3b82f6')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.white),
            ('BACKGROUND', (1, 0), (1, -1), colors.white),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        
        elements.append(stats_table)
        elements.append(Spacer(1, 20))
        
        # Severity Distribution
        if 'severity_distribution' in report_data:
            elements.append(Paragraph("Severity Distribution", self.styles['SectionHeader']))
            
            severity_data = [['Severity', 'Count', 'Percentage']]
            total = report_data.get('total_incidents', 1)
            
            for item in report_data['severity_distribution']:
                count = item.get('count', 0)
                percentage = (count / total * 100) if total > 0 else 0
                severity_data.append([
                    item.get('severity', '').title(),
                    str(count),
                    f"{percentage:.1f}%"
                ])
            
            severity_table = Table(severity_data, colWidths=[100, 80, 80])
            severity_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey)
            ]))
            
            elements.append(severity_table)
            elements.append(Spacer(1, 20))
        
        # Recent Incidents
        if 'recent_incidents' in report_data and report_data['recent_incidents']:
            elements.append(Paragraph("Recent Incidents", self.styles['SectionHeader']))
            
            incidents_data = [['Incident #', 'Title', 'Severity', 'Status', 'Created']]
            for incident in report_data['recent_incidents'][:10]:  # Limit to 10
                incidents_data.append([
                    incident.get('incident_number', ''),
                    incident.get('title', ''),
                    incident.get('severity', '').title(),
                    incident.get('status', '').title(),
                    incident.get('created_at', '').strftime('%Y-%m-%d') if hasattr(incident.get('created_at'), 'strftime') else str(incident.get('created_at', ''))
                ])
            
            incidents_table = Table(incidents_data, colWidths=[80, 150, 60, 80, 80])
            incidents_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey)
            ]))
            
            elements.append(incidents_table)
        
        return elements
    
    def generate_user_activity_pdf_content(self, report_data):
        """Generate PDF content for user activity reports"""
        elements = []
        
        # This would be implemented based on actual user activity data
        elements.append(Paragraph("User Activity Report", self.styles['SectionHeader']))
        elements.append(Paragraph("User activity data would be displayed here.", self.styles['Normal']))
        
        return elements
    
    def generate_security_pdf_content(self, report_data):
        """Generate PDF content for security reports"""
        elements = []
        
        elements.append(Paragraph("Security Report", self.styles['SectionHeader']))
        elements.append(Paragraph("Security metrics and findings would be displayed here.", self.styles['Normal']))
        
        return elements
    
    def generate_compliance_pdf_content(self, report_data):
        """Generate PDF content for compliance reports"""
        elements = []
        
        elements.append(Paragraph("Compliance Report", self.styles['SectionHeader']))
        elements.append(Paragraph("Compliance status and violations would be displayed here.", self.styles['Normal']))
        
        return elements
    
    def generate_csv_report(self, report_data, report_type):
        """
        Generate CSV report
        """
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Report Type', report_type.replace('_', ' ').title()])
        writer.writerow(['Generated At', now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        
        if report_type == 'incident':
            # Write summary
            writer.writerow(['Summary Statistics'])
            writer.writerow(['Total Incidents', report_data.get('total_incidents', 0)])
            writer.writerow(['Open Incidents', report_data.get('open_incidents', 0)])
            writer.writerow(['Resolved Incidents', report_data.get('resolved_incidents', 0)])
            writer.writerow(['Resolution Rate', f"{report_data.get('resolution_rate', 0)}%"])
            writer.writerow([])
            
            # Write severity distribution
            writer.writerow(['Severity Distribution'])
            writer.writerow(['Severity', 'Count', 'Percentage'])
            
            total = report_data.get('total_incidents', 1)
            for item in report_data.get('severity_distribution', []):
                count = item.get('count', 0)
                percentage = (count / total * 100) if total > 0 else 0
                writer.writerow([
                    item.get('severity', '').title(),
                    count,
                    f"{percentage:.1f}%"
                ])
            
            writer.writerow([])
            
            # Write recent incidents
            if 'recent_incidents' in report_data:
                writer.writerow(['Recent Incidents (Last 10)'])
                writer.writerow(['Incident #', 'Title', 'Severity', 'Status', 'Created'])
                
                for incident in report_data['recent_incidents'][:10]:
                    writer.writerow([
                        incident.get('incident_number', ''),
                        incident.get('title', ''),
                        incident.get('severity', '').title(),
                        incident.get('status', '').title(),
                        incident.get('created_at', '').strftime('%Y-%m-%d') if hasattr(incident.get('created_at'), 'strftime') else str(incident.get('created_at', ''))
                    ])
        
        return output.getvalue()
    
    def generate_excel_report(self, report_data, report_type):
        """
        Generate Excel report
        """
        output = BytesIO()
        
        if report_type == 'incident':
            # Create DataFrame for summary
            summary_data = {
                'Metric': ['Total Incidents', 'Open Incidents', 'Resolved Incidents', 'Resolution Rate', 'Avg Resolution Hours', 'Overdue Incidents'],
                'Value': [
                    report_data.get('total_incidents', 0),
                    report_data.get('open_incidents', 0),
                    report_data.get('resolved_incidents', 0),
                    f"{report_data.get('resolution_rate', 0)}%",
                    report_data.get('avg_resolution_hours', 0),
                    report_data.get('overdue_incidents', 0)
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            
            # Create DataFrame for severity distribution
            severity_data = []
            total = report_data.get('total_incidents', 1)
            
            for item in report_data.get('severity_distribution', []):
                count = item.get('count', 0)
                percentage = (count / total * 100) if total > 0 else 0
                severity_data.append({
                    'Severity': item.get('severity', '').title(),
                    'Count': count,
                    'Percentage': f"{percentage:.1f}%"
                })
            
            severity_df = pd.DataFrame(severity_data) if severity_data else pd.DataFrame()
            
            # Create DataFrame for recent incidents
            incidents_data = []
            if 'recent_incidents' in report_data:
                for incident in report_data['recent_incidents'][:20]:  # Limit to 20 in Excel
                    incidents_data.append({
                        'Incident #': incident.get('incident_number', ''),
                        'Title': incident.get('title', ''),
                        'Severity': incident.get('severity', '').title(),
                        'Status': incident.get('status', '').title(),
                        'Created': incident.get('created_at', '').strftime('%Y-%m-%d') if hasattr(incident.get('created_at'), 'strftime') else str(incident.get('created_at', '')),
                        'Assigned To': incident.get('assigned_to', '')
                    })
            
            incidents_df = pd.DataFrame(incidents_data) if incidents_data else pd.DataFrame()
            
            # Write to Excel
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                summary_df.to_excel(writer, sheet_name='Summary', index=False)
                if not severity_df.empty:
                    severity_df.to_excel(writer, sheet_name='Severity Distribution', index=False)
                if not incidents_df.empty:
                    incidents_df.to_excel(writer, sheet_name='Recent Incidents', index=False)
        
        output.seek(0)
        return output.getvalue()
    
    def generate_json_report(self, report_data, report_type):
        """
        Generate JSON report
        """
        report_json = {
            'report_type': report_type,
            'generated_at': now().isoformat(),
            'data': report_data
        }
        
        return json.dumps(report_json, default=str, indent=2)
    
    def generate_html_report(self, report_data, report_type):
        """
        Generate HTML report
        """
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{report_type.replace('_', ' ').title()} Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
                h1 {{ color: #1e40af; border-bottom: 2px solid #1e40af; padding-bottom: 10px; }}
                h2 {{ color: #374151; margin-top: 30px; }}
                .summary {{ background: #f3f4f6; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 20px 0; }}
                .stat-card {{ background: white; padding: 15px; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
                .stat-value {{ font-size: 24px; font-weight: bold; color: #1e40af; }}
                .stat-label {{ color: #6b7280; font-size: 14px; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th {{ background: #1e40af; color: white; padding: 12px; text-align: left; }}
                td {{ padding: 10px; border-bottom: 1px solid #e5e7eb; }}
                tr:hover {{ background: #f9fafb; }}
                .footer {{ margin-top: 40px; color: #9ca3af; font-size: 12px; text-align: center; }}
            </style>
        </head>
        <body>
            <h1>{report_type.replace('_', ' ').title()} Report</h1>
            <p>Generated: {timezone_now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        """
        
        if report_type == 'incident':
            html += """
            <div class="summary">
                <h2>Summary</h2>
                <div class="stats-grid">
            """
            
            # Summary cards
            stats = [
                ('Total Incidents', report_data.get('total_incidents', 0), '#3b82f6'),
                ('Open Incidents', report_data.get('open_incidents', 0), '#f59e0b'),
                ('Resolved', report_data.get('resolved_incidents', 0), '#10b981'),
                ('Resolution Rate', f"{report_data.get('resolution_rate', 0)}%", '#8b5cf6'),
                ('Avg Resolution', f"{report_data.get('avg_resolution_hours', 0)}h", '#ef4444'),
                ('Overdue', report_data.get('overdue_incidents', 0), '#dc2626')
            ]
            
            for label, value, color in stats:
                html += f"""
                <div class="stat-card">
                    <div class="stat-value" style="color: {color};">{value}</div>
                    <div class="stat-label">{label}</div>
                </div>
                """
            
            html += """
                </div>
            </div>
            """
            
            # Severity distribution
            if 'severity_distribution' in report_data:
                html += """
                <h2>Severity Distribution</h2>
                <table>
                    <tr>
                        <th>Severity</th>
                        <th>Count</th>
                        <th>Percentage</th>
                    </tr>
                """
                
                total = report_data.get('total_incidents', 1)
                for item in report_data['severity_distribution']:
                    count = item.get('count', 0)
                    percentage = (count / total * 100) if total > 0 else 0
                    
                    html += f"""
                    <tr>
                        <td>{item.get('severity', '').title()}</td>
                        <td>{count}</td>
                        <td>{percentage:.1f}%</td>
                    </tr>
                    """
                
                html += "</table>"
            
            # Recent incidents
            if 'recent_incidents' in report_data and report_data['recent_incidents']:
                html += """
                <h2>Recent Incidents</h2>
                <table>
                    <tr>
                        <th>Incident #</th>
                        <th>Title</th>
                        <th>Severity</th>
                        <th>Status</th>
                        <th>Created</th>
                        <th>Assigned To</th>
                    </tr>
                """
                
                for incident in report_data['recent_incidents'][:10]:
                    created_date = incident.get('created_at', '')
                    if hasattr(created_date, 'strftime'):
                        created_date = created_date.strftime('%Y-%m-%d')
                    
                    html += f"""
                    <tr>
                        <td>{incident.get('incident_number', '')}</td>
                        <td>{incident.get('title', '')}</td>
                        <td>{incident.get('severity', '').title()}</td>
                        <td>{incident.get('status', '').title()}</td>
                        <td>{created_date}</td>
                        <td>{incident.get('assigned_to', '')}</td>
                    </tr>
                    """
                
                html += "</table>"
        
        html += f"""
            <div class="footer">
                <p>Report generated by Hammer Tech AI-Enhanced Access Control & Compliance System</p>
                <p>© {now().year} Hammer Tech. All rights reserved.</p>
            </div>
        </body>
        </html>
        """
        
        return html


class DangerZoneAnalyzer:
    """Analyze logs for danger zone detection"""
    
    @staticmethod
    def analyze_logs_for_danger(timeframe_hours=24, risk_threshold=60):
        """
        Analyze recent logs for potential dangers
        """
        from django.utils.timezone import now as timezone_now
        from datetime import timedelta
        
        # Replace now() with timezone_now()
        cutoff_time = timezone_now() - timedelta(hours=timeframe_hours)
        
        # Get recent logs
        recent_logs = UserLog.objects.filter(
            timestamp__gte=cutoff_time
        ).order_by('-timestamp')[:1000]
        
        danger_logs = []
        
        for log in recent_logs:
            # Skip logs that already have incidents
            if hasattr(log, 'incidents') and log.incidents.exists():
                continue
            
            # Calculate risk score
            risk_score = IncidentUtils.calculate_risk_score(log)
            
            if risk_score >= risk_threshold:
                # Get additional context
                user_context = DangerZoneAnalyzer.get_user_context(log.user_email)
                ip_context = DangerZoneAnalyzer.get_ip_context(log.ip_address) if log.ip_address else {}
                
                danger_log = {
                    'id': log.id,
                    'activity': log.activity,
                    'description': log.description,
                    'user_email': log.user_email,
                    'timestamp': log.timestamp,
                    'ip_address': log.ip_address,
                    'endpoint': log.endpoint,
                    'risk_score': risk_score,
                    'danger_level': 'critical' if risk_score >= 80 else 'high' if risk_score >= 70 else 'medium',
                    'user_context': user_context,
                    'ip_context': ip_context,
                    'recommended_action': DangerZoneAnalyzer.get_recommended_action(log, risk_score)
                }
                
                danger_logs.append(danger_log)
        
        # Sort by risk score (highest first)
        danger_logs.sort(key=lambda x: x['risk_score'], reverse=True)
        
        return danger_logs[:100]
    
    @staticmethod
    def get_user_context(user_email):
        """Get context about a user for risk assessment"""
        from django.utils.timezone import now as timezone_now
        from datetime import timedelta
        
        try:
            user = CustomUser.objects.get(email=user_email)
            
            # Get user's recent failed logins
            recent_failed = UserLog.objects.filter(
                user_email=user_email,
                is_success=False,
                timestamp__gte=timezone_now() - timedelta(hours=1)
            ).count()
            
            # Get user's department
            department = None
            if user.role == 'employee' and user.department:
                department = user.department.name
            elif user.role == 'security_analyst' and user.departments.exists():
                department = ', '.join([dept.name for dept in user.departments.all()])
            
            # Get user's incident count
            incident_count = Incident.objects.filter(
                Q(log__user_email=user_email) |
                Q(assigned_to=user) |
                Q(created_by=user)
            ).count()
            
            return {
                'full_name': user.full_name,
                'role': user.role,
                'department': department,
                'status': user.status,
                'recent_failed_logins': recent_failed,
                'is_active': user.is_active,
                'incident_count': incident_count,
                'work_email': user.work_mail_address
            }
        except CustomUser.DoesNotExist:
            return {
                'error': 'User not found',
                'email': user_email
            }
        except Exception as e:
            logger.error(f"Error getting user context for {user_email}: {str(e)}")
            return {
                'error': 'Error retrieving user context',
                'email': user_email
            }
    
    @staticmethod
    def get_ip_context(ip_address):
        """Get context about an IP address"""
        from django.utils.timezone import now as timezone_now
        from datetime import timedelta
        
        if not ip_address:
            return {}
        
        try:
            # Get activities from same IP
            ip_activities = UserLog.objects.filter(
                ip_address=ip_address,
                timestamp__gte=timezone_now() - timedelta(hours=24)
            )
            
            unique_users = ip_activities.values('user_email').distinct().count()
            failed_attempts = ip_activities.filter(is_success=False).count()
            total_activities = ip_activities.count()
            
            # Get first and last seen
            first_log = ip_activities.order_by('timestamp').first()
            last_log = ip_activities.order_by('-timestamp').first()
            
            return {
                'total_activities': total_activities,
                'unique_users': unique_users,
                'failed_attempts': failed_attempts,
                'success_rate': round(((total_activities - failed_attempts) / total_activities * 100), 1) if total_activities > 0 else 0,
                'first_seen': first_log.timestamp if first_log else None,
                'last_seen': last_log.timestamp if last_log else None,
                'is_suspicious': unique_users > 3 or failed_attempts > 10
            }
        except Exception as e:
            logger.error(f"Error getting IP context for {ip_address}: {str(e)}")
            return {'error': 'Error retrieving IP context'}
    
    @staticmethod
    def get_recommended_action(log, risk_score):
        """Get recommended action based on log and risk score"""
        if risk_score >= 80:
            return "IMMEDIATE: Account suspension recommended. Security team notified."
        elif risk_score >= 70:
            return "URGENT: Security investigation required. Review user access immediately."
        elif risk_score >= 60:
            return "HIGH: Monitor closely. Consider additional authentication requirements."
        elif risk_score >= 50:
            return "MEDIUM: Review user activity and document findings."
        else:
            return "LOW: Monitor and review if pattern continues."
    
    @staticmethod
    def get_danger_zone_summary(timeframe_hours=24):
        """Get summary of danger zone activities"""
        from django.utils.timezone import now as timezone_now
        from datetime import timedelta
        
        cutoff_time = timezone_now() - timedelta(hours=timeframe_hours)
        
        summary = {
            'timeframe_hours': timeframe_hours,
            'total_logs_analyzed': UserLog.objects.filter(timestamp__gte=cutoff_time).count(),
            'danger_logs_count': 0,
            'risk_distribution': {'low': 0, 'medium': 0, 'high': 0, 'critical': 0},
            'top_risky_users': [],
            'top_risky_ips': []
        }
        
        # Get danger logs
        danger_logs = DangerZoneAnalyzer.analyze_logs_for_danger(timeframe_hours, 50)
        summary['danger_logs_count'] = len(danger_logs)
        
        # Analyze risk distribution
        for log in danger_logs:
            risk_score = log.get('risk_score', 0)
            if risk_score >= 80:
                summary['risk_distribution']['critical'] += 1
            elif risk_score >= 70:
                summary['risk_distribution']['high'] += 1
            elif risk_score >= 60:
                summary['risk_distribution']['medium'] += 1
            else:
                summary['risk_distribution']['low'] += 1
        
        # Get top risky users
        user_risk = {}
        for log in danger_logs:
            user_email = log.get('user_email')
            if user_email:
                if user_email not in user_risk:
                    user_risk[user_email] = 0
                user_risk[user_email] += log.get('risk_score', 0)
        
        summary['top_risky_users'] = sorted(
            [{'user': user, 'total_risk': risk} for user, risk in user_risk.items()],
            key=lambda x: x['total_risk'],
            reverse=True
        )[:5]
        
        # Get top risky IPs
        ip_risk = {}
        for log in danger_logs:
            ip = log.get('ip_address')
            if ip:
                if ip not in ip_risk:
                    ip_risk[ip] = 0
                ip_risk[ip] += log.get('risk_score', 0)
        
        summary['top_risky_ips'] = sorted(
            [{'ip': ip, 'total_risk': risk} for ip, risk in ip_risk.items()],
            key=lambda x: x['total_risk'],
            reverse=True
        )[:5]
        
        return summary

class ExportUtils:
    """Utility class for data exports"""
    
    @staticmethod
    def export_incidents_to_csv(incidents, include_comments=False):
        """Export incidents to CSV format"""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        headers = [
            'Incident Number', 'Title', 'Description', 'Status', 'Severity', 'Priority',
            'Risk Score', 'Created At', 'Assigned To', 'Department', 'SLA Due Date',
            'Resolved At', 'Resolution Notes'
        ]
        
        if include_comments:
            headers.append('Comments Count')
        
        writer.writerow(headers)
        
        # Write data
        for incident in incidents:
            row = [
                incident.incident_number,
                incident.title,
                incident.description,
                incident.status,
                incident.severity,
                incident.priority,
                incident.risk_score,
                incident.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                incident.assigned_to.email if incident.assigned_to else '',
                incident.department.name if incident.department else '',
                incident.sla_due_date.strftime('%Y-%m-%d %H:%M:%S') if incident.sla_due_date else '',
                incident.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if incident.resolved_at else '',
                incident.resolution_notes or ''
            ]
            
            if include_comments:
                row.append(incident.comments.count())
            
            writer.writerow(row)
        
        return output.getvalue()
    
    @staticmethod
    def export_incidents_to_excel(incidents, include_comments=False):
        """Export incidents to Excel format"""
        output = BytesIO()
        
        # Prepare data
        data = []
        for incident in incidents:
            row = {
                'Incident Number': incident.incident_number,
                'Title': incident.title,
                'Description': incident.description,
                'Status': incident.status,
                'Severity': incident.severity,
                'Priority': incident.priority,
                'Risk Score': incident.risk_score,
                'Created At': incident.created_at,
                'Assigned To': incident.assigned_to.email if incident.assigned_to else '',
                'Department': incident.department.name if incident.department else '',
                'SLA Due Date': incident.sla_due_date,
                'Resolved At': incident.resolved_at,
                'Resolution Notes': incident.resolution_notes or ''
            }
            
            if include_comments:
                row['Comments Count'] = incident.comments.count()
            
            data.append(row)
        
        if data:
            df = pd.DataFrame(data)
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Incidents', index=False)
        
        output.seek(0)
        return output.getvalue()


class NotificationUtils:
    """Utility class for sending notifications"""
    
    @staticmethod
    def send_incident_assignment_notification(incident):
        """Send notification when incident is assigned"""
        if not incident.assigned_to:
            return False
        
        try:
            from django.core.mail import send_mail
            from django.conf import settings
            
            subject = f"New Incident Assigned: {incident.incident_number}"
            
            message = f"""
            Hello {incident.assigned_to.full_name},
            
            A new incident has been assigned to you:
            
            Incident Number: {incident.incident_number}
            Title: {incident.title}
            Severity: {incident.severity.title()}
            Priority: {incident.priority.title()}
            
            Description:
            {incident.description}
            
            Please review and take appropriate action.
            
            You can view the incident at: {settings.FRONTEND_URL}/incidents/{incident.id}/
            
            Best regards,
            Hammer Tech Security Team
            """
            
            send_mail(
                subject=subject,
                message=message.strip(),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[incident.assigned_to.email],
                fail_silently=True
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send assignment notification: {str(e)}")
            return False
    
    @staticmethod
    def send_sla_violation_notification(incident):
        """Send notification when SLA is violated"""
        recipients = []
        
        # Add assigned user
        if incident.assigned_to:
            recipients.append(incident.assigned_to.email)
        
        # Add department heads for high severity incidents
        if incident.severity in ['high', 'critical'] and incident.department:
            # Get department head/manager (you might need to adjust this based on your model)
            pass
        
        # Add security team
        security_team = CustomUser.objects.filter(role='security_analyst', is_active=True)
        recipients.extend([user.email for user in security_team])
        
        if not recipients:
            return False
        
        try:
            from django.core.mail import send_mail
            from django.conf import settings
            
            subject = f"⚠️ SLA Violation: {incident.incident_number}"
            
            overdue_hours = (timezone_now() - incident.sla_due_date).total_seconds() / 3600
            
            message = f"""
            ATTENTION: SLA Violation Detected
            
            Incident: {incident.incident_number}
            Title: {incident.title}
            Severity: {incident.severity.title()}
            Assigned To: {incident.assigned_to.full_name if incident.assigned_to else 'Unassigned'}
            
            SLA Due Date: {incident.sla_due_date.strftime('%Y-%m-%d %H:%M:%S')}
            Overdue By: {overdue_hours:.1f} hours
            
            Current Status: {incident.status}
            
            This incident requires immediate attention!
            
            Please escalate if necessary.
            
            Best regards,
            Hammer Tech Compliance System
            """
            
            send_mail(
                subject=subject,
                message=message.strip(),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=list(set(recipients)),  # Remove duplicates
                fail_silently=True
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send SLA violation notification: {str(e)}")
            return False
    
    @staticmethod
    def send_resolution_notification(incident):
        """Send notification when incident is resolved"""
        recipients = []
        
        # Add creator
        if incident.created_by:
            recipients.append(incident.created_by.email)
        
        # Add user who triggered the log
        if incident.log and incident.log.user_email:
            recipients.append(incident.log.user_email)
        
        # Add security team for high severity
        if incident.severity in ['high', 'critical']:
            security_team = CustomUser.objects.filter(role='security_analyst', is_active=True)
            recipients.extend([user.email for user in security_team])
        
        if not recipients:
            return False
        
        try:
            from django.core.mail import send_mail
            from django.conf import settings
            
            subject = f"✅ Incident Resolved: {incident.incident_number}"
            
            resolution_time = incident.time_to_resolution
            if resolution_time:
                hours = resolution_time.total_seconds() / 3600
                resolution_str = f"{hours:.1f} hours"
            else:
                resolution_str = "N/A"
            
            message = f"""
            Good news! An incident has been resolved:
            
            Incident: {incident.incident_number}
            Title: {incident.title}
            Severity: {incident.severity.title()}
            
            Resolved By: {incident.assigned_to.full_name if incident.assigned_to else 'System'}
            Resolution Time: {resolution_str}
            
            Resolution Notes:
            {incident.resolution_notes or 'No notes provided.'}
            
            Status: {incident.status}
            
            Best regards,
            Hammer Tech Security Team
            """
            
            send_mail(
                subject=subject,
                message=message.strip(),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=list(set(recipients)),
                fail_silently=True
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send resolution notification: {str(e)}")
            return False


# Helper functions for views
def get_incident_data_for_report(filters):
    """Get incident data for report generation"""
    queryset = Incident.objects.all()
    
    # Apply filters
    if filters.get('date_from'):
        queryset = queryset.filter(created_at__date__gte=filters['date_from'])
    if filters.get('date_to'):
        queryset = queryset.filter(created_at__date__lte=filters['date_to'])
    if filters.get('severity'):
        queryset = queryset.filter(severity=filters['severity'])
    if filters.get('status'):
        queryset = queryset.filter(status=filters['status'])
    if filters.get('department_id'):
        queryset = queryset.filter(department_id=filters['department_id'])
    if filters.get('user_id'):
        queryset = queryset.filter(
            Q(log__user__id=filters['user_id']) |
            Q(assigned_to_id=filters['user_id']) |
            Q(created_by_id=filters['user_id'])
        )
    
    # Get statistics
    statistics = IncidentUtils.get_incident_statistics()
    
    # Get recent incidents
    recent_incidents = list(queryset.order_by('-created_at')[:20].values(
        'incident_number', 'title', 'severity', 'status', 'created_at', 'assigned_to__email'
    ))
    
    # Update statistics with filtered data
    statistics['total_incidents'] = queryset.count()
    statistics['open_incidents'] = queryset.filter(
        status__in=['pending', 'investigating', 'assigned', 'in_progress']
    ).count()
    statistics['resolved_incidents'] = queryset.filter(
        status__in=['resolved', 'closed']
    ).count()
    statistics['recent_incidents'] = recent_incidents
    
    # Calculate filtered resolution rate
    if queryset.count() > 0:
        statistics['resolution_rate'] = round(
            (statistics['resolved_incidents'] / queryset.count() * 100), 1
        )
    
    return statistics

def save_report_file(report, content, format_type):
    """Save report file to storage within MEDIA_ROOT with proper path handling"""
    try:
        # Generate unique filename
        timestamp = timezone_now().strftime('%Y%m%d_%H%M%S')
        filename = f"report_{report.report_number}_{timestamp}.{format_type}"
        
        # Create directory structure within MEDIA_ROOT
        # Use MEDIA_ROOT as base (this is the absolute path)
        year = str(timezone_now().year)
        month = str(timezone_now().month)
        report_dir = os.path.join(settings.MEDIA_ROOT, 'reports', year, month)
        
        # Create directory if it doesn't exist
        os.makedirs(report_dir, exist_ok=True)
        
        # Full absolute path to the file
        file_full_path = os.path.join(report_dir, filename)
        
        # Calculate relative path from MEDIA_ROOT for database storage
        # This will be like: reports/2026/2/report_REP-XXX_timestamp.pdf
        relative_path = os.path.join('reports', year, month, filename)
        
        print("\n" + "="*80)
        print("📁 REPORT FILE SAVE OPERATION")
        print("="*80)
        print(f"\n📋 Report Details:")
        print(f"   Report Number: {report.report_number}")
        print(f"   Title: {report.title}")
        print(f"   Format: {format_type}")
        
        print(f"\n📂 Directory Information:")
        print(f"   MEDIA_ROOT: {settings.MEDIA_ROOT}")
        print(f"   Report Directory: {report_dir}")
        print(f"   Directory Exists: {os.path.exists(report_dir)}")
        
        print(f"\n📄 File Paths:")
        print(f"   Filename: {filename}")
        print(f"   Full Absolute Path: {file_full_path}")
        print(f"   Relative Path (for DB): {relative_path}")
        
        # Save file
        if format_type in ['pdf', 'xlsx', 'excel']:
            # Binary files
            with open(file_full_path, 'wb') as f:
                f.write(content)
            print(f"\n✅ Binary file written successfully")
        else:
            # Text files (csv, json, html)
            with open(file_full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"\n✅ Text file written successfully")
        
        # Verify file was created
        if os.path.exists(file_full_path):
            file_size = os.path.getsize(file_full_path)
            print(f"\n📊 File Verification:")
            print(f"   File Exists: ✅ YES")
            print(f"   File Size: {file_size:,} bytes ({file_size / 1024:.2f} KB)")
        else:
            print(f"\n❌ ERROR: File was not created at {file_full_path}")
            return False
        
        # Update report with relative path (NOT absolute path)
        report.file_path = relative_path  # Store relative path like: reports/2026/2/filename.pdf
        report.file_size = file_size
        report.save()
        
        print(f"\n💾 Database Update:")
        print(f"   Stored Path in DB: {report.file_path}")
        print(f"   File Size in DB: {report.file_size:,} bytes")
        
        print(f"\n🔗 Download Information:")
        print(f"   Download URL: /incidents/reports/{report.id}/file/")
        print(f"   File will be retrieved from: {file_full_path}")
        
        print("="*80 + "\n")
        
        return True
        
    except Exception as e:
        error_msg = f"Failed to save report file: {str(e)}"
        logger.error(error_msg)
        print(f"\n❌ ERROR: {error_msg}")
        import traceback
        print(f"Traceback:\n{traceback.format_exc()}")
        print("="*80 + "\n")
        return False
    




class IncidentAuditTrigger:
    """Automatically trigger compliance audits based on incident criteria"""
    
    @staticmethod
    def check_and_trigger_audit(incident):
        """Check if incident should trigger a compliance audit"""
        
        # Criteria for automatic audit creation
        should_trigger = False
        trigger_reason = ""
        
        if incident.severity in ['critical', 'high']:
            should_trigger = True
            trigger_reason = f"High severity incident ({incident.severity})"
        
        elif incident.sla_violated:
            should_trigger = True
            trigger_reason = "SLA violation"
        
        elif Incident.objects.filter(
            log__user=incident.log.user,
            created_at__gte=timezone_now() - timedelta(days=30)
        ).count() >= 3:
            should_trigger = True
            trigger_reason = "Repeat incidents from same user"
        
        elif 'data breach' in incident.title.lower() or 'privacy' in incident.description.lower():
            should_trigger = True
            trigger_reason = "Data/privacy related incident"
        
        if should_trigger:
            IncidentAuditTrigger.create_automatic_audit(incident, trigger_reason)
    
    @staticmethod
    def create_automatic_audit(incident, trigger_reason):
        """Create an automatic compliance audit"""
        from complianceAuditApp.utils import IncidentBasedAuditCreator
        from userApp.models import CustomUser
        
        # Get system user or admin user for automatic creation
        try:
            system_user = CustomUser.objects.get(role='admin', is_active=True)
        except CustomUser.DoesNotExist:
            system_user = CustomUser.objects.filter(is_active=True).first()
        
        if system_user:
            try:
                audit = IncidentBasedAuditCreator.create_audit_from_incident(
                    incident, 
                    system_user,
                    None  # Auto-determine standard
                )
                
                # Update audit description with trigger reason
                audit.description = f"{audit.description}\n\nAutomatically triggered because: {trigger_reason}"
                audit.save()
                
                logger.info(f"Automatic audit created: {audit.audit_id} for incident {incident.incident_number}")
                
            except Exception as e:
                logger.error(f"Failed to create automatic audit: {str(e)}")