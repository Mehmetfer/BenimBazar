"""Unit test for messaging autonomy observations."""

from autonomy.messaging_observe import observe_messaging_health


def test_messaging_observe_healthy_and_backlog():
    healthy = observe_messaging_health(stats={"reported_messages": 0, "open_support_tickets": 1})
    assert healthy[0].kind == "HEALTHY"
    backlog = observe_messaging_health(stats={"reported_messages": 9, "open_support_tickets": 12})
    kinds = {o.kind for o in backlog}
    assert "MODERATION_BACKLOG" in kinds
    assert "SUPPORT_BACKLOG" in kinds
    errs = observe_messaging_health(api_errors=["delivery_timeout"])
    assert errs[0].kind == "API_ERROR"
