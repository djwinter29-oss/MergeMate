# Plugin And Tool Architecture

## Intent

Tool invocation should be extensible without mixing provider logic, Telegram logic, and workflow logic together.

## Design Principles

- Tools are invoked through a runtime contract.
- Workflows ask for capabilities, not concrete implementations.
- Built-in tools ship inside the package.
- External tool packs can be added later.

## MVP Scope

- registry implementation
- built-in formatter tool
- built-in syntax checker tool
- built-in package installer tool behind config gating
- built-in source-control tools for `git`, `gh`, and `glab`
- agent config listing enabled tools

## Future Expansion

- entry-point based plugin discovery
- tool permissions
- tool-specific resource limits
- tool telemetry and audit events

## Safety Boundary

Package installation is not enabled by default. Operators must explicitly turn it on in config and can restrict installation to an allowlist. This keeps the capability available for agent-assisted workflows without making runtime dependency changes implicit.

Source-control platform support assumes the operator has already authenticated with the local CLI utilities. The MVP does not manage OAuth or tokens itself; it delegates to the existing authenticated environment.