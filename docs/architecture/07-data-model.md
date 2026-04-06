# Data Model

## Primary Entities

### Agent Run

- run ID
- chat ID
- user ID
- agent name
- workflow
- status
- current stage
- original prompt
- plan text
- design text
- test text
- review text
- review iteration count
- approval flag
- result text
- error text
- timestamps
- estimate

### Run Job

- job ID
- run ID
- job type
- status
- error text
- queued timestamp
- started timestamp
- finished timestamp
- updated timestamp

### Conversation

- chat ID
- ordered messages
- role per message
- message content
- creation time

### Learning Entry

- chat ID
- workflow
- original prompt
- stored result excerpt
- creation time

### Agent Definition

- agent name
- workflow name
- enabled tools
- provider aliases
- parallel mode
- combine strategy

## Current Persistence

The MVP persists state in SQLite. The current tables are:

- `agent_runs`
- `conversation_messages`
- `learning_entries`
- `run_jobs`

Artifacts such as plan, design, tests, review, and final result are currently stored directly on the `agent_runs` record instead of a separate artifact table.

The new `run_jobs` table is the first step toward an honest ingress and worker split. It persists planning and execution dispatch separately from the user-facing run record so later worker processes can coordinate through shared storage instead of in-memory task ownership.