# userApp/management/commands/cleanup_old_logs.py

from django.core.management.base import BaseCommand
from django.utils.timezone import now, timedelta
from userApp.models import UserLog

class Command(BaseCommand):
    help = 'Clean up old user activity logs'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=90,
            help='Delete logs older than this many days (default: 90)'
        )
    
    def handle(self, *args, **options):
        days = options['days']
        cutoff_date = now() - timedelta(days=days)
        
        logs_to_delete = UserLog.objects.filter(timestamp__lt=cutoff_date)
        count = logs_to_delete.count()
        
        logs_to_delete.delete()
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully deleted {count} logs older than {days} days')
        )