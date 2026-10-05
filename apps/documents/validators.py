"""File validators for documents."""
import mimetypes
from django.core.exceptions import ValidationError
from django.conf import settings


def validate_file_size(file):
    max_size = settings.SECURITY_CONFIG.get('MAX_FILE_UPLOAD_SIZE', 10 * 1024 * 1024)
    if file.size > max_size:
        raise ValidationError(f'File too large. Maximum size is {max_size // (1024*1024)} MB.')


def validate_mime_type(file):
    allowed_types = settings.SECURITY_CONFIG.get('ALLOWED_FILE_TYPES', [])
    if not allowed_types:
        return
    content_type = getattr(file, 'content_type', None)
    if not content_type:
        content_type, _ = mimetypes.guess_type(file.name)
    if content_type not in allowed_types:
        raise ValidationError(f'File type "{content_type}" is not allowed.')


def validate_file_extension(file):
    name = file.name.lower()
    if '..' in name or '/' in name or '\\' in name:
        raise ValidationError('Invalid filename.')
    parts = name.split('.')
    if len(parts) > 2 and parts[-1] in ('exe', 'dll', 'bat', 'cmd', 'sh', 'php', 'js'):
        raise ValidationError('Suspicious file extension.')
