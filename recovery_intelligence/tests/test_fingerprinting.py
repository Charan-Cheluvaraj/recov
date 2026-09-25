import pytest
from recovery.fingerprinting import fingerprint_binary_fragment, fingerprint_text_fragment
from models.feature_vector import FeatureVector

def test_fingerprinting_interfaces():
    b_fv = fingerprint_binary_fragment(b"hello world")
    assert isinstance(b_fv, FeatureVector)
    assert b_fv.dimension == 64
    assert len(b_fv.vector) == 64

    t_fv = fingerprint_text_fragment("hello world")
    assert isinstance(t_fv, FeatureVector)
    assert t_fv.dimension == 64
    assert len(t_fv.vector) == 64