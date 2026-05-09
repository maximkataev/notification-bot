"""Data models for tasks and user profile."""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Task:
    """Parsed task with extracted fields."""

    id: Optional[int] = None
    user_id: int = 0
    raw_text: str = ""
    what: Optional[str] = None
    when_date: Optional[str] = None  # ISO format YYYY-MM-DD
    when_time: Optional[str] = None  # HH:MM
    place: Optional[str] = None
    place_hours: Optional[str] = None  # JSON string
    proposed_time: Optional[str] = None
    is_urgent: bool = False
    is_outdoor: bool = False
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None  # e.g., "every_monday", "mon_wed_fri", "every_day"
    recurrence_end_date: Optional[str] = None  # ISO format YYYY-MM-DD or None for indefinite
    constraints: Optional[str] = None  # Extra conditions/constraints
    status: str = "planned"  # planned | done | cancelled
    clarification_pending: bool = False
    clarification_question: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_tuple(self) -> tuple:
        """Convert to tuple for DB insert."""
        return (
            self.user_id,
            self.raw_text,
            self.what,
            self.when_date,
            self.when_time,
            self.place,
            self.place_hours,
            self.proposed_time,
            int(self.is_urgent),
            int(self.is_outdoor),
            int(self.is_recurring),
            self.recurrence_pattern,
            self.recurrence_end_date,
            self.status,
            int(self.clarification_pending),
            self.clarification_question,
        )


@dataclass
class UserProfile:
    """User preferences for planning."""

    user_id: int
    wake_time: str = "09:00"
    sleep_time: str = "23:00"
    preferences: str = ""
    timezone: str = "Asia/Tbilisi"
    updated_at: Optional[str] = None

    def to_tuple(self) -> tuple:
        return (
            self.user_id,
            self.wake_time,
            self.sleep_time,
            self.preferences,
            self.timezone,
        )


@dataclass
class ExchangeRate:
    """Historical exchange rate record."""

    id: Optional[int] = None
    pair: str = ""  # e.g., "EUR_USD", "USD_RUB"
    rate: float = 0.0
    timestamp: Optional[str] = None  # ISO format datetime

    def to_tuple(self) -> tuple:
        return (
            self.pair,
            self.rate,
            self.timestamp,
        )
