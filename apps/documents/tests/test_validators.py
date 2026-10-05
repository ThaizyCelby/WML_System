"""Document validator tests."""
import pytest
from django.core.exceptions import ValidationError

from apps.documents.validators import (
    validate_file_extension, validate_file_size, validate_mime_type,
)


class FakeFile:
    def __init__(self, name='test.pdf', size=100, content_type='application/pdf'):
        self.name = name
        self.size = size
        self.content_type = content_type


class TestValidators:

    def test_size_within_limit(self):
        validate_file_size(FakeFile(size=1024))  # OK

    def test_size_over_limit(self):
        with pytest.raises(ValidationError):
            validate_file_size(FakeFile(size=20 * 1024 * 1024))

    def test_mime_allowed(self):
        validate_mime_type(FakeFile(content_type='application/pdf'))  # OK

    def test_mime_disallowed(self):
        with pytest.raises(ValidationError):
            validate_mime_type(FakeFile(content_type='application/x-msdownload'))

    def test_path_traversal_rejected(self):
        with pytest.raises(ValidationError):
            validate_file_extension(FakeFile(name='../../etc/passwd'))

    def test_double_extension_rejected(self):
        with pytest.raises(ValidationError):
            validate_file_extension(FakeFile(name='invoice.pdf.exe'))
