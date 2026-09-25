import pytest
from recovery.fingerprinting import fingerprint_binary_fragment, fingerprint_text_fragment

def test_fingerprinting_interfaces():
    with pytest.raises(NotImplementedError):
        fingerprint_binary_fragment(b"hello world")
    with pytest.raises(NotImplementedError):
        fingerprint_text_fragment("hello world")
