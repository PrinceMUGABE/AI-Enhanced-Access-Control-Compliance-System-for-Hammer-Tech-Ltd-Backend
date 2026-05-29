# complianceAuditApp/management/commands/setup_media_dirs.py
# Create this file in: complianceAuditApp/management/commands/

from django.core.management.base import BaseCommand
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Create all required media directories'

    def handle(self, *args, **options):
        """Create all necessary media directories"""
        
        directories = [
            settings.MEDIA_ROOT,
            os.path.join(settings.MEDIA_ROOT, 'compliance_reports'),
            os.path.join(settings.MEDIA_ROOT, 'profile_pictures'),
            os.path.join(settings.MEDIA_ROOT, 'documents'),
            os.path.join(settings.MEDIA_ROOT, 'incident_attachments'),
            os.path.join(settings.MEDIA_ROOT, 'risk_assessment_docs'),
        ]
        
        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.SUCCESS('CREATING MEDIA DIRECTORIES'))
        self.stdout.write("="*80 + "\n")
        
        for directory in directories:
            try:
                os.makedirs(directory, exist_ok=True)
                
                # Verify directory exists and is writable
                if os.path.exists(directory):
                    # Test write permissions
                    test_file = os.path.join(directory, '.test_write')
                    try:
                        with open(test_file, 'w') as f:
                            f.write('test')
                        os.remove(test_file)
                        writable = True
                    except:
                        writable = False
                    
                    status = "✓ CREATED & WRITABLE" if writable else "✓ CREATED (NOT WRITABLE)"
                    color = self.style.SUCCESS if writable else self.style.WARNING
                else:
                    status = "✗ FAILED TO CREATE"
                    color = self.style.ERROR
                
                self.stdout.write(f"{color(status)}: {directory}")
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"✗ ERROR creating {directory}: {str(e)}")
                )
        
        self.stdout.write("\n" + "="*80)
        self.stdout.write(self.style.SUCCESS('MEDIA DIRECTORY SETUP COMPLETE'))
        self.stdout.write("="*80 + "\n")