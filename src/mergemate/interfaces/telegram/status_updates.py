"""Status update strategy for chat notifications."""


STATUS_EVENT_TYPES = (
    "accepted",
    "queued",
    "running",
    "waiting_tool",
    "completed",
    "failed",
    "cancelled",
)