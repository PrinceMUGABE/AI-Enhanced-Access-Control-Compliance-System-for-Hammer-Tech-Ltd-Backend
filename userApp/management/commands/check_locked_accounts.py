# userApp/management/commands/check_locked_accounts.py

from django.core.management.base import BaseCommand
from django.utils.timezone import now
from userApp.models import CustomUser

class Command(BaseCommand):
    help = 'Check and display locked accounts'
    
    def handle(self, *args, **options):
        locked_users = CustomUser.objects.filter(
            locked_until__gt=now()
        )
        
        if locked_users.exists():
            self.stdout.write(f"\n🔒 Locked Accounts ({locked_users.count()}):")
            self.stdout.write("="*60)
            
            for user in locked_users:
                remaining = user.get_lock_remaining_seconds()
                minutes = remaining // 60
                seconds = remaining % 60
                
                self.stdout.write(f"\n📧 Email: {user.email}")
                self.stdout.write(f"👤 Name: {user.full_name}")
                self.stdout.write(f"🔢 Failed Attempts: {user.failed_login_attempts}")
                self.stdout.write(f"⏰ Last Failed: {user.last_failed_login}")
                self.stdout.write(f"⏳ Unlock in: {minutes}m {seconds}s")
                self.stdout.write("-"*40)
        else:
            self.stdout.write("\n✅ No locked accounts found.\n")