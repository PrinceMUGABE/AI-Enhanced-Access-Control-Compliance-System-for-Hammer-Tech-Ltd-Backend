#assistanceApp/email_service.py
from django.db import models

"""
Email Service for sending assistance responses
"""

from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.utils.timezone import now
import logging

from .models import AssistanceEmailQueue, AssistanceSession

logger = logging.getLogger(__name__)


class AssistanceEmailService:
    """Service for sending assistance emails"""
    
    def __init__(self):
        self.from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@mentorship.com')
    
    def queue_assistance_response(self, session: AssistanceSession, response_message: str):
        """
        Queue an email response for a session
        
        Args:
            session: AssistanceSession instance
            response_message: The response message to send
        """
        recipient_email = session.get_email()
        recipient_name = session.get_display_name()
        
        if not recipient_email:
            logger.error(f"No email found for session {session.session_id}")
            return None
        
        # Generate email content
        subject = f"Response to your question - BTSL Mentorship"
        
        # Create HTML email
        html_content = self._generate_html_email(
            session=session,
            response_message=response_message,
            recipient_name=recipient_name
        )
        
        # Create plain text version
        text_content = self._generate_text_email(
            session=session,
            response_message=response_message,
            recipient_name=recipient_name
        )
        
        # Create email queue entry
        email_queue = AssistanceEmailQueue.objects.create(
            session=session,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            subject=subject,
            message_html=html_content,
            message_text=text_content,
            status='pending'
        )
        
        # Try to send immediately
        self.send_queued_email(email_queue)
        
        return email_queue
    
    def send_queued_email(self, email_queue: AssistanceEmailQueue):
        """Send a queued email"""
        try:
            email_queue.status = 'sending'
            email_queue.attempts += 1
            email_queue.save()
            
            # Create email message
            email = EmailMultiAlternatives(
                subject=email_queue.subject,
                body=email_queue.message_text,
                from_email=self.from_email,
                to=[email_queue.recipient_email]
            )
            
            # Attach HTML version
            email.attach_alternative(email_queue.message_html, "text/html")
            
            # Send email
            email.send(fail_silently=False)
            
            # Update status
            email_queue.status = 'sent'
            email_queue.sent_at = now()
            email_queue.save()
            
            # Update session
            session = email_queue.session
            session.email_sent = True
            session.email_sent_at = now()
            session.email_response = email_queue.message_text
            session.save()
            
            logger.info(f"Email sent successfully to {email_queue.recipient_email} for session {email_queue.session.session_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            
            email_queue.status = 'failed'
            email_queue.error_message = str(e)
            email_queue.save()
            
            # Retry if attempts < max_attempts
            if email_queue.attempts < email_queue.max_attempts:
                email_queue.status = 'pending'
                email_queue.save()
            
            return False
    
    def _generate_html_email(self, session: AssistanceSession, response_message: str, recipient_name: str) -> str:
        """Generate HTML email content"""
        html_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
            border-radius: 10px 10px 0 0;
        }}
        .header h1 {{
            margin: 0;
            font-size: 24px;
        }}
        .content {{
            background: #f9f9f9;
            padding: 30px;
            border-radius: 0 0 10px 10px;
        }}
        .question-box {{
            background: white;
            padding: 20px;
            border-left: 4px solid #667eea;
            margin: 20px 0;
            border-radius: 5px;
        }}
        .question-label {{
            font-weight: bold;
            color: #667eea;
            margin-bottom: 10px;
        }}
        .response-box {{
            background: white;
            padding: 20px;
            border-left: 4px solid #48bb78;
            margin: 20px 0;
            border-radius: 5px;
        }}
        .response-label {{
            font-weight: bold;
            color: #48bb78;
            margin-bottom: 10px;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            font-size: 12px;
        }}
        .button {{
            display: inline-block;
            padding: 12px 30px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            margin: 20px 0;
        }}
        .session-info {{
            font-size: 12px;
            color: #666;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🎓 BTSL Mentorship Platform</h1>
        <p>Response to Your Question</p>
    </div>
    
    <div class="content">
        <p>Hello <strong>{recipient_name}</strong>,</p>
        
        <p>Thank you for reaching out to our assistance service. Here's the response to your question:</p>
        
        <div class="question-box">
            <div class="question-label">📝 Your Question:</div>
            <p>{question}</p>
        </div>
        
        <div class="response-box">
            <div class="response-label">💡 Our Response:</div>
            <div>{response}</div>
        </div>
        
        <p>We hope this helps! If you have any additional questions or need further clarification, please don't hesitate to ask.</p>
        
        <div style="text-align: center;">
            <a href="{platform_url}" class="button">Visit Our Platform</a>
        </div>
        
        <div class="session-info">
            <strong>Session Information:</strong><br>
            Session ID: {session_id}<br>
            Date: {date}
        </div>
    </div>
    
    <div class="footer">
        <p>© 2025 BTSL Mentorship Platform. All rights reserved.</p>
        <p>This is an automated response from our assistance system.</p>
    </div>
</body>
</html>
"""
        
        # Format the response message (convert newlines to <br>)
        formatted_response = response_message.replace('\n', '<br>')
        
        platform_url = getattr(settings, 'PLATFORM_URL', 'https://mentorship.btsl.com')
        
        return html_template.format(
            recipient_name=recipient_name,
            question=session.initial_question,
            response=formatted_response,
            platform_url=platform_url,
            session_id=session.session_id,
            date=session.created_at.strftime('%B %d, %Y at %I:%M %p')
        )
    
    def _generate_text_email(self, session: AssistanceSession, response_message: str, recipient_name: str) -> str:
        """Generate plain text email content"""
        text_template = """
BTSL Mentorship Platform
Response to Your Question
========================

Hello {recipient_name},

Thank you for reaching out to our assistance service. Here's the response to your question:

YOUR QUESTION:
--------------
{question}

OUR RESPONSE:
-------------
{response}

We hope this helps! If you have any additional questions or need further clarification, please don't hesitate to ask.

Session Information:
Session ID: {session_id}
Date: {date}

---
© 2025 BTSL Mentorship Platform. All rights reserved.
This is an automated response from our assistance system.
"""
        
        return text_template.format(
            recipient_name=recipient_name,
            question=session.initial_question,
            response=response_message,
            session_id=session.session_id,
            date=session.created_at.strftime('%B %d, %Y at %I:%M %p')
        )
    
    def retry_failed_emails(self):
        """Retry sending failed emails"""
        failed_emails = AssistanceEmailQueue.objects.filter(
            status='failed',
            attempts__lt=models.F('max_attempts')
        )
        
        success_count = 0
        for email_queue in failed_emails:
            if self.send_queued_email(email_queue):
                success_count += 1
        
        logger.info(f"Retried {failed_emails.count()} failed emails, {success_count} successful")
        
        return success_count
    
    def send_admin_joined_notification(self, session: AssistanceSession):
        """Send notification that admin joined the session"""
        recipient_email = session.get_email()
        if not recipient_email:
            return
        
        subject = "An admin has joined your assistance session"
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
        .notification {{ background: #e6f7ff; padding: 20px; border-left: 4px solid #1890ff; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="notification">
        <h2>👋 An Admin Has Joined Your Session</h2>
        <p>Good news! An admin from our team has joined your assistance session and will be helping you directly.</p>
        <p><strong>Session ID:</strong> {session.session_id}</p>
        <p><strong>Admin:</strong> {session.admin_handler.full_name if session.admin_handler else 'Support Team'}</p>
    </div>
</body>
</html>
"""
        
        text_content = f"""
An Admin Has Joined Your Session

Good news! An admin from our team has joined your assistance session and will be helping you directly.

Session ID: {session.session_id}
Admin: {session.admin_handler.full_name if session.admin_handler else 'Support Team'}
"""
        
        try:
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=self.from_email,
                to=[recipient_email]
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=True)
            
            logger.info(f"Admin joined notification sent to {recipient_email}")
        except Exception as e:
            logger.error(f"Failed to send admin joined notification: {str(e)}")


# Singleton instance
email_service = AssistanceEmailService()