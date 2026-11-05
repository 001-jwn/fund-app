"""SQLite startup. Two engines share one file, and a locked WAL pragma does not crash."""

from __future__ import annotations

import sqlite3
import threading

from app.db import SQLITE_BUSY_TIMEOUT_MS, make_engine


def test_two_engines_connect_to_the_same_sqlite_file(tmp_path):
    url = "sqlite:///" + (tmp_path / "fund.db").as_posix()
    first = make_engine(url)
    second = make_engine(url)
    try:
        with first.connect() as left, second.connect() as right:
            assert left.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
            assert right.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
            assert left.exec_driver_sql("PRAGMA busy_timeout").scalar() == SQLITE_BUSY_TIMEOUT_MS
            assert right.exec_driver_sql("PRAGMA busy_timeout").scalar() == SQLITE_BUSY_TIMEOUT_MS
            assert left.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            left.exec_driver_sql("CREATE TABLE ping (id INTEGER)")
            left.commit()
            assert right.exec_driver_sql(
                "SELECT count(*) FROM sqlite_master WHERE name = 'ping'"
            ).scalar() == 1
    finally:
        first.dispose()
        second.dispose()


def test_wal_pragma_does_not_crash_when_the_database_is_locked(tmp_path):
    path = tmp_path / "fund.db"
    url = "sqlite:///" + path.as_posix()
    holder = sqlite3.connect(path)
    holder.execute("CREATE TABLE held (id INTEGER)")
    holder.execute("BEGIN IMMEDIATE")
    holder.execute("INSERT INTO held VALUES (1)")
    engine = make_engine(url)
    try:
        # journal_mode=WAL raises "database is locked" at once while this
        # write is open. Connecting must still succeed.
        with engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == SQLITE_BUSY_TIMEOUT_MS
            assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() != "wal"
    finally:
        holder.close()
        engine.dispose()

    quiet = make_engine(url)
    try:
        with quiet.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
    finally:
        quiet.dispose()


def test_two_engines_can_connect_in_the_same_moment(tmp_path):
    url = "sqlite:///" + (tmp_path / "fresh.db").as_posix()
    first = make_engine(url)
    second = make_engine(url)
    errors: list[Exception] = []
    barrier = threading.Barrier(2)

    def connect(engine):
        try:
            barrier.wait(timeout=5)
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1").scalar()
        except Exception as exc:
            errors.append(exc)

    threads = [
        threading.Thread(target=connect, args=(first,)),
        threading.Thread(target=connect, args=(second,)),
    ]
    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        assert not any(thread.is_alive() for thread in threads)
        assert errors == []
    finally:
        first.dispose()
        second.dispose()

    # A connection that lost the startup race may have skipped WAL. A later
    # connection, once nobody else is opening the file, still turns WAL on.
    check = make_engine(url)
    try:
        with check.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
            assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == SQLITE_BUSY_TIMEOUT_MS
    finally:
        check.dispose()
