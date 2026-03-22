# Operations And Observability

## MVP Focus

Observability should support debugging startup, run lifecycle, and operator-visible failures.

## Minimum Signals

- startup configuration source
- accepted run count
- active run count
- run state transitions
- run stage transitions sent back to Telegram while work is active
- terminal failures

## Operator Use Cases

- validate configuration before startup
- inspect default config path
- run locally with a repository config
- run as a user-space service with an explicit config path
- inspect run progress from Telegram with `/status` or via proactive stage updates