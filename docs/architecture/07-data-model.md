# Data Model

## Primary Entities

### Agent Run

- run ID
- chat ID
- workflow
- status
- timestamps
- estimate
- terminal outcome

### Conversation

- chat ID
- ordered messages
- optional artifacts or references

### Agent Definition

- agent name
- workflow name
- enabled tools

## Persistence Roadmap

MVP starts with interface contracts and SQLite placeholders. The intended persistent tables later are:

- `agent_runs`
- `conversation_messages`
- `artifacts`
- `tool_invocations`