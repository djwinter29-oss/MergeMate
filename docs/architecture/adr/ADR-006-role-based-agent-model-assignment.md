# ADR-006: Role-Based Agent Model Assignment

## Status

Accepted

## Decision

MergeMate will assign workflow roles such as planner, architect, coder, tester, and reviewer through configuration. Each role can use one or more provider aliases, and different roles may use different models.

## Rationale

- planning, design, coding, testing, and review often benefit from different models
- keeps role selection out of hardcoded runtime logic
- makes experimentation cheaper by moving model choice into config
- supports future expansion without changing the workflow contract

## In Plain Terms

The system should not assume one model is best at everything. Instead, each stage of the workflow gets its own configurable role, and each role can point to the model setup that fits it best.

## Consequences

- workflow control must map runtime stages to configured role names
- config needs stable role definitions and provider alias lists
- testing must verify that each stage routes to the intended role
- documentation must explain role responsibilities clearly