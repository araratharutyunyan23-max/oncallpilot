"""Postgres connection helper with pgvector type registration."""

import psycopg
from pgvector.psycopg import register_vector

from ..config import get_settings


def connect() -> psycopg.Connection:
    conn = psycopg.connect(get_settings().database_url, autocommit=True)
    register_vector(conn)
    return conn
