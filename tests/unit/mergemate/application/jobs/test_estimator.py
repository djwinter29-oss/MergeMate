import pytest

from mergemate.application.jobs.estimator import estimate_duration


@pytest.mark.parametrize(
    ("workflow", "expected_seconds"),
    [
        ("generate_code", 30),
        ("debug_code", 45),
        ("explain_code", 20),
        ("unknown", 60),
    ],
)
def test_estimate_duration_returns_expected_seconds(workflow: str, expected_seconds: int) -> None:
    assert estimate_duration(workflow) == expected_seconds