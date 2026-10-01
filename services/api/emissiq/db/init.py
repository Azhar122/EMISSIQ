"""Schema bootstrap. The prototype creates tables directly rather than carrying
a migration history — there is one schema and it ships with the demo."""

from __future__ import annotations

from sqlalchemy import text

from .models import Base
from .session import engine, is_postgres


def init_db(drop: bool = False) -> None:
    if is_postgres():
        with engine.begin() as conn:
            # Required before the Vector columns can be created.
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    if drop:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    if is_postgres():
        # create_all never alters existing tables; relax a constraint that older
        # deployments created as NOT NULL.
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE repair_verifications ALTER COLUMN work_order_id DROP NOT NULL"
            ))


if __name__ == "__main__":
    import sys

    init_db(drop="--drop" in sys.argv)
    print("schema ready")
