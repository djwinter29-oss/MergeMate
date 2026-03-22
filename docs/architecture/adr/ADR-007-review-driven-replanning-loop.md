# ADR-007: Review-Driven Replanning Loop

## Status

Accepted

## Decision

MergeMate will allow the reviewer stage to trigger replanning when high-severity concerns are found. This loop is bounded by a configurable maximum iteration count.

## Rationale

- review findings should influence the plan, not just annotate the output
- unbounded review loops are operationally risky and hard to reason about
- a capped loop keeps the workflow deterministic enough for operators and users
- configuration allows teams to tune cost versus rigor

## In Plain Terms

If the reviewer says the design or implementation has a serious problem, MergeMate should not just return the flawed result. It should feed that concern back into planning and try again, but only up to a safe limit.

## Consequences

- run state must track review iteration count
- review output needs a machine-detectable high-concern signal
- planning must accept reviewer feedback as input
- the final result may represent one of several bounded refinement passes