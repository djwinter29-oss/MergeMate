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
- built-in formatter placeholder
- built-in syntax checker placeholder
- built-in package installer tool behind config gating
- agent config listing enabled tools

## Future Expansion

- entry-point based plugin discovery
- tool permissions
- tool-specific resource limits
- tool telemetry and audit events

## Safety Boundary

Package installation is not enabled by default. Operators must explicitly turn it on in config and can restrict installation to an allowlist. This keeps the capability available for agent-assisted workflows without making runtime dependency changes implicit.