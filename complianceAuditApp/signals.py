from django.db.models.signals import post_save, pre_save, post_delete, m2m_changed
from django.dispatch import receiver
from django.utils.timezone import now
from django.db import transaction
import logging

from sympy import Q

from .models import (
    ComplianceAudit, AuditFinding, ControlAssessment,
    ComplianceStandard, ComplianceReport
)
from userApp.utils import ActivityLogger
from incidentApp.models import Incident

logger = logging.getLogger(__name__)


# ==================== AUDIT SIGNALS ====================

@receiver(post_save, sender=ComplianceAudit)
def audit_post_save(sender, instance, created, **kwargs):
    """
    Handle audit post-save operations
    - Update metrics
    - Create activity logs
    - Trigger notifications
    """
    try:
        # Update audit metrics
        instance.update_metrics()
        
        # Log activity
        if created:
            activity = 'audit_created'
            description = f'Created compliance audit: {instance.audit_id}'
        else:
            activity = 'audit_updated'
            description = f'Updated compliance audit: {instance.audit_id}'
        
        # Check if we have request context (from API)
        from django.core.handlers.wsgi import WSGIRequest
        import sys
        
        request = None
        for frame in sys._current_frames().values():
            for local_var in frame.f_locals.values():
                if isinstance(local_var, WSGIRequest):
                    request = local_var
                    break
            if request:
                break
        
        if request and hasattr(request, 'user'):
            user = request.user
        else:
            # Fallback to audit creator or lead auditor
            user = instance.created_by or instance.lead_auditor
        
        if user:
            ActivityLogger.create_log(
                user=user,
                log_type='compliance',
                activity=activity,
                description=description,
                request=request,
                response=None,
                is_success=True
            )
        
        # Handle status changes
        if not created:
            original_status = getattr(instance, '_original_status', None)
            if original_status and original_status != instance.status:
                # Status changed - send notifications
                _notify_audit_status_change(instance, original_status, instance.status)
        
        # Store original status for next update
        instance._original_status = instance.status
        
    except Exception as e:
        logger.error(f"Error in audit_post_save: {str(e)}", exc_info=True)


@receiver(m2m_changed, sender=ComplianceAudit.related_incidents.through)
def audit_incidents_changed(sender, instance, action, pk_set, **kwargs):
    """
    Handle audit-incident relationship changes
    """
    try:
        if action in ['post_add', 'post_remove', 'post_clear']:
            # Update risk score when incidents change
            risk_score = instance.calculate_risk_score()
            if risk_score != instance.risk_score_from_incident:
                instance.risk_score_from_incident = risk_score
                instance.save(update_fields=['risk_score_from_incident'])
            
            # Log the change
            if action == 'post_add' and pk_set:
                incidents = Incident.objects.filter(id__in=pk_set)
                incident_numbers = ', '.join([inc.incident_number for inc in incidents])
                
                from django.core.handlers.wsgi import WSGIRequest
                import sys
                
                request = None
                for frame in sys._current_frames().values():
                    for local_var in frame.f_locals.values():
                        if isinstance(local_var, WSGIRequest):
                            request = local_var
                            break
                    if request:
                        break
                
                if request and hasattr(request, 'user'):
                    user = request.user
                else:
                    user = instance.created_by or instance.lead_auditor
                
                if user:
                    ActivityLogger.create_log(
                        user=user,
                        log_type='compliance',
                        activity='incidents_linked_to_audit',
                        description=f'Linked incidents [{incident_numbers}] to audit {instance.audit_id}',
                        request=request,
                        response=None,
                        is_success=True
                    )
        
    except Exception as e:
        logger.error(f"Error in audit_incidents_changed: {str(e)}", exc_info=True)



# ==================== FINDING SIGNALS ====================

@receiver(post_save, sender=AuditFinding)
def finding_post_save(sender, instance, created, **kwargs):
    """
    Handle finding post-save operations
    - Update audit metrics
    - Create activity logs
    - Send notifications for critical findings
    """
    try:
        # Update parent audit metrics
        with transaction.atomic():
            instance.audit.update_metrics()
        
        # Log activity
        if created:
            activity = 'finding_created'
            description = f'Created audit finding: {instance.id}'
        else:
            activity = 'finding_updated'
            description = f'Updated audit finding: {instance.id}'
        
        # Get user from request context
        from django.core.handlers.wsgi import WSGIRequest
        import sys
        
        request = None
        for frame in sys._current_frames().values():
            for local_var in frame.f_locals.values():
                if isinstance(local_var, WSGIRequest):
                    request = local_var
                    break
            if request:
                break
        
        if request and hasattr(request, 'user'):
            user = request.user
        else:
            user = instance.created_by or instance.audit.created_by
        
        if user:
            ActivityLogger.create_log(
                user=user,
                log_type='compliance',
                activity=activity,
                description=description,
                request=request,
                response=None,
                is_success=True
            )
        
        # Handle status changes
        if not created:
            original_status = getattr(instance, '_original_status', None)
            if original_status and original_status != instance.status:
                # Status changed - send notifications
                _notify_finding_status_change(instance, original_status, instance.status)
                
                # If finding is now resolved/closed, check if assigned user needs notification
                if instance.status in ['resolved', 'closed'] and instance.assigned_to:
                    _notify_finding_resolved(instance)
        
        # Send notification for new critical findings
        if created and instance.risk_level == 'critical':
            _notify_critical_finding(instance)
        
        # Store original status for next update
        instance._original_status = instance.status
        
    except Exception as e:
        logger.error(f"Error in finding_post_save: {str(e)}", exc_info=True)



@receiver(post_delete, sender=AuditFinding)
def finding_post_delete(sender, instance, **kwargs):
    """
    Handle finding deletion
    """
    try:
        # Update parent audit metrics
        with transaction.atomic():
            instance.audit.update_metrics()
        
        # Log deletion
        from django.core.handlers.wsgi import WSGIRequest
        import sys
        
        request = None
        for frame in sys._current_frames().values():
            for local_var in frame.f_locals.values():
                if isinstance(local_var, WSGIRequest):
                    request = local_var
                    break
            if request:
                break
        
        if request and hasattr(request, 'user'):
            user = request.user
        else:
            user = instance.audit.created_by
        
        if user:
            ActivityLogger.create_log(
                user=user,
                log_type='compliance',
                activity='finding_deleted',
                description=f'Deleted audit finding: {instance.id}',
                request=request,
                response=None,
                is_success=True
            )
        
    except Exception as e:
        logger.error(f"Error in finding_post_delete: {str(e)}", exc_info=True)


# ==================== CONTROL ASSESSMENT SIGNALS ====================

@receiver(post_save, sender=ControlAssessment)
def control_assessment_post_save(sender, instance, created, **kwargs):
    """
    Handle control assessment post-save operations
    """
    try:
        # Update parent audit metrics
        with transaction.atomic():
            instance.audit.update_metrics()
        
        # Log activity
        if created:
            activity = 'control_assessment_created'
            description = f'Created control assessment: {instance.control_id}'
        else:
            activity = 'control_assessment_updated'
            description = f'Updated control assessment: {instance.control_id}'
        
        # Get user from context
        from django.core.handlers.wsgi import WSGIRequest
        import sys
        
        request = None
        for frame in sys._current_frames().values():
            for local_var in frame.f_locals.values():
                if isinstance(local_var, WSGIRequest):
                    request = local_var
                    break
            if request:
                break
        
        if request and hasattr(request, 'user'):
            user = request.user
        else:
            user = instance.assessed_by or instance.audit.created_by
        
        if user:
            ActivityLogger.create_log(
                user=user,
                log_type='compliance',
                activity=activity,
                description=description,
                request=request,
                response=None,
                is_success=True
            )
        
    except Exception as e:
        logger.error(f"Error in control_assessment_post_save: {str(e)}", exc_info=True)


@receiver(post_delete, sender=ControlAssessment)
def control_assessment_post_delete(sender, instance, **kwargs):
    """
    Handle control assessment deletion
    """
    try:
        # Update parent audit metrics
        with transaction.atomic():
            instance.audit.update_metrics()
        
    except Exception as e:
        logger.error(f"Error in control_assessment_post_delete: {str(e)}", exc_info=True)


# ==================== STANDARD SIGNALS ====================

@receiver(post_save, sender=ComplianceStandard)
def standard_post_save(sender, instance, created, **kwargs):
    """
    Handle compliance standard post-save operations
    """
    try:
        # Log activity
        if created:
            activity = 'standard_created'
            description = f'Created compliance standard: {instance.name}'
        else:
            activity = 'standard_updated'
            description = f'Updated compliance standard: {instance.name}'
        
        # Get user from context
        from django.core.handlers.wsgi import WSGIRequest
        import sys
        
        request = None
        for frame in sys._current_frames().values():
            for local_var in frame.f_locals.values():
                if isinstance(local_var, WSGIRequest):
                    request = local_var
                    break
            if request:
                break
        
        if request and hasattr(request, 'user'):
            user = request.user
        else:
            user = instance.created_by
        
        if user:
            ActivityLogger.create_log(
                user=user,
                log_type='compliance',
                activity=activity,
                description=description,
                request=request,
                response=None,
                is_success=True
            )
        
    except Exception as e:
        logger.error(f"Error in standard_post_save: {str(e)}", exc_info=True)


@receiver(post_delete, sender=ComplianceStandard)
def standard_post_delete(sender, instance, **kwargs):
    """
    Handle compliance standard deletion
    """
    try:
        # Log deletion
        from django.core.handlers.wsgi import WSGIRequest
        import sys
        
        request = None
        for frame in sys._current_frames().values():
            for local_var in frame.f_locals.values():
                if isinstance(local_var, WSGIRequest):
                    request = local_var
                    break
            if request:
                break
        
        if request and hasattr(request, 'user'):
            user = request.user
        else:
            user = instance.created_by
        
        if user:
            ActivityLogger.create_log(
                user=user,
                log_type='compliance',
                activity='standard_deleted',
                description=f'Deleted compliance standard: {instance.name}',
                request=request,
                response=None,
                is_success=True
            )
        
    except Exception as e:
        logger.error(f"Error in standard_post_delete: {str(e)}", exc_info=True)


# ==================== REPORT SIGNALS ====================

@receiver(post_save, sender=ComplianceReport)
def report_post_save(sender, instance, created, **kwargs):
    """
    Handle report post-save operations
    """
    try:
        # Ensure report_id is set
        if not instance.report_id:
            import uuid
            instance.report_id = f"REP-{uuid.uuid4().hex[:8].upper()}"
            instance.save(update_fields=['report_id'])
        
        # Log activity
        if created:
            activity = 'report_generated'
            description = f'Generated compliance report: {instance.report_id}'
            
            # Get user from context
            from django.core.handlers.wsgi import WSGIRequest
            import sys
            
            request = None
            for frame in sys._current_frames().values():
                for local_var in frame.f_locals.values():
                    if isinstance(local_var, WSGIRequest):
                        request = local_var
                        break
                if request:
                    break
            
            user = instance.generated_by
            if not user and request and hasattr(request, 'user'):
                user = request.user
            
            if user:
                ActivityLogger.create_log(
                    user=user,
                    log_type='compliance',
                    activity=activity,
                    description=description,
                    request=request,
                    response=None,
                    is_success=True
                )
        
    except Exception as e:
        logger.error(f"Error in report_post_save: {str(e)}", exc_info=True)


# ==================== NOTIFICATION HELPER FUNCTIONS ====================

def _notify_audit_status_change(audit, old_status, new_status):
    """
    Send notifications when audit status changes
    """
    try:
        # Get notification recipients
        recipients = []
        
        if audit.lead_auditor:
            recipients.append(audit.lead_auditor)
        
        if audit.created_by and audit.created_by != audit.lead_auditor:
            recipients.append(audit.created_by)
        
        # Create notification message
        message = f"Audit {audit.audit_id} status changed from {old_status} to {new_status}"
        
        # Send notifications (implement based on your notification system)
        _send_notifications(recipients, 'audit_status_change', message, audit)
        
    except Exception as e:
        logger.error(f"Error in _notify_audit_status_change: {str(e)}", exc_info=True)


def _notify_finding_status_change(finding, old_status, new_status):
    """
    Send notifications when finding status changes
    """
    try:
        # Get notification recipients
        recipients = []
        
        if finding.assigned_to:
            recipients.append(finding.assigned_to)
        
        if finding.audit.lead_auditor and finding.audit.lead_auditor not in recipients:
            recipients.append(finding.audit.lead_auditor)
        
        if finding.created_by and finding.created_by not in recipients:
            recipients.append(finding.created_by)
        
        # Create notification message
        message = f"Finding {finding.id} status changed from {old_status} to {new_status}"
        
        # Send notifications
        _send_notifications(recipients, 'finding_status_change', message, finding)
        
    except Exception as e:
        logger.error(f"Error in _notify_finding_status_change: {str(e)}", exc_info=True)


def _notify_finding_resolved(finding):
    """
    Send notifications when finding is resolved
    """
    try:
        if finding.assigned_to:
            message = f"Finding {finding.id} has been {finding.status}"
            _send_notifications([finding.assigned_to], 'finding_resolved', message, finding)
        
    except Exception as e:
        logger.error(f"Error in _notify_finding_resolved: {str(e)}", exc_info=True)


def _notify_critical_finding(finding):
    """
    Send notifications for new critical findings
    """
    try:
        # Get all compliance officers and admins
        from userApp.models import CustomUser
        recipients = CustomUser.objects.filter(
            Q(role='compliance_officer') | Q(is_admin=True)
        ).exclude(id=finding.created_by.id if finding.created_by else None)
        
        # Also notify audit lead auditor
        if finding.audit.lead_auditor and finding.audit.lead_auditor not in recipients:
            recipients = list(recipients) + [finding.audit.lead_auditor]
        
        message = f"New CRITICAL finding created: {finding.id} - {finding.title}"
        
        _send_notifications(recipients, 'critical_finding', message, finding)
        
    except Exception as e:
        logger.error(f"Error in _notify_critical_finding: {str(e)}", exc_info=True)


def _send_notifications(recipients, notification_type, message, related_object):
    """
    Send notifications to recipients
    This is a placeholder - implement based on your notification system
    """
    try:
        # Placeholder for notification logic
        # You might use Django's messages framework, email, or a real-time system
        
        # Example: Create Notification objects
        from django.contrib.auth.models import User
        from notificationApp.models import Notification  # If you have a notification app
        
        if 'notificationApp' in globals():
            for recipient in recipients:
                if isinstance(recipient, User):
                    Notification.objects.create(
                        user=recipient,
                        notification_type=notification_type,
                        message=message,
                        related_object_type=related_object.__class__.__name__,
                        related_object_id=related_object.id,
                        is_read=False
                    )
        
        # Example: Send email notifications
        # from django.core.mail import send_mail
        # for recipient in recipients:
        #     if recipient.email:
        #         send_mail(
        #             subject=f'Compliance System Notification: {notification_type.replace("_", " ").title()}',
        #             message=message,
        #             from_email='noreply@yourcompany.com',
        #             recipient_list=[recipient.email],
        #             fail_silently=True
        #         )
        
        logger.info(f"Would send {notification_type} notification to {len(recipients)} recipients: {message}")
        
    except Exception as e:
        logger.error(f"Error in _send_notifications: {str(e)}", exc_info=True)


# ==================== BULK OPERATION SIGNALS ====================

@receiver(m2m_changed, sender=ComplianceAudit.departments.through)
def audit_departments_changed(sender, instance, action, **kwargs):
    """
    Handle audit-department relationship changes
    """
    try:
        if action in ['post_add', 'post_remove', 'post_clear']:
            # Log the change
            from django.core.handlers.wsgi import WSGIRequest
            import sys
            
            request = None
            for frame in sys._current_frames().values():
                for local_var in frame.f_locals.values():
                    if isinstance(local_var, WSGIRequest):
                        request = local_var
                        break
                if request:
                    break
            
            if request and hasattr(request, 'user'):
                user = request.user
            else:
                user = instance.created_by or instance.lead_auditor
            
            if user:
                ActivityLogger.create_log(
                    user=user,
                    log_type='compliance',
                    activity='audit_departments_updated',
                    description=f'Updated departments for audit {instance.audit_id}',
                    request=request,
                    response=None,
                    is_success=True
                )
        
    except Exception as e:
        logger.error(f"Error in audit_departments_changed: {str(e)}", exc_info=True)


# ==================== AUTO-COMPLETE SIGNALS ====================



# ==================== INITIALIZATION ====================

def initialize_signals():
    """
    Initialize all signals - called from apps.py ready() method
    """
    # This function ensures signals are connected when Django starts
    # The @receiver decorators handle the connection automatically,
    # but this provides a clear entry point for signal initialization
    
    logger.info("Compliance audit signals initialized")