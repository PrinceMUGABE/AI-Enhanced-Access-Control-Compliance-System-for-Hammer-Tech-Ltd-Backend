# create_sample_data.py
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from assistanceApp.models import FAQ

# Create sample FAQs
sample_faqs = [
    {
        'question': 'How do I reset my password?',
        'answer': 'Click "Forgot Password" on the login page. Enter your registered email to receive a password reset link. Follow the instructions in the email to create a new password.',
        'category': 'account',
        'keywords': 'password, reset, forgot, login, security, change password'
    },
    {
        'question': 'How can I become a mentor?',
        'answer': '1. Complete your profile with detailed information about your expertise\n2. Submit your application through the Mentorship section\n3. Our team will review your qualifications\n4. Once approved, mentees can request mentorship\n5. You can accept or decline mentorship requests',
        'category': 'mentorship',
        'keywords': 'mentor, become, apply, expert, guide, teaching, helping'
    },
    {
        'question': 'How are mentors and mentees matched?',
        'answer': 'Our matching algorithm considers:\n- Skills and expertise\n- Goals and objectives\n- Availability and time zones\n- Communication preferences\n- Previous mentorship experience\nYou can also search and request specific mentors.',
        'category': 'mentorship',
        'keywords': 'match, algorithm, compatible, skills, goals, pairing'
    },
    {
        'question': 'What features does the platform offer?',
        'answer': 'Our platform includes:\n- Smart mentorship matching\n- Progress tracking and goal setting\n- Video calls and messaging\n- Resource sharing\n- Milestone celebrations\n- Feedback and review system',
        'category': 'general',
        'keywords': 'features, functionality, platform, tools, capabilities'
    },
    {
        'question': 'How do I contact support?',
        'answer': 'You can contact us through:\n- Email: support@digital-mentorship.com\n- Contact form on our website\n- In-app support chat\n- Phone: +1 (555) 123-4567\nResponse time: 24-48 hours',
        'category': 'general',
        'keywords': 'contact, support, help, email, phone, assistance'
    },
    {
        'question': 'Is there a mobile app available?',
        'answer': 'Yes! You can download our mobile app from:\n- App Store (iOS)\n- Google Play Store (Android)\nAll platform features are available in the mobile app.',
        'category': 'technical',
        'keywords': 'mobile, app, ios, android, download, install'
    },
    {
        'question': 'How do I update my profile information?',
        'answer': 'To update your profile:\n1. Log in to your account\n2. Click on your profile picture/name\n3. Select "Edit Profile"\n4. Update your information\n5. Click "Save Changes"\nProfile updates are reviewed within 24 hours.',
        'category': 'account',
        'keywords': 'profile, update, edit, information, details, modify'
    },
    {
        'question': 'What are the system requirements?',
        'answer': 'Minimum requirements:\n- Web: Latest Chrome/Firefox/Safari/Edge\n- Mobile: iOS 12+ or Android 8+\n- Internet: 5 Mbps minimum\n- Storage: 100MB free space\n- RAM: 2GB minimum',
        'category': 'technical',
        'keywords': 'requirements, system, browser, mobile, internet, specs'
    },
]

# Add FAQs to database
for faq_data in sample_faqs:
    FAQ.objects.get_or_create(
        question=faq_data['question'],
        defaults=faq_data
    )

print(f"✅ Created {len(sample_faqs)} sample FAQs!")