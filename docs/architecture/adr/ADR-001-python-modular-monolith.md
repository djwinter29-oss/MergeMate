# ADR-001: Python Modular Monolith

## Status

Accepted

## Decision

The MVP will be implemented as a Python modular monolith.

## Rationale

- fastest route to a usable MVP
- simpler packaging for later PyPI distribution
- lower operational complexity than microservices
- internal boundaries still support future extraction

## In Plain Terms

MergeMate runs as one Python application, not as several networked services. The code is still split into clear modules so the team can evolve it without paying microservice complexity too early.

## Consequences

- simpler local development and packaging
- easier MVP debugging and release flow
- fewer operational moving parts
- future extraction is possible, but not free