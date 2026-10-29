import pytest
from app.domain.types import classify_runner_provenance, ProvenanceType

def test_classify_runner_provenance():
    assert classify_runner_provenance("synthetic") == ProvenanceType.SIMULATION.value
    assert classify_runner_provenance("SYNTHETIC") == ProvenanceType.SIMULATION.value
    assert classify_runner_provenance("real_ai") == ProvenanceType.REAL_EXECUTION.value
    assert classify_runner_provenance("nebius") == ProvenanceType.REAL_EXECUTION.value
    assert classify_runner_provenance("NEBIUS") == ProvenanceType.REAL_EXECUTION.value
    assert classify_runner_provenance("unknown_runner") == ProvenanceType.UNKNOWN.value
    assert classify_runner_provenance("") == ProvenanceType.UNKNOWN.value
    assert classify_runner_provenance(None) == ProvenanceType.UNKNOWN.value
