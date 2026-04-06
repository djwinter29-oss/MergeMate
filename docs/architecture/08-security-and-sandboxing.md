# Security And Sandboxing

## MVP Stance

The MVP should avoid promising arbitrary code execution. Code generation, explanation, and debugging help are in scope. Sandboxed execution remains a planned extension point.

## Risk Areas

- prompt injection through user content
- secret leakage through provider or tool misconfiguration
- unsafe execution if sandboxing is added later without isolation
- accidental overexposure of chat context

## Baseline Controls

- keep secrets in environment variables
- separate Telegram interface from provider and tool implementations
- record explicit run states
- make execution sandbox an abstraction, not a default capability
- require webhook ingress secret-token validation in webhook mode
- require `https` for non-loopback webhook public URLs