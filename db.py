"""MySQL connection helpers for Indiana Hotel Booking."""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def get_db_config() -> dict[str, Any]:
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASS") or "",
        "database": os.getenv("DB_NAME", "IndianaHotel"),
    }


def get_connection():
    """Return a new connection to the configured database."""
    return mysql.connector.connect(**get_db_config())


def serialize_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def row_to_dict(row: dict) -> dict:
    return {k: serialize_value(v) for k, v in row.items()}
