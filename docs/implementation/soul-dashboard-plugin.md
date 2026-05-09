# Soul Dashboard Plugin — Implementation Notes

**Author:** Coder
**Date:** 2026-05-09

## Summary

Implemented a Hermes Dashboard plugin that displays real-time status of all
7 MergeMate Souls (roles): planner, architect, coder, tester, reviewer,
chronicler, explainer.

## Files Created

| File | Purpose |
|------|---------|
| `~/.hermes/plugins/soul-dashboard/dashboard/manifest.json` | Plugin manifest — name, icon, tab config, entry points |
| `~/.hermes/plugins/soul-dashboard/dashboard/plugin_api.py` | FastAPI backend — 5 read-only endpoints |
| `~/.hermes/plugins/soul-dashboard/dashboard/dist/index.js` | React frontend bundle (IIFE, uses Plugin SDK) |

## Backend API (`plugin_api.py`)

### Data Sources

- **MergeMate SQLite DB** — `~/.hermes/mergemate/state/mergemate.db` (runs, agent status)
- **Hermes Kanban DB** — `~/.hermes/kanban.db` (tasks, dispatcher events)
- **Process health** — PID files for gateway/dispatcher

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/plugins/soul-dashboard/souls` | All 7 Souls with computed status, task counts, workflow info, system health |
| `GET` | `/api/plugins/soul-dashboard/soul/{name}` | Single Soul detail + recent runs + tasks + workers |
| `GET` | `/api/plugins/soul-dashboard/runs?limit=20` | Recent run history from MergeMate DB |
| `GET` | `/api/plugins/soul-dashboard/tasks/{status}` | Kanban tasks filtered by status, aggregated by role |
| `GET` | `/api/plugins/soul-dashboard/system` | Gateway + dispatcher health status |

### Status Determination Logic

Each Soul's status is computed from active runs in the MergeMate DB:

- **active** — Soul has runs with `status = 'running'`
- **pending** — Soul has queued runs or pending kanban tasks
- **error** — Soul has failed runs
- **idle** — No activity

### Graceful Degradation

All endpoints handle missing DB files gracefully, returning empty states
with log warnings instead of crashing.

## Frontend (`dist/index.js`)

### Architecture

- Plain IIFE (no build step) using `window.__HERMES_PLUGIN_SDK__`
- Auto-discovery via `manifest.json` — no registration needed
- Registered as `"soul-dashboard"` tab via `window.__HERMES_PLUGINS__.register()`

### Components

- **SoulDashboardPage** — Main page component, manages polling loop
- **SoulCard** — Card per role with status dot, task counters, workflow badge
- **SystemStatusBar** — Gateway + dispatcher health indicators
- **PipelineVisualizer** — Horizontal pipeline showing Plan → Design → Implement → Test → Review → Chronicle
- **StatusDot** — Reusable pulsing/animated status indicator

### Behavior

- Polls `/souls` every 5 seconds for live updates
- Shows "Live" / "Error" indicator in header
- Empty state shown when no soul data available
- Pipeline highlights current stage based on which soul is active
- Cards show active top-bar glow for running roles

### Color Scheme

| Soul | Active | Idle |
|------|--------|------|
| Planner | #22d3ee (cyan) | #155e75 |
| Architect | #34d399 (emerald) | #065f46 |
| Coder | #a78bfa (violet) | #5b21b6 |
| Tester | #fbbf24 (amber) | #92400e |
| Reviewer | #fb7185 (rose) | #9f1239 |
| Chronicler | #f97316 (orange) | #9a3412 |
| Explainer | #94a3b8 (slate) | #475569 |

## Known Limitations

1. **Real-time delay** — 5s polling interval means up to 5s delay in status changes
2. **Worker count static** — Currently reports `worker_count: 1` for all roles (MergeMate DB doesn't store parallel worker count)
3. **Gateway uptime tracking** — Current implementation uses PID file mtime, not actual process start time

## Verification

Start the dashboard with `hermes dashboard` and navigate to the "Soul Dashboard" tab.
The plugin auto-discovers via `~/.hermes/plugins/soul-dashboard/dashboard/manifest.json`.