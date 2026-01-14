# notificationApp/email_utils.py - FIXED VERSION

from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import logging

logger = logging.getLogger(__name__)


def send_notification_email(recipient, title, message, notification_type='announcement', sender=None):
    """
    Send email notification to a user
    
    Args:
        recipient: CustomUser object
        title: Email subject/notification title
        message: Email body/notification message
        notification_type: Type of notification
        sender: CustomUser who sent the notification (optional)
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Check if recipient has email
        if not recipient.email:
            logger.warning(f"No email address for recipient: {recipient.work_mail_address}")
            return False
        
        # Check user preferences (if exists)
        try:
            if hasattr(recipient, 'notification_preferences'):
                if not recipient.notification_preferences.enable_email_notifications:
                    logger.info(f"Email notifications disabled for {recipient.email}")
                    return False
        except Exception as pref_error:
            logger.warning(f"Could not check preferences for {recipient.email}: {str(pref_error)}")
            # Continue anyway if preferences don't exist
        
        # Build email subject
        subject = f"[Digital Mentorship] {title}"
        
        # Build email body
        sender_name = sender.full_name if sender else "System"
        sender_email = sender.work_mail_address if sender else "system@btsl_mentorship.com"
        
        # Create HTML email
        html_message = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    background-color: white;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .header {{
                    background-color: #2563eb;
                    color: white;
                    padding: 30px 20px;
                    text-align: center;
                }}
                .header h1 {{
                    margin: 0;
                    font-size: 24px;
                }}
                .content {{
                    padding: 30px;
                }}
                .notification-badge {{
                    display: inline-block;
                    padding: 6px 12px;
                    background-color: #dbeafe;
                    color: #1e40af;
                    border-radius: 20px;
                    font-size: 12px;
                    font-weight: bold;
                    margin-bottom: 20px;
                    text-transform: uppercase;
                }}
                .title {{
                    font-size: 20px;
                    color: #1f2937;
                    margin: 20px 0;
                    font-weight: bold;
                }}
                .message-box {{
                    background-color: #f9fafb;
                    padding: 20px;
                    border-radius: 8px;
                    border-left: 4px solid #2563eb;
                    margin: 20px 0;
                }}
                .sender-info {{
                    color: #6b7280;
                    font-size: 14px;
                    margin: 10px 0;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background-color: #2563eb;
                    color: white;
                    text-decoration: none;
                    border-radius: 6px;
                    margin-top: 20px;
                    font-weight: bold;
                }}
                .button:hover {{
                    background-color: #1d4ed8;
                }}
                .footer {{
                    text-align: center;
                    color: #6b7280;
                    font-size: 12px;
                    margin-top: 30px;
                    padding: 20px;
                    border-top: 1px solid #e5e7eb;
                }}
                .recipient-info {{
                    background-color: #f0f9ff;
                    padding: 15px;
                    border-radius: 6px;
                    margin: 15px 0;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎓 Digital Mentorship Platform</h1>
                </div>
                <div class="content">
                    <span class="notification-badge">{notification_type}</span>
                    
                    <div class="title">{title}</div>
                    
                    <div class="recipient-info">
                        <strong>To:</strong> {recipient.full_name} ({recipient.work_mail_address})
                    </div>
                    
                    <div class="sender-info">
                        <strong>From:</strong> {sender_name} ({sender_email})
                    </div>
                    
                    <div class="message-box">
                        {message}
                    </div>
                    
                    <p style="text-align: center;">
                        <a href="{settings.FRONTEND_URL}/notifications" class="button">
                            View in Platform →
                        </a>
                    </p>
                </div>
                <div class="footer">
                    <p><strong>Digital Mentorship Platform</strong></p>
                    <p>This is an automated notification. Please do not reply to this email.</p>
                    <p>If you have questions, contact your mentor or HR department.</p>
                    <p style="margin-top: 15px; font-size: 11px; color: #9ca3af;">
                        You received this email because you are registered on the Digital Mentorship Platform.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        plain_message = f"""
        Digital Mentorship Platform
        =====================================
        
        NOTIFICATION: {notification_type.upper()}
        
        {title}
        
        To: {recipient.full_name} ({recipient.work_mail_address})
        From: {sender_name} ({sender_email})
        
        Message:
        {message}
        
        =====================================
        View this notification at: {settings.FRONTEND_URL}/notifications
        
        This is an automated message from Digital Mentorship Platform.
        Please do not reply to this email.
        """
        
        # Create email message
        email = EmailMultiAlternatives(
            subject=subject,
            body=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient.email],
        )
        email.attach_alternative(html_message, "text/html")
        
        # Send email
        email.send(fail_silently=False)
        
        logger.info(f"✅ Email notification sent successfully to {recipient.email}")
        print(f"\n{'='*80}")
        print(f"✅ EMAIL SENT SUCCESSFULLY")
        print(f"{'='*80}")
        print(f"To: {recipient.email}")
        print(f"Subject: {subject}")
        print(f"Notification Type: {notification_type}")
        print(f"{'='*80}\n")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to send email to {recipient.email}: {str(e)}")
        print(f"\n{'='*80}")
        print(f"❌ EMAIL SEND FAILED")
        print(f"{'='*80}")
        print(f"To: {recipient.email}")
        print(f"Error: {str(e)}")
        print(f"{'='*80}\n")
        return False


def send_bulk_notification_emails(recipients, title, message, notification_type='announcement', sender=None):
    """
    Send email notifications to multiple users
    
    Args:
        recipients: QuerySet or list of CustomUser objects
        title: Email subject
        message: Email body
        notification_type: Type of notification
        sender: User who sent the notification
    
    Returns:
        dict: Statistics about email sending
    """
    stats = {
        'total': 0,
        'success': 0,
        'failed': 0,
        'failed_emails': [],
        'skipped': 0,
        'skipped_emails': []
    }
    
    logger.info(f"Starting bulk email send to {len(recipients)} recipients")
    print(f"\n{'='*80}")
    print(f"📧 BULK EMAIL SEND STARTED")
    print(f"{'='*80}")
    print(f"Recipients: {len(recipients)}")
    print(f"Title: {title}")
    print(f"{'='*80}\n")
    
    for recipient in recipients:
        stats['total'] += 1
        
        # Check if user has email notifications enabled
        try:
            if hasattr(recipient, 'notification_preferences'):
                if not recipient.notification_preferences.enable_email_notifications:
                    logger.info(f"Email notifications disabled for {recipient.email}")
                    stats['skipped'] += 1
                    stats['skipped_emails'].append(recipient.email)
                    continue
        except Exception:
            pass  # If preferences don't exist, send anyway
        
        # Send email
        if send_notification_email(recipient, title, message, notification_type, sender):
            stats['success'] += 1
        else:
            stats['failed'] += 1
            stats['failed_emails'].append(recipient.email)
    
    logger.info(f"Bulk email send completed. Success: {stats['success']}, Failed: {stats['failed']}, Skipped: {stats['skipped']}")
    print(f"\n{'='*80}")
    print(f"📧 BULK EMAIL SEND COMPLETED")
    print(f"{'='*80}")
    print(f"Total: {stats['total']}")
    print(f"Success: {stats['success']}")
    print(f"Failed: {stats['failed']}")
    print(f"Skipped: {stats['skipped']}")
    print(f"{'='*80}\n")
    
    return stats