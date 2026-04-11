from django.core.management.base import BaseCommand
from complianceAuditApp.models import ControlAssessment

class Command(BaseCommand):
    help = 'Fix control IDs for existing assessments'

    def handle(self, *args, **options):
        assessments = ControlAssessment.objects.filter(
            control_id='TEMP-0000-0000'
        )
        
        for assessment in assessments:
            standard = assessment.audit.standard
            
            # Generate new control ID
            old_id = assessment.control_id
            assessment.control_id = ''  # Clear it so save() will regenerate
            assessment.save()
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Updated {old_id} to {assessment.control_id}'
                )
            )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully updated {assessments.count()} control assessments'
            )
        )