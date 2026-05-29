# manage_report_files.py
import os
from django.conf import settings
from incidentApp.models import Report

def fix_report_file_paths():
    """Fix existing report file paths"""
    for report in Report.objects.filter(file_path__isnull=False):
        if report.file_path.startswith(settings.MEDIA_ROOT):
            # This is an absolute path, convert to relative
            rel_path = report.file_path.replace(settings.MEDIA_ROOT, '').lstrip('/')
            report.file_path = rel_path
            report.save()
            print(f"Fixed report {report.report_number}: {rel_path}")