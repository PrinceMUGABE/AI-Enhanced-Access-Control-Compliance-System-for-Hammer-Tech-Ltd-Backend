import pandas as pd
from io import BytesIO, StringIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from django.http import HttpResponse
from datetime import datetime
import json
from django.utils.timezone import now, localtime
import csv


class ReportGenerator:
    """Generate various compliance reports"""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
    
    def generate_audit_report(self, audit, format='pdf'):
        """Generate detailed audit report"""
        print(f"ReportGenerator: Generating {format} report for audit {audit.audit_id}")
        
        # Map formats to file extensions
        format_extensions = {
            'pdf': '.pdf',
            'excel': '.xlsx',
            'csv': '.csv',
            'html': '.html'
        }
        
        extension = format_extensions.get(format, '.bin')
        
        if format == 'pdf':
            buffer = self._generate_audit_pdf_report(audit)
            filename = f"audit_report_{audit.audit_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{extension}"
        elif format == 'excel':
            buffer = self._generate_audit_excel_report(audit)
            filename = f"audit_report_{audit.audit_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{extension}"
        elif format == 'csv':
            buffer = self._generate_audit_csv_report(audit)
            filename = f"audit_report_{audit.audit_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{extension}"
        elif format == 'html':
            buffer = self._generate_audit_html_report(audit)
            filename = f"audit_report_{audit.audit_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{extension}"
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        return buffer, filename

    def _generate_audit_pdf_report(self, audit):
        """Generate PDF report for an audit"""
        print(f"Generating PDF report for audit {audit.audit_id}")
        buffer = BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        elements = []
        
        # Title
        title_style = self.styles['Title']
        title = Paragraph(f"Compliance Audit Report: {audit.audit_id}", title_style)
        elements.append(title)
        elements.append(Spacer(1, 20))
        
        # Audit Details
        details_data = [
            ['Audit ID:', audit.audit_id],
            ['Title:', audit.title],
            ['Standard:', f"{audit.standard.name} (v{audit.standard.version})"],
            ['Status:', audit.status],
            ['Audit Type:', audit.audit_type],
            ['Lead Auditor:', audit.lead_auditor.full_name if audit.lead_auditor else 'Not Assigned'],
            ['Planned Start:', audit.planned_start_date.strftime('%Y-%m-%d')],
            ['Planned End:', audit.planned_end_date.strftime('%Y-%m-%d')],
            ['Overall Score:', f"{audit.overall_score or 0}%" if audit.overall_score else 'N/A'],
            ['Compliance Rate:', f"{audit.compliance_rate or 0}%" if audit.compliance_rate else 'N/A'],
        ]
        
        details_table = Table(details_data, colWidths=[150, 300])
        details_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey)
        ]))
        
        elements.append(details_table)
        elements.append(Spacer(1, 20))
        
        # Findings Summary
        findings = audit.findings.all()
        if findings.exists():
            elements.append(Paragraph("Findings Summary", self.styles['Heading2']))
            elements.append(Spacer(1, 10))
            
            findings_data = [['ID', 'Title', 'Risk Level', 'Status', 'Due Date']]
            for finding in findings:
                findings_data.append([
                    str(finding.id)[:8],
                    finding.title[:50] + '...' if len(finding.title) > 50 else finding.title,
                    finding.risk_level,
                    finding.status,
                    finding.target_completion_date.strftime('%Y-%m-%d') if finding.target_completion_date else 'N/A'
                ])
            
            findings_table = Table(findings_data, colWidths=[80, 200, 70, 70, 80])
            findings_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('ALIGN', (2, 1), (2, -1), 'CENTER'),
                ('ALIGN', (3, 1), (3, -1), 'CENTER'),
                ('ALIGN', (4, 1), (4, -1), 'CENTER')
            ]))
            
            elements.append(findings_table)
            elements.append(Spacer(1, 20))
        
        # Control Assessments
        controls = audit.control_assessments.all()
        if controls.exists():
            elements.append(Paragraph("Control Assessments", self.styles['Heading2']))
            elements.append(Spacer(1, 10))
            
            controls_data = [['Control ID', 'Control Name', 'Status', 'Remediation']]
            for control in controls:
                controls_data.append([
                    control.control_id,
                    control.control_name[:50] + '...' if len(control.control_name) > 50 else control.control_name,
                    control.status,
                    'Required' if control.remediation_required else 'Not Required'
                ])
            
            controls_table = Table(controls_data, colWidths=[100, 250, 80, 80])
            controls_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey),
                ('ALIGN', (2, 1), (2, -1), 'CENTER'),
                ('ALIGN', (3, 1), (3, -1), 'CENTER')
            ]))
            
            elements.append(controls_table)
            elements.append(Spacer(1, 20))
        
        # Footer
        elements.append(Paragraph(f"Report generated on: {now().strftime('%Y-%m-%d %H:%M:%S')}", self.styles['Normal']))
        elements.append(Paragraph("Hammer Tech AI-Enhanced Access Control & Compliance System", self.styles['Italic']))
        
        # Build PDF
        try:
            doc.build(elements)
            buffer.seek(0)
            print(f"PDF report generated successfully. Size: {len(buffer.getvalue())} bytes")
            return buffer
        except Exception as e:
            print(f"Error generating PDF: {str(e)}")
            raise
    
    def _generate_audit_excel_report(self, audit):
        """Generate Excel report for an audit"""
        print(f"Generating Excel report for audit {audit.audit_id}")
        output = BytesIO()
        
        # Helper function to convert timezone-aware datetime to naive
        def convert_datetime(value):
            if value and hasattr(value, 'tzinfo') and value.tzinfo is not None:
                # Convert to local time and remove timezone
                return localtime(value).replace(tzinfo=None)
            return value
        
        # Create audit summary DataFrame
        audit_summary = {
            'Audit ID': [audit.audit_id],
            'Title': [audit.title],
            'Standard': [audit.standard.name],
            'Version': [audit.standard.version],
            'Status': [audit.status],
            'Audit Type': [audit.audit_type],
            'Lead Auditor': [audit.lead_auditor.full_name if audit.lead_auditor else ''],
            'Planned Start': [audit.planned_start_date],
            'Planned End': [audit.planned_end_date],
            'Overall Score': [audit.overall_score or 0],
            'Compliance Rate': [audit.compliance_rate or 0],
            'Controls Assessed': [audit.controls_assessed],
            'Total Findings': [audit.total_findings],
            'Open Findings': [audit.open_findings],
            'Critical Findings': [audit.critical_findings]
        }
        summary_df = pd.DataFrame(audit_summary)
        
        # Create findings DataFrame
        findings_data = []
        for finding in audit.findings.all():
            findings_data.append({
                'ID': str(finding.id),
                'Title': finding.title,
                'Description': finding.description[:200] if finding.description else '',
                'Type': finding.finding_type,
                'Risk Level': finding.risk_level,
                'Status': finding.status,
                'Assigned To': finding.assigned_to.full_name if finding.assigned_to else '',
                'Target Date': finding.target_completion_date,
                'Created Date': convert_datetime(finding.created_at)
            })
        
        findings_df = pd.DataFrame(findings_data) if findings_data else pd.DataFrame()
        
        # Create controls DataFrame
        controls_data = []
        for control in audit.control_assessments.all():
            controls_data.append({
                'Control ID': control.control_id,
                'Control Name': control.control_name,
                'Description': control.control_description[:200] if control.control_description else '',
                'Status': control.status,
                'Assessment Date': control.assessment_date,
                'Assessed By': control.assessed_by.full_name if control.assessed_by else '',
                'Remediation Required': 'Yes' if control.remediation_required else 'No',
                'Remediation Status': control.remediation_status,
                'Remediation Deadline': control.remediation_deadline
            })
        controls_df = pd.DataFrame(controls_data) if controls_data else pd.DataFrame()
        
        # Write to Excel
        try:
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Write summary sheet
                summary_df.to_excel(writer, sheet_name='Audit Summary', index=False)
                
                # Write findings sheet if data exists
                if not findings_df.empty:
                    findings_df.to_excel(writer, sheet_name='Findings', index=False)
                
                # Write controls sheet if data exists
                if not controls_df.empty:
                    controls_df.to_excel(writer, sheet_name='Controls', index=False)
            
            output.seek(0)
            print(f"Excel report generated successfully. Size: {len(output.getvalue())} bytes")
            return output
        except Exception as e:
            print(f"Error generating Excel report: {str(e)}")
            # Fallback: create a simple Excel file
            return self._create_simple_excel_report(audit)
    
    def _create_simple_excel_report(self, audit):
        """Create a simple Excel report as fallback"""
        output = BytesIO()
        
        # Create a simple DataFrame
        data = {
            'Audit Information': ['Audit ID', 'Title', 'Standard', 'Status', 'Generated Date'],
            'Details': [
                audit.audit_id,
                audit.title,
                f"{audit.standard.name} v{audit.standard.version}",
                audit.status,
                now().strftime('%Y-%m-%d %H:%M:%S')
            ]
        }
        
        df = pd.DataFrame(data)
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Audit Report', index=False)
        
        output.seek(0)
        return output
    
    def _generate_audit_csv_report(self, audit):
        """Generate CSV report for an audit"""
        print(f"Generating CSV report for audit {audit.audit_id}")
        
        # Use StringIO for CSV text data
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Compliance Audit Report'])
        writer.writerow(['Generated on:', now().strftime('%Y-%m-%d %H:%M:%S')])
        writer.writerow([])
        
        # Write audit details
        writer.writerow(['Audit Details'])
        writer.writerow(['Audit ID:', audit.audit_id])
        writer.writerow(['Title:', audit.title])
        writer.writerow(['Standard:', f"{audit.standard.name} (v{audit.standard.version})"])
        writer.writerow(['Status:', audit.status])
        writer.writerow(['Audit Type:', audit.audit_type])
        writer.writerow(['Overall Score:', f"{audit.overall_score or 0}%" if audit.overall_score else 'N/A'])
        writer.writerow(['Compliance Rate:', f"{audit.compliance_rate or 0}%" if audit.compliance_rate else 'N/A'])
        writer.writerow([])
        
        # Write findings
        findings = audit.findings.all()
        if findings.exists():
            writer.writerow(['Findings'])
            writer.writerow(['ID', 'Title', 'Risk Level', 'Status', 'Assigned To', 'Target Date'])
            for finding in findings:
                writer.writerow([
                    str(finding.id),
                    finding.title,
                    finding.risk_level,
                    finding.status,
                    finding.assigned_to.full_name if finding.assigned_to else '',
                    finding.target_completion_date.strftime('%Y-%m-%d') if finding.target_completion_date else ''
                ])
            writer.writerow([])
        
        # Write controls
        controls = audit.control_assessments.all()
        if controls.exists():
            writer.writerow(['Control Assessments'])
            writer.writerow(['Control ID', 'Control Name', 'Status', 'Remediation Required', 'Remediation Status'])
            for control in controls:
                writer.writerow([
                    control.control_id,
                    control.control_name,
                    control.status,
                    'Yes' if control.remediation_required else 'No',
                    control.remediation_status
                ])
        
        # Convert StringIO to BytesIO for consistency
        csv_bytes = BytesIO(output.getvalue().encode('utf-8'))
        print(f"CSV report generated successfully. Size: {len(csv_bytes.getvalue())} bytes")
        return csv_bytes
    
    def _generate_audit_html_report(self, audit):
        """Generate HTML report for an audit"""
        print(f"Generating HTML report for audit {audit.audit_id}")
        
        # Get data
        findings = audit.findings.all()
        controls = audit.control_assessments.all()
        
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Compliance Audit Report: {audit.audit_id}</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    background: #f8f9fa;
                    padding: 20px;
                }}
                
                .report-container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 10px;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                }}
                
                .header {{
                    background: linear-gradient(135deg, #1e40af, #3b82f6);
                    color: white;
                    padding: 40px;
                    text-align: center;
                }}
                
                .header h1 {{
                    font-size: 28px;
                    margin-bottom: 10px;
                    font-weight: 700;
                }}
                
                .header .subtitle {{
                    font-size: 16px;
                    opacity: 0.9;
                }}
                
                .audit-id {{
                    display: inline-block;
                    background: rgba(255, 255, 255, 0.2);
                    padding: 8px 16px;
                    border-radius: 20px;
                    font-size: 14px;
                    margin-top: 15px;
                }}
                
                .content {{
                    padding: 40px;
                }}
                
                .section {{
                    margin-bottom: 40px;
                }}
                
                .section-title {{
                    color: #1e40af;
                    font-size: 20px;
                    font-weight: 600;
                    margin-bottom: 20px;
                    padding-bottom: 10px;
                    border-bottom: 2px solid #e5e7eb;
                }}
                
                .info-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                
                .info-card {{
                    background: #f8fafc;
                    padding: 20px;
                    border-radius: 8px;
                    border-left: 4px solid #3b82f6;
                }}
                
                .info-card h3 {{
                    color: #374151;
                    font-size: 14px;
                    font-weight: 600;
                    margin-bottom: 8px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                
                .info-card p {{
                    color: #1f2937;
                    font-size: 16px;
                    font-weight: 500;
                }}
                
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin: 20px 0;
                }}
                
                th {{
                    background: #f3f4f6;
                    color: #374151;
                    font-weight: 600;
                    padding: 12px 16px;
                    text-align: left;
                    border-bottom: 2px solid #e5e7eb;
                }}
                
                td {{
                    padding: 12px 16px;
                    border-bottom: 1px solid #e5e7eb;
                    color: #4b5563;
                }}
                
                tr:hover {{
                    background: #f9fafb;
                }}
                
                .badge {{
                    display: inline-block;
                    padding: 4px 12px;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: 600;
                    text-transform: uppercase;
                }}
                
                .status-draft {{ background: #f3f4f6; color: #6b7280; }}
                .status-planned {{ background: #dbeafe; color: #1d4ed8; }}
                .status-in_progress {{ background: #fef3c7; color: #d97706; }}
                .status-completed {{ background: #d1fae5; color: #065f46; }}
                
                .risk-critical {{ background: #fee2e2; color: #991b1b; }}
                .risk-high {{ background: #fed7aa; color: #9a3412; }}
                .risk-medium {{ background: #fef3c7; color: #92400e; }}
                .risk-low {{ background: #d1fae5; color: #065f46; }}
                
                .control-compliant {{ background: #d1fae5; color: #065f46; }}
                .control-non_compliant {{ background: #fee2e2; color: #991b1b; }}
                .control-partial {{ background: #fef3c7; color: #92400e; }}
                
                .footer {{
                    background: #f8fafc;
                    padding: 30px;
                    text-align: center;
                    border-top: 1px solid #e5e7eb;
                    color: #6b7280;
                    font-size: 14px;
                }}
                
                .footer p {{
                    margin: 5px 0;
                }}
                
                .footer .system-name {{
                    color: #3b82f6;
                    font-weight: 600;
                }}
                
                .empty-state {{
                    text-align: center;
                    padding: 40px;
                    color: #9ca3af;
                    font-style: italic;
                }}
                
                @media print {{
                    body {{
                        background: white;
                        padding: 0;
                    }}
                    
                    .report-container {{
                        box-shadow: none;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="report-container">
                <div class="header">
                    <h1>Compliance Audit Report</h1>
                    <div class="subtitle">Detailed audit findings and compliance assessment</div>
                    <div class="audit-id">{audit.audit_id}</div>
                </div>
                
                <div class="content">
                    <div class="section">
                        <h2 class="section-title">Audit Overview</h2>
                        <div class="info-grid">
                            <div class="info-card">
                                <h3>Audit Title</h3>
                                <p>{audit.title}</p>
                            </div>
                            <div class="info-card">
                                <h3>Compliance Standard</h3>
                                <p>{audit.standard.name} (v{audit.standard.version})</p>
                            </div>
                            <div class="info-card">
                                <h3>Status</h3>
                                <p><span class="badge status-{audit.status}">{audit.status.replace('_', ' ').title()}</span></p>
                            </div>
                            <div class="info-card">
                                <h3>Audit Type</h3>
                                <p>{audit.audit_type.replace('_', ' ').title()}</p>
                            </div>
                            <div class="info-card">
                                <h3>Lead Auditor</h3>
                                <p>{audit.lead_auditor.full_name if audit.lead_auditor else 'Not Assigned'}</p>
                            </div>
                            <div class="info-card">
                                <h3>Compliance Rate</h3>
                                <p>{audit.compliance_rate or 0}%</p>
                            </div>
                        </div>
                    </div>
                    
                    <div class="section">
                        <h2 class="section-title">Timeline</h2>
                        <div class="info-grid">
                            <div class="info-card">
                                <h3>Planned Start</h3>
                                <p>{audit.planned_start_date.strftime('%B %d, %Y')}</p>
                            </div>
                            <div class="info-card">
                                <h3>Planned End</h3>
                                <p>{audit.planned_end_date.strftime('%B %d, %Y')}</p>
                            </div>
                            <div class="info-card">
                                <h3>Actual Start</h3>
                                <p>{audit.actual_start_date.strftime('%B %d, %Y') if audit.actual_start_date else 'N/A'}</p>
                            </div>
                            <div class="info-card">
                                <h3>Actual End</h3>
                                <p>{audit.actual_end_date.strftime('%B %d, %Y') if audit.actual_end_date else 'N/A'}</p>
                            </div>
                        </div>
                    </div>
        """
        
        # Findings section
        if findings.exists():
            html += f"""
                    <div class="section">
                        <h2 class="section-title">Audit Findings ({findings.count()})</h2>
                        <table>
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Title</th>
                                    <th>Type</th>
                                    <th>Risk Level</th>
                                    <th>Status</th>
                                    <th>Target Date</th>
                                </tr>
                            </thead>
                            <tbody>
            """
            
            for finding in findings:
                html += f"""
                                <tr>
                                    <td>{str(finding.id)[:8]}...</td>
                                    <td>{finding.title}</td>
                                    <td>{finding.finding_type.replace('_', ' ').title()}</td>
                                    <td><span class="badge risk-{finding.risk_level}">{finding.risk_level.title()}</span></td>
                                    <td><span class="badge status-{finding.status}">{finding.status.replace('_', ' ').title()}</span></td>
                                    <td>{finding.target_completion_date.strftime('%Y-%m-%d') if finding.target_completion_date else 'N/A'}</td>
                                </tr>
                """
            
            html += """
                            </tbody>
                        </table>
                    </div>
            """
        else:
            html += """
                    <div class="section">
                        <h2 class="section-title">Audit Findings</h2>
                        <div class="empty-state">No findings reported for this audit.</div>
                    </div>
            """
        
        # Controls section
        if controls.exists():
            html += f"""
                    <div class="section">
                        <h2 class="section-title">Control Assessments ({controls.count()})</h2>
                        <table>
                            <thead>
                                <tr>
                                    <th>Control ID</th>
                                    <th>Control Name</th>
                                    <th>Status</th>
                                    <th>Remediation Required</th>
                                    <th>Remediation Status</th>
                                </tr>
                            </thead>
                            <tbody>
            """
            
            for control in controls:
                remediation_text = 'Yes' if control.remediation_required else 'No'
                html += f"""
                                <tr>
                                    <td>{control.control_id}</td>
                                    <td>{control.control_name}</td>
                                    <td><span class="badge control-{control.status}">{control.status.replace('_', ' ').title()}</span></td>
                                    <td>{remediation_text}</td>
                                    <td>{control.remediation_status.replace('_', ' ').title()}</td>
                                </tr>
                """
            
            html += """
                            </tbody>
                        </table>
                    </div>
            """
        else:
            html += """
                    <div class="section">
                        <h2 class="section-title">Control Assessments</h2>
                        <div class="empty-state">No control assessments reported for this audit.</div>
                    </div>
            """
        
        # Footer
        html += f"""
                </div>
                
                <div class="footer">
                    <p>Report generated on {now().strftime('%B %d, %Y at %H:%M:%S')}</p>
                    <p>Generated by: {audit.created_by.full_name if audit.created_by else 'System'}</p>
                    <p class="system-name">Hammer Tech AI-Enhanced Access Control & Compliance System</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Convert HTML string to BytesIO
        html_bytes = BytesIO(html.encode('utf-8'))
        print(f"HTML report generated successfully. Size: {len(html_bytes.getvalue())} bytes")
        return html_bytes