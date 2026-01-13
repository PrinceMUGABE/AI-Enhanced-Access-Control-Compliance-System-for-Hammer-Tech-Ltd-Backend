from django.core.management.base import BaseCommand
from assistanceApp.models import AssistanceKnowledgeBase
from userApp.models import CustomUser


class Command(BaseCommand):
    help = 'Seed the knowledge base with initial Q&A entries'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Starting knowledge base seeding...'))
        
        # Get an admin user to set as creator
        admin_user = CustomUser.objects.filter(role='admin').first()
        if not admin_user:
            self.stdout.write(self.style.WARNING('No admin user found. Creating entries without creator.'))
        
        # Knowledge base entries
        kb_entries = [
            # General Information
            {
                'category': 'general',
                'question': 'What is the BTSL Mentorship Platform?',
                'answer': 'The BTSL Mentorship Platform is a comprehensive system designed to connect mentors with mentees, facilitating professional growth and knowledge sharing. It provides tools for communication, goal setting, progress tracking, and resource sharing.',
                'keywords': ['platform', 'about', 'btsl', 'mentorship', 'what is'],
                'priority': 10
            },
            {
                'category': 'general',
                'question': 'How do I get started?',
                'answer': 'To get started:\n1. Create an account by registering with your phone number\n2. Complete your profile with relevant information\n3. Wait for admin approval\n4. Once approved, you can access the platform and connect with mentors or mentees',
                'keywords': ['start', 'begin', 'getting started', 'how to', 'first time'],
                'priority': 9
            },
            
            # Mentorship Program
            {
                'category': 'mentorship',
                'question': 'How do I become a mentor?',
                'answer': 'To become a mentor:\n1. Register with your details and select "Mentor" as your role\n2. Complete your profile highlighting your expertise and experience\n3. Select the departments you can mentor in\n4. Wait for admin approval\n5. Once approved, you\'ll be matched with mentees based on your expertise',
                'keywords': ['mentor', 'become mentor', 'mentoring', 'teach'],
                'priority': 9
            },
            {
                'category': 'mentorship',
                'question': 'How do I find a mentor?',
                'answer': 'To find a mentor:\n1. Register as a mentee and get approved by admin\n2. Browse available mentors in your department\n3. Send a mentorship request\n4. Wait for the mentor to accept\n5. Once accepted, you can start communicating through the chat system',
                'keywords': ['find mentor', 'get mentor', 'mentee', 'learning'],
                'priority': 9
            },
            {
                'category': 'mentorship',
                'question': 'What happens in a mentorship?',
                'answer': 'In a mentorship relationship:\n- Set goals together with your mentor/mentee\n- Schedule regular meetings and check-ins\n- Share resources and learning materials\n- Track progress through the platform\n- Communicate via chat and video calls\n- Provide and receive feedback',
                'keywords': ['mentorship', 'what happens', 'process', 'activities'],
                'priority': 7
            },
            
            # Account Management
            {
                'category': 'account',
                'question': 'How do I reset my password?',
                'answer': 'To reset your password:\n1. Click on "Forgot Password" on the login page\n2. Enter your registered phone number\n3. You\'ll receive a verification code\n4. Enter the code and create a new password\n\nIf you face issues, contact support.',
                'keywords': ['password', 'reset', 'forgot', 'change password'],
                'priority': 8
            },
            {
                'category': 'account',
                'question': 'How do I update my profile?',
                'answer': 'To update your profile:\n1. Log in to your account\n2. Click on your profile icon\n3. Select "Edit Profile"\n4. Update your information\n5. Click "Save Changes"\n\nYou can update your name, email, department, and other details.',
                'keywords': ['profile', 'update', 'edit', 'change'],
                'priority': 7
            },
            {
                'category': 'account',
                'question': 'Why is my account pending approval?',
                'answer': 'New accounts require admin approval for security and quality control. This typically takes 24-48 hours. You\'ll receive an email once your account is approved. If it\'s been longer, please contact support.',
                'keywords': ['pending', 'approval', 'waiting', 'account status'],
                'priority': 8
            },
            
            # Technical Support
            {
                'category': 'technical',
                'question': 'The chat is not working. What should I do?',
                'answer': 'If the chat is not working:\n1. Check your internet connection\n2. Refresh the page (Ctrl+F5)\n3. Clear your browser cache\n4. Try a different browser\n5. Ensure WebSocket connections are not blocked by your firewall\n\nIf the issue persists, contact technical support.',
                'keywords': ['chat', 'not working', 'broken', 'issue', 'problem'],
                'priority': 8
            },
            {
                'category': 'technical',
                'question': 'Video calls are not connecting. How do I fix this?',
                'answer': 'If video calls are not connecting:\n1. Check your camera and microphone permissions in browser settings\n2. Ensure your internet connection is stable (minimum 1 Mbps)\n3. Try using Chrome or Firefox browser\n4. Disable VPN if active\n5. Check firewall settings\n\nContact support if problems continue.',
                'keywords': ['video', 'call', 'not connecting', 'camera', 'microphone'],
                'priority': 8
            },
            {
                'category': 'technical',
                'question': 'Which browsers are supported?',
                'answer': 'The platform works best on:\n- Google Chrome (latest version)\n- Mozilla Firefox (latest version)\n- Microsoft Edge (latest version)\n- Safari (latest version)\n\nWe recommend using the latest version of Chrome for the best experience.',
                'keywords': ['browser', 'supported', 'compatible', 'chrome', 'firefox'],
                'priority': 6
            },
            
            # Department Information
            {
                'category': 'department',
                'question': 'What departments are available?',
                'answer': 'Available departments vary based on your organization structure. Common departments include:\n- Engineering\n- Product Management\n- Design\n- Data Science\n- Marketing\n- Sales\n\nContact your admin to see the full list of active departments.',
                'keywords': ['department', 'available', 'list', 'which'],
                'priority': 6
            },
            {
                'category': 'department',
                'question': 'Can I change my department?',
                'answer': 'Yes, you can request a department change:\n1. Contact your admin or HR\n2. Explain the reason for the change\n3. Admin will review and approve if appropriate\n\nNote that changing departments may affect your current mentorship assignments.',
                'keywords': ['change department', 'switch', 'transfer'],
                'priority': 7
            },
            
            # Policies
            {
                'category': 'policy',
                'question': 'What are the mentorship guidelines?',
                'answer': 'Key mentorship guidelines:\n- Maintain professional conduct at all times\n- Respect confidentiality and privacy\n- Be responsive and committed to scheduled meetings\n- Provide constructive feedback\n- Report any concerns to admin\n- Follow the code of conduct\n\nFor detailed policies, refer to the platform documentation.',
                'keywords': ['guidelines', 'rules', 'policy', 'conduct'],
                'priority': 7
            },
            {
                'category': 'policy',
                'question': 'How is my data protected?',
                'answer': 'We take data protection seriously:\n- All data is encrypted in transit and at rest\n- Access is role-based and restricted\n- Regular security audits are performed\n- We comply with data protection regulations\n- Personal information is never shared without consent\n\nFor more details, see our Privacy Policy.',
                'keywords': ['data', 'privacy', 'security', 'protected', 'safe'],
                'priority': 7
            },
            
            # Contact & Support
            {
                'category': 'general',
                'question': 'How do I contact support?',
                'answer': 'You can contact support through:\n- This AI assistance chat (available 24/7)\n- Email: support@btsl-mentorship.com\n- In-platform messaging to admins\n- Phone: Available during business hours\n\nFor urgent issues, please contact admin directly through the platform.',
                'keywords': ['contact', 'support', 'help', 'reach', 'assistance'],
                'priority': 8
            },
        ]
        
        created_count = 0
        updated_count = 0
        
        for entry_data in kb_entries:
            # Check if entry exists (by question)
            existing = AssistanceKnowledgeBase.objects.filter(
                question=entry_data['question']
            ).first()
            
            if existing:
                # Update existing entry
                for key, value in entry_data.items():
                    setattr(existing, key, value)
                existing.save()
                updated_count += 1
                self.stdout.write(self.style.WARNING(f'Updated: {entry_data["question"][:50]}...'))
            else:
                # Create new entry
                AssistanceKnowledgeBase.objects.create(
                    created_by=admin_user,
                    **entry_data
                )
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created: {entry_data["question"][:50]}...'))
        
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Knowledge base seeding complete!'
            f'\n   - Created: {created_count} entries'
            f'\n   - Updated: {updated_count} entries'
            f'\n   - Total: {created_count + updated_count} entries'
        ))