"""Configuração do banco de dados SQLite e sessão SQLAlchemy 2.0."""
from __future__ import annotations

from collections.abc import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    """Classe base para todos os modelos SQLAlchemy 2.0."""
    pass


def _configure_sqlite_pragmas(dbapi_connection, connection_record) -> None:
    """Ativa integridade referencial e modo WAL em todas as conexões SQLite."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON;")
    cursor.execute("PRAGMA journal_mode = WAL;")
    cursor.execute("PRAGMA synchronous = NORMAL;")
    cursor.execute("PRAGMA busy_timeout = 5000;")
    cursor.close()


engine: Engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)

event.listen(engine, "connect", _configure_sqlite_pragmas)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """Dependência FastAPI para fornecer sessão de banco por requisição."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
