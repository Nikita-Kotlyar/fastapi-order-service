from __future__ import annotations

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models import Base


def test_all_tables_compile_for_postgres() -> None:
    """Catch SQLite-only types before the CI PostgreSQL job runs."""

    dialect = postgresql.dialect()
    statements = [str(CreateTable(table).compile(dialect=dialect)) for table in Base.metadata.sorted_tables]
    assert len(statements) == len(Base.metadata.tables) == 16
    assert any("JSON" in statement for statement in statements)
    assert any("TIMESTAMP WITH TIME ZONE" in statement for statement in statements)
    assert any("NUMERIC(18, 2)" in statement for statement in statements)
