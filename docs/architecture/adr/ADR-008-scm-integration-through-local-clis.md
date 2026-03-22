# ADR-008: SCM Integration Through Local Authenticated CLIs

## Status

Accepted

## Decision

MergeMate will integrate with source control through locally installed and already authenticated command-line tools such as `git`, `gh`, and `glab`, instead of embedding platform OAuth flows in the MVP.

## Rationale

- keeps the MVP focused on coding workflow rather than auth infrastructure
- matches how many local developers already work
- reduces security and token-management scope inside the app
- supports GitHub and GitLab inspection with relatively small implementation cost

## In Plain Terms

If the user is already logged into GitHub or GitLab on their machine, MergeMate can reuse that environment. The app does not need to become its own identity broker in the MVP.

## Consequences

- platform support depends on the relevant CLI being installed and authenticated
- docs must clearly state this operational assumption
- the tool layer stays simple and shell-oriented
- deeper platform features may require richer adapters or OAuth later