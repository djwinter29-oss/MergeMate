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
    short_estimate = estimate_duration("generate_code", "fix typo")
    complex_prompt = """
Implement auth database migration and API schema.

1. update schema
2. add API endpoint

```python
print('x')
```
"""
    complex_estimate = estimate_duration("generate_code", complex_prompt)

    assert short_estimate == 24
    assert complex_estimate > short_estimate


def test_estimate_duration_accounts_for_structured_multi_file_prompts() -> None:
    complex_prompt = """
Implement auth database migration and API schema.

1. update schema
2. add API endpoint

```python
print('x')
```
"""
    structured_prompt = """
Update src/mergemate/cli.py and tests/unit/mergemate/test_cli.py.

- add a command handler
- adjust the README
- expand the regression tests

```python
print("hello")
```
"""

    complex_estimate = estimate_duration("generate_code", complex_prompt)
    structured_estimate = estimate_duration("generate_code", structured_prompt)

    assert structured_estimate > complex_estimate
