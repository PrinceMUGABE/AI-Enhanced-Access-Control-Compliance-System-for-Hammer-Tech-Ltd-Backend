# models.py in trainingApp
from django.db import models
from django.conf import settings


class Training(models.Model):
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trainings')
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True, null=True)  # Added description field
    created_at = models.DateTimeField(auto_now_add=True)
    picture_data = models.BinaryField(blank=True, null=True)

    def __str__(self):
        return f"{self.name}"
    
    def get_total_materials_count(self):
        """Get total count of materials across all modules"""
        return sum(module.materials.count() for module in self.modules.all())


class Module(models.Model):
    training = models.ForeignKey(Training, on_delete=models.CASCADE, related_name='modules')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.training.name}"
    
    def get_materials_count(self):
        """Get count of materials in this module"""
        return self.materials.count()


class TrainingMaterial(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='materials', null=True)
    file = models.FileField(upload_to='training_materials/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Material for {self.module.name}"
    
    def get_file_size(self):
        """Get file size in a human readable format"""
        try:
            size = self.file.size
            for unit in ['bytes', 'KB', 'MB', 'GB']:
                if size < 1024.0:
                    return f"{size:.1f} {unit}"
                size /= 1024.0
            return f"{size:.1f} TB"
        except:
            return "Unknown"
    
    def get_filename(self):
        """Get just the filename without path"""
        import os
        return os.path.basename(self.file.name) if self.file else None