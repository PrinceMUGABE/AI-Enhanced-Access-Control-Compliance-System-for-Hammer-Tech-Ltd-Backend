#departmenteApp/models.py
from django.db import models
from django.utils.timezone import now
from django.conf import settings


class Department(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]
    
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(default=now)
    created_by = models.ForeignKey(
        'userApp.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='departments_created'
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.name:
            self.name = self.name.strip().title()
        super().save(*args, **kwargs)
    
    def get_mentee_count(self):
        """Get count of mentees in this department"""
        return self.users.filter(role='employee').count()
    
    def get_mentor_count(self):
        """Get count of mentors associated with this department"""
        return self.mentors.count()