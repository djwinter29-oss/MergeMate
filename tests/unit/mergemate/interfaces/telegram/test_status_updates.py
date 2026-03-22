from mergemate.interfaces.telegram.status_updates import STATUS_EVENT_TYPES


def test_status_event_types_match_expected_order() -> None:
    assert STATUS_EVENT_TYPES == (
        "accepted",
        "queued",
        "running",
        "waiting_tool",
        "completed",
        "failed",
        "cancelled",
    )
