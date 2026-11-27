"""Independent queue, frozen evidence, cached copy, and success cursor."""

from __future__ import annotations

import fcntl
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import MODEL, PROMPT_VERSION
from .evidence import digest


def job_key(repository: str, branch: str, frozen: dict) -> str:
    return digest([repository, branch, frozen["source_commit"], frozen["catalog_digest"],
                   PROMPT_VERSION, MODEL])


@contextmanager
def locked(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "news-agent.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another news-agent cycle holds the lock") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class State:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(directory / "news-agent.sqlite3")
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS cursors (scope TEXT PRIMARY KEY, sha TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS jobs (
                key TEXT PRIMARY KEY, scope TEXT NOT NULL, evidence TEXT NOT NULL,
                copy TEXT, copy_origin TEXT NOT NULL DEFAULT 'model',
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0, error TEXT, result TEXT
            );
        """)

    def close(self):
        self.db.close()

    def cursor(self, scope: str) -> str | None:
        row = self.db.execute("SELECT sha FROM cursors WHERE scope=?", (scope,)).fetchone()
        return row[0] if row else None

    def advance(self, scope: str, sha: str):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO cursors VALUES (?, ?)", (scope, sha))

    def enqueue(self, key: str, scope: str, frozen: dict):
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO jobs(key,scope,evidence) VALUES(?,?,?)",
                            (key, scope, json.dumps(frozen, ensure_ascii=False)))

    def job(self, key: str) -> dict:
        return dict(self.db.execute("SELECT * FROM jobs WHERE key=?", (key,)).fetchone())

    def pending(self, scope: str, mode: str) -> list[dict]:
        # A dry-run preview remains publishable without another model call.
        statuses = ("pending", "failed") if mode == "dry-run" else ("pending", "failed", "preview")
        marks = ",".join("?" for _ in statuses)
        return [dict(row) for row in self.db.execute(
            f"SELECT * FROM jobs WHERE scope=? AND status IN ({marks}) ORDER BY rowid",
            (scope, *statuses))]

    def queued_pipeline_ids(self, scope: str) -> set[str]:
        return {chain["pipeline_id"] for row in self.db.execute(
            "SELECT evidence FROM jobs WHERE scope=?", (scope,))
            for chain in json.loads(row[0])["chains"]}

    def cache_copy(self, key: str, copy: dict, *, manual: bool = False):
        with self.db:
            self.db.execute("UPDATE jobs SET copy=?,copy_origin=?,error=NULL WHERE key=?",
                            (json.dumps(copy, ensure_ascii=False),
                             "manual" if manual else "model", key))

    def finish(self, key: str, status: str, result: str):
        with self.db:
            self.db.execute("UPDATE jobs SET status=?,result=?,error=NULL WHERE key=?",
                            (status, result, key))

    def fail(self, key: str, error: str):
        with self.db:
            self.db.execute("UPDATE jobs SET status='failed', attempts=attempts+1, error=? WHERE key=?",
                            (error[:2000], key))

    def diagnostics(self) -> dict:
        return {"cursors": [dict(row) for row in self.db.execute("SELECT * FROM cursors")],
                "jobs": [dict(row) for row in self.db.execute(
                    "SELECT key,status,attempts,error,result FROM jobs ORDER BY rowid")]}
