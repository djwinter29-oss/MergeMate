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


def test_estimate_duration_uses_prompt_complexity() -> None:
    assert estimate_duration("generate_code", "fix typo") == 24

    complex_prompt = """
Implement auth database migration and API schema.

1. update schema
2. add API endpoint

```python
print('x')
```
"""

    assert estimate_duration("generate_code", complex_prompt) == 45
