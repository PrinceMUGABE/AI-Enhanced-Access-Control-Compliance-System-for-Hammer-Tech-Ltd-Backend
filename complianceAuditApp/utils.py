import os
import json
import csv
import io
import pandas as pd
from datetime import datetime, timedelta
from django.db.models import Q, Count, Avg, F, Sum, Max
from django.utils.timezone import now
from django.http import HttpResponse
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
import logging

from .models import (
    ComplianceStandard, ComplianceAudit, ControlAssessment,
    AuditFinding, ComplianceReport
)
from incidentApp.models import Incident
from userApp.models import CustomUser
from departmentApp.models import Department
from userApp.utils import ActivityLogger

# logger = logging.getLogger(__name__)


class ComplianceCalculator:
    """Utility class for compliance calculations"""
    
    @staticmethod
    def calculate_organization_compliance():
        """Calculate overall organization compliance score"""
        # Get all completed audits
        completed_audits = ComplianceAudit.objects.filter(
            status='completed',
            overall_score__isnull=False
        )
        
        if not completed_audits.exists():
            return {
                'overall_score': 0,
                'audit_count': 0,
                'departments_audited': 0,
                'standards_covered': 0,
                'compliance_level': 'unknown'
            }
        
        # Calculate weighted average
        total_weight = 0
        weighted_score = 0
        
        for audit in completed_audits:
            # Weight by number of controls assessed
            weight = audit.controls_assessed
            total_weight += weight
            weighted_score += audit.overall_score * weight
        
        overall_score = weighted_score / total_weight if total_weight > 0 else 0
        
        # Get statistics
        departments_audited = Department.objects.filter(
            compliance_audits__status='completed'
        ).distinct().count()
        
        standards_covered = ComplianceStandard.objects.filter(
            audits__status='completed'
        ).distinct().count()
        
        # Determine compliance level
        if overall_score >= 90:
            level = 'excellent'
        elif overall_score >= 75:
            level = 'good'
        elif overall_score >= 60:
            level = 'fair'
        else:
            level = 'poor'
        
        return {
            'overall_score': round(overall_score, 1),
            'audit_count': completed_audits.count(),
            'departments_audited': departments_audited,
            'standards_covered': standards_covered,
            'compliance_level': level
        }
    
    @staticmethod
    def calculate_department_compliance(department_id):
        """Calculate compliance score for a specific department"""
        department = Department.objects.get(id=department_id)
        
        # Get department's completed audits
        audits = department.compliance_audits.filter(status='completed')
        
        if not audits.exists():
            return {
                'department_id': department.id,
                'department_name': department.name,
                'overall_score': 0,
                'audit_count': 0,
                'standards_assessed': [],
                'compliance_level': 'unknown'
            }
        
        # Calculate average score
        total_score = sum(audit.overall_score for audit in audits if audit.overall_score)
        avg_score = total_score / audits.count()
        
        # Get standards assessed
        standards_assessed = audits.values(
            'standard__name',
            'standard__standard_type'
        ).annotate(
            avg_score=Avg('overall_score'),
            last_audit=Max('actual_end_date')
        )
        
        # Determine compliance level
        if avg_score >= 90:
            level = 'excellent'
        elif avg_score >= 75:
            level = 'good'
        elif avg_score >= 60:
            level = 'fair'
        else:
            level = 'poor'
        
        return {
            'department_id': department.id,
            'department_name': department.name,
            'overall_score': round(avg_score, 1),
            'audit_count': audits.count(),
            'standards_assessed': list(standards_assessed),
            'compliance_level': level,
            'open_findings': AuditFinding.objects.filter(
                audit__departments=department,
                status__in=['open', 'in_progress']
            ).count()
        }
    
    @staticmethod
    def calculate_standard_compliance(standard_id):
        """Calculate compliance for a specific standard"""
        standard = ComplianceStandard.objects.get(id=standard_id)
        
        # Get completed audits for this standard
        audits = standard.audits.filter(status='completed')
        
        if not audits.exists():
            return {
                'standard_id': standard.id,
                'standard_name': standard.name,
                'standard_type': standard.standard_type,
                'overall_score': 0,
                'audit_count': 0,
                'departments_assessed': 0,
                'compliance_level': 'unknown'
            }
        
        # Calculate average score
        total_score = sum(audit.overall_score for audit in audits if audit.overall_score)
        avg_score = total_score / audits.count()
        
        # Get departments assessed
        departments_assessed = audits.values('departments__name').distinct().count()
        
        # Get control-level statistics
        controls = standard.controls.all()
        control_stats = []
        
        for control in controls:
            assessments = ControlAssessment.objects.filter(
                control=control,
                audit__status='completed'
            )
            
            if assessments.exists():
                compliant = assessments.filter(status='compliant').count()
                total = assessments.count()
                compliance_rate = (compliant / total) * 100 if total > 0 else 0
                
                control_stats.append({
                    'control_id': control.control_id,
                    'control_title': control.title,
                    'assessments_count': total,
                    'compliance_rate': round(compliance_rate, 1)
                })
        
        # Determine compliance level
        if avg_score >= 90:
            level = 'excellent'
        elif avg_score >= 75:
            level = 'good'
        elif avg_score >= 60:
            level = 'fair'
        else:
            level = 'poor'
        
        return {
            'standard_id': standard.id,
            'standard_name': standard.name,
            'standard_type': standard.standard_type,
            'overall_score': round(avg_score, 1),
            'audit_count': audits.count(),
            'departments_assessed': departments_assessed,
            'control_stats': control_stats[:10],  # Limit to 10 controls
            'compliance_level': level
        }


class AuditScheduler:
    """Utility class for scheduling compliance audits"""
    
    @staticmethod
    def get_upcoming_audits(days_ahead=30):
        """Get audits scheduled in the next X days"""
        cutoff_date = now() + timedelta(days=days_ahead)
        
        upcoming = ComplianceAudit.objects.filter(
            status__in=['planned', 'in_progress'],
            planned_start_date__lte=cutoff_date
        ).select_related('standard', 'lead_auditor')
        
        return upcoming
    
    @staticmethod
    def check_overdue_audits():
        """Check for audits that are overdue"""
        today = now().date()
        
        overdue = ComplianceAudit.objects.filter(
            status='in_progress',
            planned_end_date__lt=today,
            actual_end_date__isnull=True
        ).select_related('standard', 'lead_auditor')
        
        return overdue
    
    @staticmethod
    def generate_audit_schedule(standard_id, department_ids, start_date, frequency_days):
        """Generate audit schedule for standards and departments"""
        schedule = []
        
        standard = ComplianceStandard.objects.get(id=standard_id)
        departments = Department.objects.filter(id__in=department_ids)
        
        current_date = start_date
        
        for department in departments:
            schedule.append({
                'standard': standard.name,
                'department': department.name,
                'scheduled_date': current_date,
                'frequency_days': frequency_days,
                'next_date': current_date + timedelta(days=frequency_days)
            })
            
            current_date += timedelta(days=frequency_days)
        
        return schedule


class ReportGenerator:
    """Generate compliance reports"""
    
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
    
    def generate_compliance_report(self, audit_id, format_type='pdf'):
        """Generate compliance report for an audit"""
        audit = ComplianceAudit.objects.get(id=audit_id)
        
        # Gather report data
        report_data = {
            'audit': audit,
            'controls_assessed': audit.control_assessments.all(),
            'findings': audit.findings.all(),
            'statistics': {
                'total_controls': audit.standard.total_controls,
                'controls_assessed': audit.controls_assessed,
                'compliance_rate': audit.overall_score,
                'findings_count': audit.findings_count,
                'major_findings': audit.major_findings,
                'minor_findings': audit.minor_findings
            }
        }
        
        # Generate based on format
        if format_type == 'pdf':
            return self.generate_pdf_report(report_data)
        elif format_type == 'excel':
            return self.generate_excel_report(report_data)
        elif format_type == 'csv':
            return self.generate_csv_report(report_data)
        else:
            return self.generate_html_report(report_data)
    
    def generate_multiaudit_pdf(self, report_data):
        """Generate PDF for multiple audits"""
        buffer = io.BytesIO()
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
        elements.append(Paragraph(
            f"Multi-Audit Compliance Report",
            self.styles['ReportTitle']
        ))
        
        # Add overall statistics
        elements.append(Paragraph("Overall Statistics", self.styles['SectionHeader']))
        
        stats_table = Table([
            ['Total Audits', str(report_data['overall_stats']['total_audits'])],
            ['Average Score', f"{report_data['overall_stats']['average_score']:.1f}%"],
            ['Total Findings', str(report_data['overall_stats']['total_findings'])],
            ['Open Findings', str(report_data['overall_stats']['open_findings'])]
        ], colWidths=[150, 100])
        
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
        
        # Add audit details
        elements.append(Paragraph("Audit Details", self.styles['SectionHeader']))
        
        audit_data = []
        audit_data.append(['Audit ID', 'Standard', 'Score', 'Findings', 'Status'])
        
        for audit_item in report_data['audits']:
            audit = audit_item['audit']
            audit_data.append([
                audit.audit_id,
                audit.standard.name,
                f"{audit.overall_score or 0}%",
                str(audit_item['controls_assessed']),
                audit.status
            ])
        
        audit_table = Table(audit_data, colWidths=[100, 150, 70, 70, 80])
        audit_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ALIGN', (2, 1), (2, -1), 'CENTER'),
            ('ALIGN', (3, 1), (3, -1), 'CENTER')
        ]))
        
        elements.append(audit_table)
        
        # Build PDF
        doc.build(elements)
        buffer.seek(0)
        
        return buffer.getvalue()

    def generate_multiaudit_excel(self, report_data):
        """Generate Excel report for multiple audits"""
        output = io.BytesIO()
        
        # Create summary DataFrame
        summary_data = {
            'Metric': ['Total Audits', 'Average Score', 'Total Findings', 'Open Findings'],
            'Value': [
                report_data['overall_stats']['total_audits'],
                f"{report_data['overall_stats']['average_score']:.1f}%",
                report_data['overall_stats']['total_findings'],
                report_data['overall_stats']['open_findings']
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        
        # Create audit details DataFrame
        audit_details = []
        for audit_item in report_data['audits']:
            audit = audit_item['audit']
            audit_details.append({
                'Audit ID': audit.audit_id,
                'Title': audit.title,
                'Standard': audit.standard.name,
                'Score': audit.overall_score or 0,
                'Controls Assessed': audit_item['controls_assessed'],
                'Status': audit.status,
                'Start Date': audit.planned_start_date,
                'End Date': audit.planned_end_date
            })
        
        audit_df = pd.DataFrame(audit_details) if audit_details else pd.DataFrame()
        
        # Write to Excel
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            if not audit_df.empty:
                audit_df.to_excel(writer, sheet_name='Audit Details', index=False)
        
        output.seek(0)
        return output.getvalue()

    def generate_multiaudit_csv(self, report_data):
        """Generate CSV report for multiple audits"""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Multi-Audit Compliance Report'])
        writer.writerow(['Generated on', now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        
        # Write summary
        writer.writerow(['Overall Statistics'])
        writer.writerow(['Total Audits', report_data['overall_stats']['total_audits']])
        writer.writerow(['Average Score', f"{report_data['overall_stats']['average_score']:.1f}%"])
        writer.writerow(['Total Findings', report_data['overall_stats']['total_findings']])
        writer.writerow(['Open Findings', report_data['overall_stats']['open_findings']])
        writer.writerow([])
        
        # Write audit details
        writer.writerow(['Audit Details'])
        writer.writerow(['Audit ID', 'Title', 'Standard', 'Score', 'Controls', 'Status', 'Start Date', 'End Date'])
        
        for audit_item in report_data['audits']:
            audit = audit_item['audit']
            writer.writerow([
                audit.audit_id,
                audit.title,
                audit.standard.name,
                f"{audit.overall_score or 0}%",
                audit_item['controls_assessed'],
                audit.status,
                audit.planned_start_date,
                audit.planned_end_date
            ])
        
        return output.getvalue()

    def generate_multiaudit_html(self, report_data):
        """Generate HTML report for multiple audits"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Multi-Audit Compliance Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
                h1 {{ color: #1e40af; border-bottom: 2px solid #1e40af; padding-bottom: 10px; }}
                h2 {{ color: #374151; margin-top: 30px; }}
                .summary {{ background: #f3f4f6; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th {{ background: #1e40af; color: white; padding: 12px; text-align: left; }}
                td {{ padding: 10px; border-bottom: 1px solid #e5e7eb; }}
                .stats {{ display: flex; gap: 20px; margin: 20px 0; }}
                .stat-card {{ background: white; border: 1px solid #e5e7eb; border-radius: 5px; padding: 20px; flex: 1; }}
                .stat-value {{ font-size: 24px; font-weight: bold; color: #1e40af; }}
                .stat-label {{ color: #6b7280; font-size: 14px; }}
                .footer {{ margin-top: 40px; color: #9ca3af; font-size: 12px; text-align: center; }}
            </style>
        </head>
        <body>
            <h1>Multi-Audit Compliance Report</h1>
            
            <div class="summary">
                <h2>Overall Statistics</h2>
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-value">{report_data['overall_stats']['total_audits']}</div>
                        <div class="stat-label">Total Audits</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{report_data['overall_stats']['average_score']:.1f}%</div>
                        <div class="stat-label">Average Score</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{report_data['overall_stats']['total_findings']}</div>
                        <div class="stat-label">Total Findings</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{report_data['overall_stats']['open_findings']}</div>
                        <div class="stat-label">Open Findings</div>
                    </div>
                </div>
            </div>
            
            <h2>Audit Details</h2>
            <table>
                <tr>
                    <th>Audit ID</th>
                    <th>Title</th>
                    <th>Standard</th>
                    <th>Score</th>
                    <th>Controls Assessed</th>
                    <th>Status</th>
                    <th>Start Date</th>
                    <th>End Date</th>
                </tr>
        """
        
        for audit_item in report_data['audits']:
            audit = audit_item['audit']
            html += f"""
                <tr>
                    <td>{audit.audit_id}</td>
                    <td>{audit.title}</td>
                    <td>{audit.standard.name}</td>
                    <td>{audit.overall_score or 0}%</td>
                    <td>{audit_item['controls_assessed']}</td>
                    <td>{audit.status}</td>
                    <td>{audit.planned_start_date}</td>
                    <td>{audit.planned_end_date}</td>
                </tr>
            """
        
        html += f"""
            </table>
            
            <div class="footer">
                <p>Report generated on {now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Hammer Tech AI-Enhanced Access Control & Compliance System</p>
            </div>
        </body>
        </html>
        """
        
        return html



    def generate_multiaudit_report(self, audit_ids, format_type='pdf'):
        """Generate report for multiple audits"""
        audits = ComplianceAudit.objects.filter(id__in=audit_ids).select_related('standard', 'lead_auditor')
        
        report_data = {
            'audits': [],
            'overall_stats': {
                'total_audits': len(audits),
                'average_score': 0,
                'total_findings': 0,
                'open_findings': 0
            }
        }
        
        total_score = 0
        for audit in audits:
            # Get audit details
            audit_data = {
                'audit': audit,
                'findings': audit.findings.all(),
                'controls_assessed': audit.control_assessments.count()
            }
            report_data['audits'].append(audit_data)
            
            # Update overall stats
            total_score += audit.overall_score or 0
            report_data['overall_stats']['total_findings'] += audit.findings.count()
            report_data['overall_stats']['open_findings'] += audit.findings.filter(status='open').count()
        
        if len(audits) > 0:
            report_data['overall_stats']['average_score'] = total_score / len(audits)
        
        # Generate report based on format
        if format_type == 'pdf':
            return self.generate_multiaudit_pdf(report_data)
        elif format_type == 'excel':
            return self.generate_multiaudit_excel(report_data)
        elif format_type == 'csv':
            return self.generate_multiaudit_csv(report_data)
        else:
            return self.generate_multiaudit_html(report_data)


class ComplianceMonitor:
    """Monitor compliance status and generate alerts"""
    
    @staticmethod
    def check_upcoming_deadlines(days_ahead=30):
        """Check for upcoming compliance deadlines"""
        today = now().date()
        deadline_date = today + timedelta(days=days_ahead)
        
        # Check audit remediation deadlines
        audit_deadlines = AuditFinding.objects.filter(
            status__in=['open', 'in_progress'],
            target_completion_date__lte=deadline_date,
            target_completion_date__gte=today
        ).select_related('audit', 'responsible_party').order_by('target_completion_date')
        
        # Check control assessment remediation deadlines
        control_deadlines = ControlAssessment.objects.filter(
            remediation_required=True,
            remediation_deadline__lte=deadline_date,
            remediation_deadline__gte=today,
            remediation_status__in=['open', 'in_progress']
        ).select_related('control', 'audit').order_by('remediation_deadline')
        
        return {
            'audit_deadlines': list(audit_deadlines),
            'control_deadlines': list(control_deadlines)
        }
    
    @staticmethod
    def check_expired_certifications():
        """Check for expired or expiring certifications"""
        today = now().date()
        warning_date = today + timedelta(days=90)  # 90-day warning
        
        # Get standards that need review
        expiring_standards = ComplianceStandard.objects.filter(
            is_active=True,
            review_date__lte=warning_date
        ).order_by('review_date')
        
        return expiring_standards
    
    @staticmethod
    def generate_compliance_alerts():
        """Generate compliance alerts for dashboard"""
        alerts = []
        
        # Check overdue audits
        overdue_audits = AuditScheduler.check_overdue_audits()
        for audit in overdue_audits:
            overdue_days = (now().date() - audit.planned_end_date).days
            alerts.append({
                'type': 'overdue_audit',
                'severity': 'high',
                'title': f'Overdue Audit: {audit.audit_id}',
                'description': f'Audit is {overdue_days} days overdue',
                'entity_id': audit.id,
                'entity_type': 'audit',
                'due_date': audit.planned_end_date
            })
        
        # Check upcoming deadlines (next 7 days)
        deadlines = ComplianceMonitor.check_upcoming_deadlines(7)
        
        for deadline in deadlines['audit_deadlines']:
            days_remaining = (deadline.target_completion_date - now().date()).days
            alerts.append({
                'type': 'remediation_deadline',
                'severity': 'medium' if days_remaining > 3 else 'high',
                'title': f'Remediation Due: {deadline.title}',
                'description': f'Remediation due in {days_remaining} days',
                'entity_id': deadline.id,
                'entity_type': 'finding',
                'due_date': deadline.target_completion_date
            })
        
        # Check expiring standards (next 30 days)
        expiring_standards = ComplianceMonitor.check_expired_certifications()
        for standard in expiring_standards:
            days_remaining = (standard.review_date - now().date()).days
            if days_remaining <= 30:
                alerts.append({
                    'type': 'expiring_standard',
                    'severity': 'medium',
                    'title': f'Standard Review Due: {standard.name}',
                    'description': f'Review due in {days_remaining} days',
                    'entity_id': standard.id,
                    'entity_type': 'standard',
                    'due_date': standard.review_date
                })
        
        return alerts
    



class IncidentBasedAuditCreator:
    """Create compliance audits based on incidents"""
    
    @staticmethod
    def create_audit_from_incident(incident, user, standard_id=None):
        """Create a compliance audit triggered by an incident"""
        from .models import ComplianceAudit, ComplianceStandard
        
        try:
            # Determine appropriate standard if not specified
            if not standard_id:
                standard_id = IncidentBasedAuditCreator.determine_standard_from_incident(incident)
            
            standard = ComplianceStandard.objects.get(id=standard_id)
            
            # Generate audit title based on incident
            title = f"Incident Response Audit: {incident.incident_number} - {incident.title}"
            
            # Create audit
            audit = ComplianceAudit.objects.create(
                title=title,
                description=f"Compliance audit triggered by incident {incident.incident_number}. {incident.description}",
                standard=standard,
                audit_type='incident_response',
                triggered_by_incident=incident,
                status='planned',
                planned_start_date=now().date(),
                planned_end_date=now().date() + timedelta(days=7),  # 1-week audit
                created_by=user
            )
            
            # Add incident to related incidents
            audit.related_incidents.add(incident)
            
            # Calculate risk from incident
            audit.risk_score_from_incident = IncidentBasedAuditCreator.calculate_risk_score(incident)
            audit.save()
            
            # Log activity
            ActivityLogger.create_log(
                user=user,
                log_type='compliance',
                activity='incident_audit_created',
                description=f'Created compliance audit {audit.audit_id} from incident {incident.incident_number}',
                is_success=True
            )
            
            # Generate initial findings from incident
            IncidentBasedAuditCreator.create_findings_from_incident(audit, incident, user)
            
            return audit
            
        except Exception as e:
            # logger.error(f"Error creating audit from incident: {str(e)}")
            raise
    
    @staticmethod
    def determine_standard_from_incident(incident):
        """Determine appropriate compliance standard based on incident type"""
        # Map incident severity/type to standards
        if 'data' in incident.description.lower() or 'privacy' in incident.description.lower():
            # GDPR or data protection standards
            try:
                return ComplianceStandard.objects.get(standard_type='gdpr').id
            except:
                return ComplianceStandard.objects.filter(standard_type__in=['gdpr', 'hipaa', 'rwanda_dpa']).first().id
        
        elif 'security' in incident.description.lower() or 'breach' in incident.title.lower():
            # Security standards
            try:
                return ComplianceStandard.objects.get(standard_type='iso27001').id
            except:
                return ComplianceStandard.objects.filter(standard_type__in=['iso27001', 'nist', 'soc2']).first().id
        
        elif 'access' in incident.description.lower() or 'login' in incident.title.lower():
            # Access control standards
            try:
                return ComplianceStandard.objects.get(standard_type='iso27001').id
            except:
                return ComplianceStandard.objects.filter(standard_type='iso27001').first().id
        
        # Default to first active standard
        return ComplianceStandard.objects.filter(is_active=True).first().id
    
    @staticmethod
    def calculate_risk_score(incident):
        """Calculate risk score from incident severity"""
        severity_scores = {
            'critical': 90,
            'high': 70,
            'medium': 50,
            'low': 30
        }
        
        base_score = severity_scores.get(incident.severity, 50)
        
        # Adjust based on other factors
        adjustments = 0
        
        # SLA violation increases risk
        if incident.sla_violated:
            adjustments += 20
        
        # Multiple incidents from same source increases risk
        related_incidents_count = Incident.objects.filter(
            log__user=incident.log.user
        ).count()
        
        if related_incidents_count > 1:
            adjustments += min(related_incidents_count * 5, 30)
        
        return min(base_score + adjustments, 100)
    
    @staticmethod
    def create_findings_from_incident(audit, incident, user):
        """Create initial findings from incident details"""
        from .models import AuditFinding
        
        # Create main finding from incident
        main_finding = AuditFinding.objects.create(
            audit=audit,
            related_incident=incident,
            title=f"Incident {incident.incident_number}: {incident.title}",
            description=f"Compliance issue identified from incident: {incident.description}\n\n"
                       f"Incident Details:\n"
                       f"- Severity: {incident.severity}\n"
                       f"- Priority: {incident.priority}\n"
                       f"- Status: {incident.status}\n"
                       f"- Created: {incident.created_at}",
            risk_level=incident.severity if incident.severity in ['low', 'medium', 'high'] else 'medium',
            finding_type='incident_related',
            status='open',
            created_by=user,
            target_completion_date=now().date() + timedelta(days=14)  # 2 weeks to resolve
        )
        
        # Additional findings based on incident details
        additional_findings = []
        
        if incident.sla_violated:
            additional_findings.append({
                'title': 'SLA Violation in Incident Response',
                'description': f'Incident {incident.incident_number} violated SLA requirements.\n'
                             f'Expected resolution time was not met, indicating potential compliance gaps '
                             f'in incident response procedures.',
                'risk_level': 'high'
            })
        
        if incident.escalated_by:
            additional_findings.append({
                'title': 'Incident Escalation Required',
                'description': f'Incident {incident.incident_number} required escalation to {incident.escalated_by.full_name}.\n'
                             f'This indicates potential gaps in initial response capabilities.',
                'risk_level': 'medium'
            })
        
        # Create additional findings
        for finding_data in additional_findings:
            AuditFinding.objects.create(
                audit=audit,
                related_incident=incident,
                **finding_data,
                finding_type='incident_related',
                status='open',
                created_by=user,
                target_completion_date=now().date() + timedelta(days=21)
            )
        
        return main_finding