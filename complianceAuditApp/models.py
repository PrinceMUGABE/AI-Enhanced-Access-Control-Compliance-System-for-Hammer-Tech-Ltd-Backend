from django.db import models
from django.conf import settings
import uuid
from django.utils.timezone import now
from userApp.models import CustomUser
from incidentApp.models import Incident
from departmentApp.models import Department


class ComplianceStandard(models.Model):
    """Model for different compliance standards"""
    
    STANDARD_TYPES = [
        ('gdpr', 'GDPR'),
        ('iso27001', 'ISO 27001'),
        ('soc2', 'SOC 2'),
        ('hipaa', 'HIPAA'),
        ('pci_dss', 'PCI DSS'),
        ('rwanda_dpa', 'Rwanda Data Protection Act'),
        ('nist', 'NIST Cybersecurity Framework'),
        ('custom', 'Custom Standard'),
    ]
    
    # Basic Information
    name = models.CharField(max_length=200, unique=True)
    standard_type = models.CharField(max_length=50, choices=STANDARD_TYPES)
    version = models.CharField(max_length=20)
    description = models.TextField()
    
    # Status & Dates
    is_active = models.BooleanField(default=True)
    
    # Control Metrics
    total_controls = models.IntegerField(default=0)
    mandatory_controls = models.IntegerField(default=0)
    
    # Auto-incrementing counter for control IDs
    control_counter = models.IntegerField(default=0)
    
    # Metadata
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_standards'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['standard_type', 'is_active']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.name} v{self.version}"
    
    def generate_control_id(self):
        """Generate a unique control ID for this standard"""
        # Get standard type prefix
        prefix_map = {
            'gdpr': 'GDPR',
            'iso27001': 'ISO27K',
            'soc2': 'SOC2',
            'hipaa': 'HIPAA',
            'pci_dss': 'PCI',
            'rwanda_dpa': 'RDPA',
            'nist': 'NIST',
            'custom': 'CSTM',
        }
        prefix = prefix_map.get(self.standard_type, 'CTRL')
        
        # Increment counter
        self.control_counter += 1
        self.save(update_fields=['control_counter'])
        
        # Format: PREFIX-VERSIONSHORT-XXXX (e.g., ISO27K-2022-0001)
        version_short = self.version.replace('.', '')[:4]
        control_number = str(self.control_counter).zfill(4)
        
        return f"{prefix}-{version_short}-{control_number}"
    
    @property
    def compliance_score(self):
        """Calculate overall compliance score for this standard"""
        from django.db.models import Avg
        score = self.audits.filter(status='completed').aggregate(
            avg_score=Avg('overall_score')
        )['avg_score']
        return round(score, 2) if score else 0
    
    @property
    def active_audits_count(self):
        return self.audits.filter(status='in_progress').count()


class ComplianceAudit(models.Model):
    """Main audit model for compliance assessments"""
    
    AUDIT_STATUS = [
        ('draft', 'Draft'),
        ('planned', 'Planned'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    AUDIT_TYPES = [
        ('internal', 'Internal Audit'),
        ('external', 'External Audit'),
        ('regulatory', 'Regulatory Audit'),
        ('certification', 'Certification Audit'),
        ('incident_response', 'Incident Response Audit'),
    ]
    
    # Identification
    audit_id = models.CharField(max_length=50, unique=True, editable=False)
    title = models.CharField(max_length=500)
    description = models.TextField()
    
    # Core Relationships
    standard = models.ForeignKey(
        ComplianceStandard,
        on_delete=models.PROTECT,
        related_name='audits'
    )
    related_incidents = models.ManyToManyField(
        Incident,
        related_name='compliance_audits',
        blank=True
    )
    triggered_by_incident = models.ForeignKey(
        Incident,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggered_audits'
    )
    
    # Audit Details
    audit_type = models.CharField(max_length=50, choices=AUDIT_TYPES, default='internal')
    status = models.CharField(max_length=20, choices=AUDIT_STATUS, default='draft')
    priority = models.CharField(max_length=20, choices=[
        ('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')
    ], default='medium')
    
    # Schedule
    planned_start_date = models.DateField()
    planned_end_date = models.DateField()
    actual_start_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank=True)
    
    # Team & Responsibilities
    lead_auditor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='led_audits'
    )
    departments = models.ManyToManyField(
        Department,
        related_name='compliance_audits',
        blank=True
    )
    
    # Scores & Metrics
    overall_score = models.FloatField(null=True, blank=True)  # 0-100
    controls_assessed = models.IntegerField(default=0)
    compliance_rate = models.FloatField(null=True, blank=True)  # Calculated percentage
    
    # Risk Correlation
    risk_score_from_incident = models.FloatField(null=True, blank=True)
    incident_severity_match = models.BooleanField(default=False)
    
    # Findings Statistics (auto-calculated)
    total_findings = models.IntegerField(default=0)
    open_findings = models.IntegerField(default=0)
    critical_findings = models.IntegerField(default=0)
    
    # Metadata
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_audits'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'planned_start_date']),
            models.Index(fields=['audit_type', 'status']),
            models.Index(fields=['standard', 'status']),
        ]
    
    def __str__(self):
        return f"{self.audit_id}: {self.title}"
    
    # In models.py, update the ComplianceAudit.save() method:
    def save(self, *args, **kwargs):
        if not self.audit_id:
            self.audit_id = f"AUD-{uuid.uuid4().hex[:8].upper()}"
        
        # Call parent save first to get the primary key
        super().save(*args, **kwargs)
        
        # Auto-calculate fields AFTER saving
        self.update_metrics()
    
    def update_metrics(self):
        """Update calculated metrics"""
        # Update findings count
        findings = self.findings.all()
        self.total_findings = findings.count()
        self.open_findings = findings.filter(status='open').count()
        self.critical_findings = findings.filter(
            risk_level='critical'
        ).count()
        
        # Update controls count
        self.controls_assessed = self.control_assessments.count()
        
        # Calculate compliance rate
        if self.controls_assessed > 0:
            compliant_controls = self.control_assessments.filter(
                status='compliant'
            ).count()
            self.compliance_rate = round((compliant_controls / self.controls_assessed) * 100, 2)
    
    def calculate_risk_score(self):
        """Calculate risk score from related incidents"""
        incidents = self.related_incidents.all()
        if not incidents:
            return None
        
        severity_weights = {
            'critical': 1.0,
            'high': 0.75,
            'medium': 0.5,
            'low': 0.25
        }
        
        total_weight = 0
        weighted_sum = 0
        
        for incident in incidents:
            weight = severity_weights.get(incident.severity, 0.5)
            weighted_sum += weight
            total_weight += 1
        
        if total_weight > 0:
            return round((weighted_sum / total_weight) * 100, 2)
        return None


class AuditFinding(models.Model):
    """Detailed findings from compliance audits"""
    
    FINDING_TYPES = [
        ('major', 'Major'),
        ('minor', 'Minor'),
        ('observation', 'Observation'),
        ('incident_related', 'Incident-Related'),
    ]
    
    RISK_LEVELS = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    
    # Basic Information
    audit = models.ForeignKey(
        ComplianceAudit,
        on_delete=models.CASCADE,
        related_name='findings'
    )
    title = models.CharField(max_length=500)
    description = models.TextField()
    
    # Classification
    finding_type = models.CharField(max_length=50, choices=FINDING_TYPES, default='minor')
    risk_level = models.CharField(max_length=20, choices=RISK_LEVELS, default='medium')
    
    # Incident Relationship
    related_incident = models.ForeignKey(
        Incident,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='findings'
    )
    
    # Status & Tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    target_completion_date = models.DateField(null=True, blank=True)
    actual_completion_date = models.DateField(null=True, blank=True)
    
    # Responsibility
    assigned_to = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_findings'
    )
    
    # Evidence & Documentation
    evidence = models.TextField(blank=True, null=True)
    remediation_plan = models.TextField(blank=True, null=True)
    
    # Metadata
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_findings'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'risk_level']),
            models.Index(fields=['audit', 'status']),
        ]
    
    def __str__(self):
        return f"{self.title}"
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update audit metrics
        self.audit.update_metrics()
    
    @property
    def is_overdue(self):
        if self.target_completion_date and self.status in ['open', 'in_progress']:
            return now().date() > self.target_completion_date
        return False


class ControlAssessment(models.Model):
    """Assessment of individual controls during an audit"""
    
    STATUS_CHOICES = [
        ('not_assessed', 'Not Assessed'),
        ('compliant', 'Compliant'),
        ('non_compliant', 'Non-Compliant'),
        ('partially_compliant', 'Partially Compliant'),
        ('not_applicable', 'Not Applicable'),
    ]
    
    REMEDIATION_STATUS = [
        ('not_required', 'Not Required'),
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('verified', 'Verified'),
    ]
    
    # Core Information
    audit = models.ForeignKey(
        ComplianceAudit,
        on_delete=models.CASCADE,
        related_name='control_assessments'
    )
    
    # AUTO-GENERATED Control ID
    control_id = models.CharField(max_length=100, unique=True, editable=False)
    control_name = models.CharField(max_length=500)
    control_description = models.TextField()
    
    # Control Category (optional for better organization)
    control_category = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="e.g., Access Control, Data Protection, Network Security"
    )
    
    # Assessment Details
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='not_assessed')
    assessment_date = models.DateField(null=True, blank=True)
    assessed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assessed_controls'
    )
    
    # Evidence & Documentation
    evidence = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    attachments = models.JSONField(default=list, blank=True)  # Store file references
    
    # Remediation
    remediation_required = models.BooleanField(default=False)
    remediation_status = models.CharField(
        max_length=50,
        choices=REMEDIATION_STATUS,
        default='not_required'
    )
    remediation_deadline = models.DateField(null=True, blank=True)
    remediation_notes = models.TextField(blank=True, null=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['control_id']
        indexes = [
            models.Index(fields=['audit', 'status']),
            models.Index(fields=['status', 'remediation_required']),
            models.Index(fields=['control_id']),
        ]
    
    def __str__(self):
        return f"{self.control_id}: {self.control_name}"
    
    def save(self, *args, **kwargs):
        # Auto-generate control_id if not exists
        if not self.control_id:
            # Get the compliance standard from the audit
            standard = self.audit.standard
            self.control_id = standard.generate_control_id()
        
        super().save(*args, **kwargs)
        
        # Update audit metrics
        self.audit.update_metrics()
        
        # Update standard total_controls count
        if self.pk:
            standard = self.audit.standard
            standard.total_controls = ControlAssessment.objects.filter(
                audit__standard=standard
            ).values('control_id').distinct().count()
            standard.save(update_fields=['total_controls'])


class ComplianceReport(models.Model):
    """Generated compliance reports"""
    
    REPORT_TYPES = [
        ('audit_report', 'Audit Report'),
        ('compliance_summary', 'Compliance Summary'),
        ('gap_analysis', 'Gap Analysis'),
        ('finding_summary', 'Finding Summary'),
        ('control_assessment', 'Control Assessment'),
    ]
    
    FORMATS = [
        ('pdf', 'PDF'),
        ('excel', 'Excel'),
        ('csv', 'CSV'),
        ('html', 'HTML'),
    ]
    
    # Report Information
    report_id = models.CharField(max_length=100, unique=True, editable=False)
    title = models.CharField(max_length=500)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPES)
    format = models.CharField(max_length=10, choices=FORMATS)
    
    # Content & Storage
    file_path = models.FileField(upload_to='compliance_reports/', null=True, blank=True)
    file_content = models.TextField(blank=True, null=True)
    parameters = models.JSONField(default=dict)  # Store generation parameters
    
    # Scope & Context
    audit = models.ForeignKey(
        ComplianceAudit,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports'
    )
    standard = models.ForeignKey(
        ComplianceStandard,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports'
    )
    
    # Metadata
    generated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name='generated_reports'
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    download_count = models.IntegerField(default=0)
    
    class Meta:
        ordering = ['-generated_at']
    
    def __str__(self):
        return f"{self.report_id}: {self.title}"
    
    def save(self, *args, **kwargs):
        if not self.report_id:
            self.report_id = f"REP-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
    
    def increment_download(self):
        self.download_count += 1
        self.save()


class DashboardMetrics(models.Model):
    """Store aggregated dashboard metrics for performance"""
    
    metric_date = models.DateField(unique=True)
    
    # Audit Metrics
    total_audits = models.IntegerField(default=0)
    completed_audits = models.IntegerField(default=0)
    in_progress_audits = models.IntegerField(default=0)
    incident_audits = models.IntegerField(default=0)
    
    # Finding Metrics
    total_findings = models.IntegerField(default=0)
    open_findings = models.IntegerField(default=0)
    critical_findings = models.IntegerField(default=0)
    overdue_findings = models.IntegerField(default=0)
    
    # Control Metrics
    total_controls_assessed = models.IntegerField(default=0)
    compliant_controls = models.IntegerField(default=0)
    
    # Standard Metrics
    total_standards = models.IntegerField(default=0)
    active_standards = models.IntegerField(default=0)
    
    # Compliance Score
    overall_compliance_score = models.FloatField(default=0)
    
    # Calculated at
    calculated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-metric_date']
    
    def __str__(self):
        return f"Metrics for {self.metric_date}"