# trainingApp/email_utils.py

from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.auth import get_user_model
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

User = get_user_model()

class TrainingEmailNotifier:
    """Handles email notifications for training-related events"""
    
    @staticmethod
    def send_training_created_notification(training, created_by):
        """
        Send email notification to all employees when a new training is created.
        
        Args:
            training: Training object that was created
            created_by: User who created the training
        """
        try:
            # Get all users with 'employee' role who are active and approved
            employee_users = User.objects.filter(
                role='employee',
                is_active=True,
                status='approved'
            )
            
            if not employee_users.exists():
                logger.info(f"No active employees found to notify about training: {training.name}")
                return {"success": False, "message": "No active employees to notify"}
            
            # Prepare email content
            subject = f"📚 New Training Available: {training.name}"
            
            # Get training statistics
            total_modules = training.modules.count()
            total_materials = sum(module.materials.count() for module in training.modules.all())
            
            # Create HTML email content
            html_content = TrainingEmailNotifier._create_training_email_html(
                training=training,
                created_by=created_by,
                total_modules=total_modules,
                total_materials=total_materials
            )
            
            # Plain text fallback
            text_content = strip_tags(html_content)
            
            # Send emails in batches to avoid overwhelming the email server
            batch_size = 50
            employee_emails = list(employee_users.values_list('email', flat=True))
            total_employees = len(employee_emails)
            
            successful_sends = 0
            failed_sends = []
            
            for i in range(0, total_employees, batch_size):
                batch = employee_emails[i:i + batch_size]
                try:
                    # Create email message
                    email = EmailMultiAlternatives(
                        subject=subject,
                        body=text_content,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=batch,
                        bcc=batch,  # Use BCC to hide recipients from each other
                    )
                    email.attach_alternative(html_content, "text/html")
                    
                    # Send the email
                    email.send(fail_silently=False)
                    successful_sends += len(batch)
                    
                    logger.info(f"Sent training notification email to {len(batch)} employees")
                    
                except Exception as e:
                    failed_sends.extend(batch)
                    logger.error(f"Failed to send emails to batch of {len(batch)} employees: {str(e)}")
                    continue
            
            # Log the notification
            logger.info(f"""
            Training Notification Summary:
            - Training: {training.name}
            - Created by: {created_by.email}
            - Total employees notified: {successful_sends}/{total_employees}
            - Failed sends: {len(failed_sends)}
            """)
            
            return {
                "success": True,
                "total_notified": successful_sends,
                "total_employees": total_employees,
                "failed_sends": len(failed_sends)
            }
            
        except Exception as e:
            logger.error(f"Error sending training notifications: {str(e)}")
            return {"success": False, "message": str(e)}
    
    @staticmethod
    def _create_training_email_html(training, created_by, total_modules, total_materials):
        """Create HTML email template for training notification"""
        
        # Get training image if available
        image_html = ""
        if training.picture_data:
            import base64
            image_base64 = base64.b64encode(training.picture_data).decode('utf-8')
            image_html = f'''
            <div style="text-align: center; margin-bottom: 20px;">
                <img src="data:image/jpeg;base64,{image_base64}" 
                     alt="{training.name}" 
                     style="max-width: 100%; height: auto; border-radius: 8px; max-height: 200px; object-fit: cover;">
            </div>
            '''
        
        # Get modules preview (first 3 modules)
        modules_preview = training.modules.all()[:3]
        modules_html = ""
        for module in modules_preview:
            materials_count = module.materials.count()
            modules_html += f"""
            <div style="margin-bottom: 15px; padding: 10px; background-color: #f8f9fa; border-left: 4px solid #3b82f6; border-radius: 4px;">
                <strong style="color: #1f2937;">📘 {module.name}</strong>
                <p style="margin: 5px 0 0 0; color: #6b7280; font-size: 14px;">
                    {module.description[:100] if module.description else 'No description available'}
                    {f'...' if module.description and len(module.description) > 100 else ''}
                </p>
                <small style="color: #9ca3af;">📄 {materials_count} material(s)</small>
            </div>
            """
        
        if training.modules.count() > 3:
            modules_html += f"""
            <div style="text-align: center; margin-top: 10px;">
                <small style="color: #6b7280;">+ {training.modules.count() - 3} more modules</small>
            </div>
            """
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>New Training Available</title>
        </head>
        <body style="font-family: 'Segoe UI', Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f7fb;">
            <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: white; padding: 30px 20px; text-align: center;">
                    <h1 style="margin: 0; font-size: 28px; font-weight: 700;">🎓 New Training Available</h1>
                    <p style="margin: 10px 0 0; opacity: 0.9;">Hammer Tech Group - Employee Development Program</p>
                </div>
                
                <!-- Body -->
                <div style="padding: 30px 25px;">
                    <!-- Greeting -->
                    <div style="margin-bottom: 25px;">
                        <h2 style="color: #1e3a8a; margin: 0 0 10px;">Dear Employee,</h2>
                        <p style="margin: 0;">We are excited to announce a new training opportunity to enhance your skills and knowledge!</p>
                    </div>
                    
                    <!-- Training Details -->
                    <div style="background-color: #f0f9ff; border-radius: 10px; padding: 20px; margin-bottom: 25px;">
                        <h3 style="color: #1e3a8a; margin: 0 0 15px;">📋 Training Information</h3>
                        
                        {image_html}
                        
                        <div style="margin-bottom: 15px;">
                            <strong style="color: #1f2937;">Training Name:</strong>
                            <p style="margin: 5px 0 0 15px; font-size: 18px; font-weight: 600; color: #3b82f6;">
                                {training.name}
                            </p>
                        </div>
                        
                        <div style="margin-bottom: 15px;">
                            <strong style="color: #1f2937;">📝 Description:</strong>
                            <p style="margin: 5px 0 0 15px; color: #4b5563;">
                                {training.description if training.description else 'No description provided.'}
                            </p>
                        </div>
                        
                        <div style="display: flex; gap: 20px; margin-top: 15px; flex-wrap: wrap;">
                            <div style="flex: 1; min-width: 120px;">
                                <strong style="color: #1f2937;">📊 Modules:</strong>
                                <p style="margin: 5px 0; font-size: 24px; font-weight: 700; color: #3b82f6;">{total_modules}</p>
                            </div>
                            <div style="flex: 1; min-width: 120px;">
                                <strong style="color: #1f2937;">📚 Materials:</strong>
                                <p style="margin: 5px 0; font-size: 24px; font-weight: 700; color: #10b981;">{total_materials}</p>
                            </div>
                            <div style="flex: 1; min-width: 120px;">
                                <strong style="color: #1f2937;">👨‍🏫 Created By:</strong>
                                <p style="margin: 5px 0; color: #6b7280;">
                                    {created_by.full_name}
                                </p>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Modules Preview -->
                    {f'''
                    <div style="margin-bottom: 25px;">
                        <h3 style="color: #1e3a8a; margin: 0 0 15px;">📖 Modules Overview</h3>
                        {modules_html}
                    </div>
                    ''' if modules_html else ''}
                    
                    <!-- Action Button -->
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{settings.FRONTEND_URL}/training/{training.id}" 
                           style="display: inline-block; background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%); 
                                  color: white; padding: 12px 30px; text-decoration: none; 
                                  border-radius: 8px; font-weight: 600; font-size: 16px;
                                  box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            🔗 Access Training
                        </a>
                    </div>
                    
                    <!-- Additional Info -->
                    <div style="background-color: #fef3c7; border-left: 4px solid #f59e0b; padding: 15px; margin-top: 20px; border-radius: 6px;">
                        <p style="margin: 0; font-size: 14px; color: #92400e;">
                            <strong>💡 Tip:</strong> Complete this training at your own pace. Track your progress and earn certificates upon completion.
                        </p>
                    </div>
                </div>
                
                <!-- Footer -->
                <div style="background-color: #f8fafc; padding: 20px; text-align: center; border-top: 1px solid #e2e8f0;">
                    <p style="margin: 0 0 10px; font-size: 12px; color: #64748b;">
                        This is an automated notification from the Hammer Tech AI-Enhanced Access Control & Compliance System.
                    </p>
                    <p style="margin: 0; font-size: 12px; color: #64748b;">
                        © {datetime.now().year} Hammer Tech Group Rwanda. All rights reserved.
                    </p>
                    <p style="margin: 10px 0 0; font-size: 11px; color: #94a3b8;">
                        If you have any questions, please contact your HR department.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_content
    
    @staticmethod
    def send_module_added_notification(training, module, added_by):
        """
        Send notification when a new module is added to an existing training
        """
        try:
            # Get employees who are enrolled in this training
            from trainingCandidateApp.models import Candidate
            enrolled_employees = Candidate.objects.filter(
                training=training,
                status__in=['in_progress', 'pending']
            ).select_related('learner')
            
            if not enrolled_employees.exists():
                return {"success": False, "message": "No enrolled employees to notify"}
            
            employee_emails = [candidate.learner.email for candidate in enrolled_employees]
            
            subject = f"📖 New Module Added: {module.name} - {training.name}"
            
            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>New Module Added</title>
            </head>
            <body style="font-family: Arial, sans-serif;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #3b82f6;">New Module Available</h2>
                    <p>Hello,</p>
                    <p>A new module has been added to the training <strong>{training.name}</strong>:</p>
                    
                    <div style="background-color: #f0f9ff; padding: 15px; border-radius: 8px; margin: 15px 0;">
                        <h3 style="margin: 0 0 10px;">📘 {module.name}</h3>
                        <p style="margin: 0;">{module.description if module.description else 'No description available'}</p>
                    </div>
                    
                    <p>Log in to your account to access this new content.</p>
                    
                    <a href="{settings.FRONTEND_URL}/training/{training.id}" 
                       style="display: inline-block; background-color: #3b82f6; color: white; 
                              padding: 10px 20px; text-decoration: none; border-radius: 5px;">
                        Access Training
                    </a>
                </div>
            </body>
            </html>
            """
            
            text_content = strip_tags(html_content)
            
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                bcc=employee_emails,
            )
            email.attach_alternative(html_content, "text/html")
            email.send(fail_silently=False)
            
            logger.info(f"Module notification sent to {len(employee_emails)} employees")
            
            return {"success": True, "notified_count": len(employee_emails)}
            
        except Exception as e:
            logger.error(f"Error sending module notification: {str(e)}")
            return {"success": False, "message": str(e)}



            