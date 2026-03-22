# Diagrams Guide

These diagrams summarize the current MergeMate MVP architecture from three different viewpoints.

## How To Read Them

- start with the system context diagram for the broad external view
- then read the container view for the major runtime parts inside the application
- finish with the sequence diagram to understand the approval and execution flow

## Diagram Notes

- `Telegram Interface` means the polling-based bot entrypoint and message handlers
- `Planning Service` means the plan-drafting stage that happens before approval-gated execution
- `Background Worker` means the asynchronous execution path for approved or auto-dispatched runs
- `Configured LLM Providers` means the current OpenAI-compatible provider endpoints configured by URL
- `Tool Runtime` means built-in tools such as formatting, syntax checks, package installation, and source-control CLI integration

## Files

- [System Context](./system-context.mmd): external actors and system dependencies
- [Container View](./container-view.mmd): main runtime components and their relationships
- [Sequence Message Flow](./sequence-message-flow.mmd): prompt submission, approval, background execution, progress updates, and final response

## Current Scope Reminder

These diagrams describe the current MVP draft. They do not imply that webhook mode, sandboxed execution, or non-OpenAI-compatible provider adapters are already implemented.