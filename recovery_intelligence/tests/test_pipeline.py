import pytest
from pipeline import run_pipeline

def test_pipeline_interface():
    with pytest.raises(NotImplementedError):
        run_pipeline("dummy_evidence.dd")
