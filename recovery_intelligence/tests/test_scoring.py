import pytest
from intelligence.scoring import calculate_reconstruction_confidence, calculate_composite_integrity

def test_scoring_interfaces():
    with pytest.raises(NotImplementedError):
        calculate_reconstruction_confidence({})
    with pytest.raises(NotImplementedError):
        calculate_composite_integrity(0.8, 0.9, 1.0, 0.1)
