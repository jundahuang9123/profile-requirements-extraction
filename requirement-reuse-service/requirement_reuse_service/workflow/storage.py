"""Transactional local artifact store with immutable sources and optimistic run updates.

A workflow run is a JSON document plus separately stored *parts*: collections that are
only appended to or written once and that grow with every model call or stage (model
call records, stage copies, the frozen machine snapshot, attempt history, baselines,
extraction excerpt catalogues). Keeping them out of the document means that updating a
run rewrites only the document. The run's status and worker lease are also kept in a
small state row, so that extending the lease before each model call writes only that row.
``get`` / ``get_run`` and ``mutate(..., hydrate=True)`` assemble the complete run, so
readers see the same structure as before. Runs saved by earlier versions keep their parts
inline until their next update, which moves the parts to rows.

A command repeated under its idempotency key returns its first response unchanged: the run
document saved with the command and the parts as they were at that moment. To make that
possible, a part row that a saved response included is kept in ``run_part_history`` when a
later update replaces or removes it.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
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


class PartNotLoaded(RuntimeError):
    """A change function read a run part that mutate did not load."""


# Run parts stored as rows next to the run document, with their shape and empty value.
# ``catalogues`` maps the hash of each extraction excerpt catalogue to the catalogue.
RUN_PARTS = {'model_calls': list, 'attempt_history': list, 'baselines': list, 'base_check_audit': list,
             'stage_results': dict, 'machine_snapshot': dict, 'catalogues': dict, 'assessment_reuse': dict,
             'consolidation_chunks': dict, 'need_chunks': dict, 'need_steps': dict, 'stakeholder_audit': dict}
_LISTS = {name for name, shape in RUN_PARTS.items() if shape is list}
_VALUES = {'machine_snapshot'}          # stored as one row; every other dict is keyed per entry
_MISSING = object()


class _WriteOnlyPart:
    """Stand-in for an unloaded run part inside ``mutate``: records writes, refuses reads.

    It deliberately is no list or dict, so that serializing or copying it fails loudly
    instead of silently producing an empty value.
    """

    def __init__(self, name: str):
        self._name = name
        self._operations: list[tuple[str, Any, Any]] = []

    def _refuse(self, *_args, **_kwargs):
        raise PartNotLoaded(f"Run part '{self._name}' is stored separately; call mutate(..., parts=True) to read it.")

    __iter__ = __len__ = __getitem__ = __contains__ = __bool__ = __eq__ = _refuse
    __hash__ = None
    keys = values = items = get = copy = index = count = _refuse

    def __repr__(self):
        return f'<write-only run part {self._name}>'


class _WriteOnlyList(_WriteOnlyPart):
    def append(self, item):
        self._operations.append(('append', None, item))

    def extend(self, items):
        for item in items:
            self.append(item)


class _WriteOnlyDict(_WriteOnlyPart):
    def __setitem__(self, key, value):
        self._operations.append(('set', key, value))

    def update(self, *args, **kwargs):
        for key, value in dict(*args, **kwargs).items():
            self[key] = value

    def pop(self, key, default=None):
        """Remove ``key``. The removed value is not loaded, so ``default`` is returned."""
        self._operations.append(('delete', key, None))
        return default

    def __delitem__(self, key):
        self.pop(key)


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
                CREATE TABLE IF NOT EXISTS run_parts (
                  sequence INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
                  part TEXT NOT NULL, key TEXT NOT NULL, body TEXT NOT NULL,
                  UNIQUE (run_id, part, key));
                CREATE TABLE IF NOT EXISTS run_state (
                  run_id TEXT PRIMARY KEY, status TEXT NOT NULL, lease_until REAL NOT NULL,
                  replay_sequence INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS run_part_history (
                  sequence INTEGER NOT NULL, run_id TEXT NOT NULL, part TEXT NOT NULL,
                  key TEXT NOT NULL, body TEXT NOT NULL, retired_at INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS run_part_history_by_run ON run_part_history (run_id, sequence);
                -- A run's events are read without scanning every run's events; the scan held the read lock
                -- for over 30 s on the 1.8 GB store and a live run's next write failed (30 Oct).
                CREATE INDEX IF NOT EXISTS events_by_run ON events (run_id, sequence);
            ''')
            # Databases written by this layout before saved responses recorded their parts.
            if 'replay_sequence' not in {row[1] for row in db.execute('PRAGMA table_info(run_state)')}:
                try:
                    db.execute('ALTER TABLE run_state ADD COLUMN replay_sequence INTEGER NOT NULL DEFAULT 0')
                except sqlite3.OperationalError as exc:     # another process added it meanwhile
                    if 'duplicate column' not in str(exc):
                        raise

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
        if kind == 'run':
            return self._put_run(identifier, value)
        body = canonical(value)
        with self.connect() as db:
            existing = db.execute('SELECT body FROM objects WHERE kind=? AND id=?', (kind, identifier)).fetchone()
            if existing and existing[0] != body:
                raise ConflictError(f'Immutable {kind} {identifier} already exists with different content.')
            db.execute('INSERT OR IGNORE INTO objects VALUES (?,?,?)', (kind, identifier, body))

    def get(self, kind: str, identifier: str) -> dict:
        if kind == 'run':
            return self.get_run(identifier)
        with self.connect() as db:
            row = db.execute('SELECT body FROM objects WHERE kind=? AND id=?', (kind, identifier)).fetchone()
        if not row:
            raise KeyError(f'{kind} {identifier} not found')
        return json.loads(row[0])

    def list(self, kind: str) -> list[dict]:
        """All objects of a kind; runs as stored documents, without their separately stored parts."""
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT body FROM objects WHERE kind=? ORDER BY rowid DESC', (kind,))]

    # Runs --------------------------------------------------------------------------------

    def get_run(self, run_id: str, *, parts: bool = True, omit: tuple[str, ...] = ()) -> dict:
        """The run document; with ``parts`` (default) the complete run including its parts.

        ``omit`` leaves out the named parts. The document and its parts are read in one
        transaction, so they belong to the same saved state.
        """
        with self.connect() as db:
            db.execute('BEGIN')
            run = self._load_run(db, run_id)
            if not parts:
                return self._without_parts(run)
            run = self._attach_parts(db, run_id, run, omit=omit)
            return {key: value for key, value in run.items() if key not in omit}

    def get_run_part_entry(self, run_id: str, part: str, key: str) -> Any:
        """``get_run(run_id)[part].get(key)`` for a keyed part, reading only that entry's row.

        A step looking up one saved answer otherwise reads the run document and every part row,
        which grows with the run. A run whose document still holds the part inline (an earlier
        layout) is read in full, where its inline and stored entries are merged.
        """
        if part in _LISTS or part in _VALUES or part not in RUN_PARTS:
            raise ValueError(f'{part} is not a keyed part of a run.')
        with self.connect() as db:
            db.execute('BEGIN')
            inline = db.execute("SELECT json_type(body, '$.' || ?) FROM objects WHERE kind='run' AND id=?",
                                (part, run_id)).fetchone()
            row = db.execute('SELECT body FROM run_parts WHERE run_id=? AND part=? AND key=?', (run_id, part, key)).fetchone()
        if inline is None:
            raise KeyError(f'run {run_id} not found')
        if inline[0] is not None:
            return self.get_run(run_id, omit=tuple(name for name in RUN_PARTS if name != part))[part].get(key)
        return json.loads(row[0]) if row else None

    def mutate(self, run_id: str, expected_version: int | None, event_type: str,
               change: Callable[[dict], Any], *, key: str | None = None, payload: dict | None = None,
               parts: bool = False, hydrate: bool = False) -> dict:
        """The command result, event, and aggregate update share one transaction.

        ``change`` receives the run document. Its parts are write-only stand-ins: appending
        to a list part, setting or removing entries of ``stage_results``, and assigning a
        part are saved without loading the part. With ``parts=True`` the parts are loaded
        and any change to them is saved. With ``hydrate=True`` the returned run includes
        the parts, as API responses need.

        A command repeated with the same ``key`` and payload is not applied again; it returns
        the response of its first application (see ``_replayed``).
        """
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if key:
                old = db.execute('SELECT payload_hash,result FROM commands WHERE run_id=? AND key=?', (run_id, key)).fetchone()
                if old:
                    if old[0] != digest(payload):
                        raise ConflictError('Idempotency key reused with a different command.')
                    return self._replayed(db, run_id, json.loads(old[1]), hydrate)
            run = self._load_run(db, run_id)
            self._move_inline_parts(db, run_id, run)
            if expected_version is not None and expected_version != run['version']:
                raise ConflictError('The run has changed. Refresh before applying this command.')
            if parts:
                loaded, before = self._read_parts(db, run_id, with_bodies=True)
                run.update(loaded)
            else:
                before = None
                # A value part (the machine snapshot) can only be replaced as a whole.
                run.update({name: _WriteOnlyList(name) if name in _LISTS else
                            _WriteOnlyPart(name) if name in _VALUES else _WriteOnlyDict(name) for name in RUN_PARTS})
            result = change(run)
            run['version'] += 1
            self._save_parts(db, run_id, run, before)
            self._write_run(db, run_id, run)
            db.execute('INSERT INTO events(run_id,event_type,body,created_at) VALUES(?,?,?,?)',
                       (run_id, event_type, canonical({'payload': payload, 'result': result, 'version': run['version']}), now()))
            response = {'run': run, 'result': result}
            if key:
                # The response includes the part rows saved so far; record that position, and
                # keep the rows it includes when later updates replace or remove them.
                position = self._high_water(db)
                db.execute('INSERT INTO commands VALUES(?,?,?,?)',
                           (run_id, key, digest(payload), canonical({**response, 'parts_sequence': position})))
                db.execute('UPDATE run_state SET replay_sequence=? WHERE run_id=?', (position, run_id))
            if hydrate:
                response = {'run': self._attach_parts(db, run_id, dict(run)), 'result': result}
            return response

    def append_run_part(self, run_id: str, part: str, item: Any, *, event_type: str | None = None) -> None:
        """Append one item to a list part without rewriting the run document."""
        if part not in _LISTS:
            raise ValueError(f'{part} is not a list part of a run.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM objects WHERE kind="run" AND id=?', (run_id,)).fetchone():
                raise KeyError(run_id)
            key = uuid.uuid4().hex
            db.execute('INSERT INTO run_parts(run_id,part,key,body) VALUES(?,?,?,?)', (run_id, part, key, canonical(item)))
            if event_type:
                db.execute('INSERT INTO events(run_id,event_type,body,created_at) VALUES(?,?,?,?)',
                           (run_id, event_type, canonical({'payload': None, 'result': {'part': part, 'key': key}, 'version': None}), now()))

    def set_run_part_entry(self, run_id: str, part: str, key: str, value: Any) -> None:
        """Add one entry of a keyed part without rewriting the run document.

        For entries whose key identifies their content (a catalogue under its hash): an
        existing entry is kept, and a different value under the same key is refused.
        """
        if part in _LISTS or part in _VALUES or part not in RUN_PARTS:
            raise ValueError(f'{part} is not a keyed part of a run.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM objects WHERE kind="run" AND id=?', (run_id,)).fetchone():
                raise KeyError(run_id)
            body = canonical(value)
            existing = db.execute('SELECT body FROM run_parts WHERE run_id=? AND part=? AND key=?',
                                  (run_id, part, key)).fetchone()
            if existing is None:
                db.execute('INSERT INTO run_parts(run_id,part,key,body) VALUES(?,?,?,?)', (run_id, part, key, body))
            elif existing[0] != body:
                raise ConflictError(f'{part} entry {key} already exists with different content.')

    def touch_run(self, run_id: str, lease_until: float) -> None:
        """Extend the worker lease before a model call, refusing a cancelled run.

        Only the small state row changes; ``get_run`` and ``mutate`` read the lease from it.
        """
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM run_state WHERE run_id=?', (run_id,)).fetchone()
            if row is None:
                run = self._load_run(db, run_id)
                self._write_state(db, run_id, run)
                status = run['status']
            else:
                status = row[0]
            if status == 'cancelled':
                raise ConflictError('Run cancelled before provider call.')
            db.execute('UPDATE run_state SET lease_until=? WHERE run_id=?', (lease_until, run_id))

    def events(self, run_id: str) -> list[dict]:
        with self.connect() as db:
            return [{'sequence': row[0], 'event_type': row[1], 'data': json.loads(row[2]), 'created_at': row[3]}
                    for row in db.execute('SELECT sequence,event_type,body,created_at FROM events WHERE run_id=? ORDER BY sequence', (run_id,))]

    # Internals ----------------------------------------------------------------------------

    def _put_run(self, run_id: str, value: dict):
        run = dict(value)
        with self.connect() as db:
            if db.execute('SELECT 1 FROM objects WHERE kind="run" AND id=?', (run_id,)).fetchone():
                raise ConflictError(f'Run {run_id} already exists.')
            db.execute('INSERT INTO objects VALUES (?,?,?)', ('run', run_id, canonical(self._without_parts(run))))
            self._move_inline_parts(db, run_id, run)
            self._write_state(db, run_id, run)

    def _load_run(self, db, run_id: str) -> dict:
        row = db.execute('SELECT body FROM objects WHERE kind="run" AND id=?', (run_id,)).fetchone()
        if not row:
            raise KeyError(f'run {run_id} not found')
        run = json.loads(row[0])
        state = db.execute('SELECT lease_until FROM run_state WHERE run_id=?', (run_id,)).fetchone()
        if state is not None:
            run['job_lease_until'] = state[0]       # touch_run extends the lease outside mutate
        return run

    @staticmethod
    def _without_parts(run: dict) -> dict:
        return {key: value for key, value in run.items() if key not in RUN_PARTS}

    def _write_run(self, db, run_id: str, run: dict):
        db.execute('UPDATE objects SET body=? WHERE kind="run" AND id=?', (canonical(run), run_id))
        self._write_state(db, run_id, run)

    @staticmethod
    def _write_state(db, run_id: str, run: dict):
        db.execute('INSERT INTO run_state(run_id,status,lease_until) VALUES(?,?,?) ON CONFLICT(run_id) '
                   'DO UPDATE SET status=excluded.status, lease_until=excluded.lease_until',
                   (run_id, run['status'], float(run.get('job_lease_until') or 0)))

    def _move_inline_parts(self, db, run_id: str, run: dict):
        """Move parts that an earlier version kept inside the run document to rows.

        Rows that already exist are newer: model calls recorded since the upgrade stay
        after the inline ones, and stored entries win over inline entries.
        """
        for name in RUN_PARTS:
            value = run.pop(name, _MISSING)
            if value is _MISSING or not value:
                continue
            if name in _LISTS:
                newer = db.execute('SELECT key,body FROM run_parts WHERE run_id=? AND part=? ORDER BY sequence',
                                   (run_id, name)).fetchall()
                db.execute('DELETE FROM run_parts WHERE run_id=? AND part=?', (run_id, name))
                self._append_rows(db, run_id, name, value)
                db.executemany('INSERT INTO run_parts(run_id,part,key,body) VALUES(?,?,?,?)',
                               [(run_id, name, key, body) for key, body in newer])
            else:
                entries = {'': value} if name in _VALUES else value
                db.executemany('INSERT OR IGNORE INTO run_parts(run_id,part,key,body) VALUES(?,?,?,?)',
                               [(run_id, name, key, canonical(item)) for key, item in entries.items()])

    def _read_parts(self, db, run_id: str, *, with_bodies: bool = False, omit: tuple[str, ...] = ()):
        """Stored parts; with ``with_bodies`` also their serialized rows, to detect changes.
        Omitted parts are not read."""
        names = [name for name in RUN_PARTS if name not in omit]
        rows = db.execute(f'SELECT part,key,body FROM run_parts WHERE run_id=? AND part IN ({",".join("?" * len(names))}) '
                          'ORDER BY sequence', (run_id, *names))
        return self._collect_parts(rows, with_bodies=with_bodies, omit=omit)

    @staticmethod
    def _collect_parts(rows, *, with_bodies: bool = False, omit: tuple[str, ...] = ()):
        """Assemble parts from (part, key, body) rows in saving order."""
        parts = {name: shape() for name, shape in RUN_PARTS.items()}
        bodies = {name: [] if name in _LISTS else None if name in _VALUES else {} for name in RUN_PARTS}
        for name, key, body in rows:
            if name not in RUN_PARTS or name in omit:
                continue
            value = json.loads(body)
            if name in _LISTS:
                parts[name].append(value)
                bodies[name].append(body)
            elif name in _VALUES:
                parts[name], bodies[name] = value, body
            else:
                parts[name][key] = value
                bodies[name][key] = body
        return (parts, bodies) if with_bodies else parts

    def _attach_parts(self, db, run_id: str, run: dict, *, omit: tuple[str, ...] = ()) -> dict:
        stored = self._read_parts(db, run_id, omit=omit)
        for name in RUN_PARTS:
            inline = run.get(name)
            if not inline:
                run[name] = stored[name]
            elif name in _LISTS:
                run[name] = [*inline, *stored[name]]           # not yet moved: rows are newer
            elif name in _VALUES:
                run[name] = stored[name] or inline
            else:
                run[name] = {**inline, **stored[name]}
        return run

    # Repeated commands -------------------------------------------------------------------

    def _replayed(self, db, run_id: str, saved: dict, hydrate: bool) -> dict:
        """The response a command returned when it was first applied.

        Its run document was saved with the command; its parts are the rows saved up to the
        recorded position that had not yet been replaced or removed at the command's version.
        """
        position = saved.pop('parts_sequence', None)
        if position is not None:
            if hydrate:
                parts = self._parts_as_of(db, run_id, position, saved['run']['version'])
                saved['run'] = {**saved['run'], **parts}
            return saved
        if set(RUN_PARTS) & saved['run'].keys():
            return saved     # saved by an earlier version with the parts inline, as it was returned
        # Saved by this layout before responses recorded their position: the run as it is now,
        # document and parts read together.
        run = self._load_run(db, run_id)
        return {'run': self._attach_parts(db, run_id, run) if hydrate else self._without_parts(run),
                'result': saved['result']}

    def _parts_as_of(self, db, run_id: str, position: int, version: int) -> dict:
        rows = db.execute(
            'SELECT part,key,body FROM ('
            ' SELECT sequence,part,key,body FROM run_parts WHERE run_id=? AND sequence<=?'
            ' UNION ALL'
            ' SELECT sequence,part,key,body FROM run_part_history WHERE run_id=? AND sequence<=? AND retired_at>?'
            ') ORDER BY sequence', (run_id, position, run_id, position, version))
        return self._collect_parts(rows)

    @staticmethod
    def _high_water(db) -> int:
        """The position of the last part row saved, in any run."""
        row = db.execute("SELECT seq FROM sqlite_sequence WHERE name='run_parts'").fetchone()
        return row[0] if row else 0

    @staticmethod
    def _replay_mark(db, run_id: str) -> int:
        """Rows up to this position are included in a saved response of the run."""
        row = db.execute('SELECT replay_sequence FROM run_state WHERE run_id=?', (run_id,)).fetchone()
        return row[0] if row else 0

    # Saving parts --------------------------------------------------------------------------

    def _save_parts(self, db, run_id: str, run: dict, before: dict | None):
        """Save part changes and remove the parts from the document.

        ``before`` holds the serialized rows that ``mutate(parts=True)`` loaded; a part the
        change function assigned without loading is compared with its stored rows. Unchanged
        rows stay, a grown list is appended to, and anything else is replaced.
        """
        version, keep = run['version'], self._replay_mark(db, run_id)
        for name in RUN_PARTS:
            value = run.pop(name, _MISSING)
            if value is _MISSING:
                continue
            if isinstance(value, _WriteOnlyPart):
                for operation, key, item in value._operations:
                    if operation == 'append':
                        self._append_rows(db, run_id, name, [item])
                    elif operation == 'set':
                        self._set_row(db, run_id, name, key, item, version, keep)
                    else:
                        self._retire(db, run_id, name, version, keep, key)
                continue
            old = before[name] if before is not None else self._stored_bodies(db, run_id, name)
            if name in _LISTS:
                items = list(value or [])
                kept = len(items) >= len(old) and all(canonical(item) == body for item, body in zip(items, old))
                if not kept:
                    self._retire(db, run_id, name, version, keep)
                self._append_rows(db, run_id, name, items[len(old):] if kept else items)
            elif name in _VALUES:
                if value:
                    self._set_row(db, run_id, name, '', value, version, keep)
                else:
                    self._retire(db, run_id, name, version, keep)
            else:
                entries = dict(value or {})
                for key, item in entries.items():
                    if old.get(key) != canonical(item):
                        self._set_row(db, run_id, name, key, item, version, keep)
                for key in old.keys() - entries.keys():
                    self._retire(db, run_id, name, version, keep, key)

    @staticmethod
    def _stored_bodies(db, run_id: str, name: str):
        rows = db.execute('SELECT key,body FROM run_parts WHERE run_id=? AND part=? ORDER BY sequence',
                          (run_id, name)).fetchall()
        if name in _LISTS:
            return [body for _, body in rows]
        if name in _VALUES:
            return rows[0][1] if rows else None
        return dict(rows)

    @staticmethod
    def _append_rows(db, run_id: str, name: str, items):
        db.executemany('INSERT INTO run_parts(run_id,part,key,body) VALUES(?,?,?,?)',
                       [(run_id, name, uuid.uuid4().hex, canonical(item)) for item in items])

    @classmethod
    def _set_row(cls, db, run_id: str, name: str, key: str, value, version: int, keep: int):
        body = canonical(value)
        existing = db.execute('SELECT body FROM run_parts WHERE run_id=? AND part=? AND key=?',
                              (run_id, name, key)).fetchone()
        if existing is not None:
            if existing[0] == body:
                return
            cls._retire(db, run_id, name, version, keep, key)
        db.execute('INSERT INTO run_parts(run_id,part,key,body) VALUES(?,?,?,?)', (run_id, name, key, body))

    @staticmethod
    def _retire(db, run_id: str, name: str, version: int, keep: int, key: str | None = None):
        """Remove a part's rows (or one entry) at ``version``. Rows up to position ``keep``
        are included in a saved command response and move to the history instead."""
        where, params = 'run_id=? AND part=?', [run_id, name]
        if key is not None:
            where, params = where + ' AND key=?', [*params, key]
        if keep:
            db.execute('INSERT INTO run_part_history(sequence,run_id,part,key,body,retired_at) '
                       f'SELECT sequence,run_id,part,key,body,? FROM run_parts WHERE {where} AND sequence<=?',
                       [version, *params, keep])
        db.execute(f'DELETE FROM run_parts WHERE {where}', params)
