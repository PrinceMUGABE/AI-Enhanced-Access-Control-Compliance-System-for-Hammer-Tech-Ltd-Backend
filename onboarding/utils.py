# onboarding/utils.py
import os
import traceback
import uuid
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
import logging
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class FileUploadHandler:
    """
    Utility class for handling file uploads for onboarding modules
    """
    
    @staticmethod
    def get_storage_path(module_id, file_type):
        """Generate storage path for uploaded files"""
        # Create directory structure: media/modules/{module_id}/{file_type}/
        module_dir = Path('modules') / str(module_id) / file_type
        full_path = Path(settings.MEDIA_ROOT) / module_dir
        full_path.mkdir(parents=True, exist_ok=True)
        return module_dir, full_path
    
    @staticmethod
    def get_file_type(filename):
        """Determine file type based on extension"""
        if not filename:
            return 'other'
        
        ext = Path(filename).suffix.lower().lstrip('.')
        
        # Define allowed file types and extensions
        ALLOWED_TYPES = {
            'document': ['pdf', 'doc', 'docx', 'txt', 'rtf', 'odt', 'xls', 'xlsx', 'ppt', 'pptx'],
            'image': ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg', 'webp'],
            'video': ['mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm'],
            'audio': ['mp3', 'wav', 'ogg', 'm4a', 'flac'],
            'archive': ['zip', 'rar', '7z', 'tar', 'gz']
        }
        
        for file_type, extensions in ALLOWED_TYPES.items():
            if ext in extensions:
                return file_type
        
        return 'other'
    
    @staticmethod
    def validate_file(file, max_size=None, allowed_types=None):
        """Validate uploaded file"""
        if not file:
            raise ValidationError("No file provided")
        
        # Get file size in MB
        file_size = file.size / (1024 * 1024)  # Convert to MB
        
        # Use default max size if not provided
        max_size_mb = max_size or getattr(settings, 'MAX_FILE_SIZE_MB', 50)
        
        if file_size > max_size_mb:
            raise ValidationError(f"File size {file_size:.2f}MB exceeds maximum allowed size of {max_size_mb}MB")
        
        # Validate file type
        ext = Path(file.name).suffix.lower().lstrip('.')
        
        # Use default allowed types if not provided
        allowed_extensions = allowed_types or getattr(settings, 'ALLOWED_FILE_EXTENSIONS', [])
        
        if allowed_extensions and ext not in allowed_extensions:
            raise ValidationError(f"File type .{ext} is not allowed. Allowed types: {', '.join(allowed_extensions)}")
        
        return True
    
    @staticmethod
    def save_file(file, module_id, user_id, title=None, description=None):
        """
        Save uploaded file and return metadata
        
        Args:
            file: Uploaded file object
            module_id: ID of the module
            user_id: ID of the user uploading the file
            title: Optional custom title for the file
            description: Optional description
        
        Returns:
            dict: File metadata
        """
        try:
            # Validate file
            FileUploadHandler.validate_file(file)
            
            # Generate unique filename
            original_filename = file.name
            ext = Path(original_filename).suffix.lower()
            unique_filename = f"{uuid.uuid4()}{ext}"
            
            # Determine file type
            file_type = FileUploadHandler.get_file_type(original_filename)
            
            # Create storage path
            module_dir, full_path = FileUploadHandler.get_storage_path(module_id, file_type)
            
            # Save file
            fs = FileSystemStorage(location=str(full_path))
            saved_filename = fs.save(unique_filename, file)
            
            # Construct file URL
            file_url = Path(settings.MEDIA_URL) / module_dir / saved_filename
            absolute_path = full_path / saved_filename
            
            # Get file metadata
            file_size = file.size
            mime_type, _ = mimetypes.guess_type(original_filename)
            
            # Prepare metadata
            file_metadata = {
                'id': str(uuid.uuid4()),
                'original_filename': original_filename,
                'filename': saved_filename,
                'url': str(file_url),
                'path': str(absolute_path),
                'type': file_type,
                'mime_type': mime_type or 'application/octet-stream',
                'extension': ext.lstrip('.'),
                'size': file_size,
                'size_mb': round(file_size / (1024 * 1024), 2),
                'title': title or Path(original_filename).stem,
                'description': description or '',
                'uploaded_by': user_id,
                'uploaded_at': datetime.now().isoformat(),
                'last_modified': datetime.now().isoformat()
            }
            
            # Add additional metadata based on file type
            if file_type == 'image':
                # Could add image dimensions here if needed
                file_metadata['dimensions'] = {'width': None, 'height': None}
            
            logger.info(f"File saved successfully: {original_filename} -> {saved_filename}")
            return file_metadata
            
        except ValidationError as e:
            logger.error(f"File validation failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error saving file {file.name}: {str(e)}")
            logger.error(traceback.format_exc())
            raise Exception(f"Failed to save file: {str(e)}")
    
    @staticmethod
    def delete_file(file_path):
        """Delete a file from storage"""
        try:
            if not file_path:
                logger.warning("No file path provided for deletion")
                return False
            
            path = Path(file_path)
            if path.exists():
                path.unlink()
                logger.info(f"File deleted: {file_path}")
                
                # Try to remove empty parent directories
                try:
                    parent = path.parent
                    if parent.exists() and not any(parent.iterdir()):
                        parent.rmdir()
                        
                        # Remove module directory if empty
                        grandparent = parent.parent
                        if grandparent.exists() and not any(grandparent.iterdir()):
                            grandparent.rmdir()
                except:
                    pass  # Ignore errors cleaning up directories
                
                return True
            
            logger.warning(f"File not found: {file_path}")
            return False
            
        except Exception as e:
            logger.error(f"Error deleting file {file_path}: {str(e)}")
            raise Exception(f"Failed to delete file: {str(e)}")
    
    @staticmethod
    def get_file_info(file_path):
        """Get information about a file"""
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            
            stats = path.stat()
            mime_type, _ = mimetypes.guess_type(file_path)
            
            return {
                'path': str(path),
                'name': path.name,
                'size': stats.st_size,
                'size_mb': round(stats.st_size / (1024 * 1024), 2),
                'created': datetime.fromtimestamp(stats.st_ctime).isoformat(),
                'modified': datetime.fromtimestamp(stats.st_mtime).isoformat(),
                'mime_type': mime_type or 'application/octet-stream',
                'exists': True
            }
        except Exception as e:
            logger.error(f"Error getting file info for {file_path}: {str(e)}")
            return None
    
    @staticmethod
    def process_multiple_files(files_list, module_id, user_id):
        """Process multiple file uploads"""
        results = {
            'successful': [],
            'failed': []
        }
        
        for file_data in files_list:
            try:
                file = file_data.get('file')
                if not file:
                    continue
                
                title = file_data.get('title')
                description = file_data.get('description')
                
                metadata = FileUploadHandler.save_file(
                    file=file,
                    module_id=module_id,
                    user_id=user_id,
                    title=title,
                    description=description
                )
                
                results['successful'].append(metadata)
                
            except Exception as e:
                filename = file_data.get('file', {}).get('name', 'Unknown file')
                results['failed'].append({
                    'filename': filename,
                    'error': str(e)
                })
                logger.error(f"Failed to process file {filename}: {str(e)}")
        
        return results
    
    @staticmethod
    def cleanup_old_files(days_old=30):
        """Clean up files older than specified days"""
        try:
            media_root = Path(settings.MEDIA_ROOT)
            modules_dir = media_root / 'modules'
            
            if not modules_dir.exists():
                return {'deleted': 0, 'errors': []}
            
            cutoff_date = datetime.now() - timedelta(days=days_old)
            deleted_count = 0
            errors = []
            
            for module_folder in modules_dir.iterdir():
                if module_folder.is_dir():
                    for file_type_folder in module_folder.iterdir():
                        if file_type_folder.is_dir():
                            for file_path in file_type_folder.iterdir():
                                if file_path.is_file():
                                    try:
                                        # Check if file is older than cutoff
                                        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                                        if mtime < cutoff_date:
                                            file_path.unlink()
                                            deleted_count += 1
                                    except Exception as e:
                                        errors.append(f"Error deleting {file_path}: {str(e)}")
            
            logger.info(f"Cleaned up {deleted_count} old files")
            return {
                'deleted': deleted_count,
                'errors': errors
            }
            
        except Exception as e:
            logger.error(f"Error in cleanup_old_files: {str(e)}")
            return {
                'deleted': 0,
                'errors': [str(e)]
            }

