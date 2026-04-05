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
- Telegram delivery failures for progress or terminal notifications
- duplicate-dispatch prevention for active runs

## Operator Use Cases

- validate configuration before startup
- inspect default config path
- run locally with a repository config
- run as a user-space service with an explicit config path
- inspect run progress from Telegram with `/status` or via proactive stage updates

## Runtime Expectations

- Progress delivery should degrade gracefully when Telegram rejects or temporarily fails a send. A failed progress update should be logged without terminating the watcher for that run.
- User-visible Telegram messages may need chunking to remain within platform payload limits. This applies to terminal output as well as large planning, error, `/status`, `/tools`, or progress messages that include verbose tool detail.
- Terminal Telegram delivery should use the same retry-tolerant watcher path as in-flight progress updates so a transient send failure does not permanently hide the final run outcome.
- A run that is already `running`, `waiting_tool`, `completed`, `failed`, or `cancelled` should not be re-entered by a duplicate background dispatch, including when multiple runtime instances share the same persisted state.
- Local CLI dependencies such as `git`, `gh`, `glab`, and `pip` are operational dependencies and should fail within a bounded timeout instead of blocking worker capacity indefinitely.