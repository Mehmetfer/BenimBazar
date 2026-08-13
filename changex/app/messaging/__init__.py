"""CHANGE X messaging — phone-free conversations + support tickets."""

from __future__ import annotations

from .safety import ContactHit, detect_contact_info, ContactPolicy
from .service import (
    MessagingError,
    block_user,
    create_or_get_listing_conversation,
    create_support_ticket,
    get_conversation_for_user,
    inbox_for_user,
    list_messages,
    list_reports_for_staff,
    list_support_tickets,
    messaging_stats,
    moderate_report,
    report_message,
    reply_support_ticket,
    send_message,
    send_support_message,
    unblock_user,
)

__all__ = [
    "ContactHit",
    "ContactPolicy",
    "MessagingError",
    "block_user",
    "create_or_get_listing_conversation",
    "create_support_ticket",
    "detect_contact_info",
    "get_conversation_for_user",
    "inbox_for_user",
    "list_messages",
    "list_reports_for_staff",
    "list_support_tickets",
    "messaging_stats",
    "moderate_report",
    "report_message",
    "reply_support_ticket",
    "send_message",
    "send_support_message",
    "unblock_user",
]
