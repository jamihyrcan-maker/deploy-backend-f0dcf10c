from __future__ import annotations

import os
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

# SQLite by default (file in project root)
DB_URL = os.getenv("DB_URL", "sqlite:///./robot_backend.db")

# For SQLite, check_same_thread must be False when used in web apps
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

engine = create_engine(DB_URL, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Create all tables (simple v0 approach; later you can add migrations)."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
