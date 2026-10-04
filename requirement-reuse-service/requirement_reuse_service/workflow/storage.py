"""Transactional local artifact store with immutable sources and optimistic run updates."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def digest(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value).encode()).hexdigest()


def uid(prefix: str, *parts: Any) -> str:
    return f'{prefix}-{digest(parts)[:24]}'


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConflictError(ValueError):
    pass


class Store:
    def __init__(self, path: str | None = None):
        self.path = Path(path or os.environ.get('RQ1_WORKFLOW_STORE', '.rq1-workflow/workflow.sqlite3'))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS objects (
                  kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL,
                  PRIMARY KEY (kind, id));
                CREATE TABLE IF NOT EXISTS events (
                  sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                  event_type TEXT NOT NULL, body TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS commands (
                  run_id TEXT NOT NULL, key TEXT NOT NULL, payload_hash TEXT NOT NULL,
                  result TEXT NOT NULL, PRIMARY KEY(run_id, key));
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def put(self, kind: str, identifier: str, value: dict):
        body = canonical(value)
        with self.connect() as db:
            existing = db.execute('SELECT body FROM objects WHERE kind=? AND id=?', (kind, identifier)).fetchone()
            if existing and existing[0] != body:
                raise ConflictError(f'Immutable {kind} {identifier} already exists with different content.')
            db.execute('INSERT OR IGNORE INTO objects VALUES (?,?,?)', (kind, identifier, body))

    def get(self, kind: str, identifier: str) -> dict:
        with self.connect() as db:
            row = db.execute('SELECT body FROM objects WHERE kind=? AND id=?', (kind, identifier)).fetchone()
        if not row:
            raise KeyError(f'{kind} {identifier} not found')
        return json.loads(row[0])

    def list(self, kind: str) -> list[dict]:
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT body FROM objects WHERE kind=? ORDER BY rowid DESC', (kind,))]

    def mutate(self, run_id: str, expected_version: int | None, event_type: str,
               change: Callable[[dict], Any], *, key: str | None = None, payload: dict | None = None) -> dict:
        """The command result, event, and aggregate update share one transaction."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                old = db.execute('SELECT payload_hash,result FROM commands WHERE run_id=? AND key=?', (run_id, key)).fetchone()
                if old:
                    if old[0] != digest(payload):
                        raise ConflictError('Idempotency key reused with a different command.')
                    return json.loads(old[1])
            row = db.execute('SELECT body FROM objects WHERE kind="run" AND id=?', (run_id,)).fetchone()
            if not row:
                raise KeyError(run_id)
            run = json.loads(row[0])
            if expected_version is not None and expected_version != run['version']:
                raise ConflictError('The run has changed. Refresh before applying this command.')
            result = change(run)
            run['version'] += 1
            db.execute('UPDATE objects SET body=? WHERE kind="run" AND id=?', (canonical(run), run_id))
            db.execute('INSERT INTO events(run_id,event_type,body,created_at) VALUES(?,?,?,?)',
                       (run_id, event_type, canonical({'payload': payload, 'result': result, 'version': run['version']}), now()))
            response = {'run': run, 'result': result}
            if key:
                db.execute('INSERT INTO commands VALUES(?,?,?,?)', (run_id, key, digest(payload), canonical(response)))
            return response

    def events(self, run_id: str) -> list[dict]:
        with self.connect() as db:
            return [{'sequence': row[0], 'event_type': row[1], 'data': json.loads(row[2]), 'created_at': row[3]}
                    for row in db.execute('SELECT sequence,event_type,body,created_at FROM events WHERE run_id=? ORDER BY sequence', (run_id,))]
