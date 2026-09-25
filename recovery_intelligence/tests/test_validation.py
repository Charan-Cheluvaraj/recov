import pytest
from recovery.validation import validate_jpeg, validate_pdf, validate_docx

def test_validation_interfaces():
    with pytest.raises(NotImplementedError):
        validate_jpeg(b"dummy")
    with pytest.raises(NotImplementedError):
        validate_pdf(b"dummy")
    with pytest.raises(NotImplementedError):
        validate_docx(b"dummy")
