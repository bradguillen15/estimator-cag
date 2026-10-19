"""Postgres persistence (SQLAlchemy). The only package that imports sqlalchemy/psycopg.

Importing it never opens a connection: engines and sessions are built on demand.
"""
