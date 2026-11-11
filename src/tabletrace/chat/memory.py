"""Memory for the conversational agent.

Two kinds, kept apart on purpose:

  SessionMemory  short-term, in process: the turns of one conversation and the table in focus. It lets a follow-up such
                 as "그럼 신과함께는?" be completed from the previous question and its evidence cell.
  UserMemory     long-term, SQLite: what a user asked the agent to keep (named tables, answer preferences) and the
                 questions they asked before. It survives the process when TABLETRACE_MEMORY_PATH names a file.

Nothing is stored about a user unless a user id is given, and DELETE /v1/users/{id}/memory removes all of it.
"""
from __future__ import annotations

import re
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field

USER_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
PREFS = {"answer_style": ("short", "evidence"), "default_corpus": ("ko_tables", "chem_docs")}


@dataclass
class Turn:
    index: int
    message: str                      # what the user typed
    intent: str
    question: str = ""                # what went to the pipeline after resolution ("" for memory actions)
    doc_id: str | None = None
    table_id: str | None = None
    status: str | None = None
    answer: str | None = None
    op: str | None = None
    evidence: list[list[int]] = field(default_factory=list)   # final evidence cells as [row, col]
    notes: list[str] = field(default_factory=list)            # what memory contributed to this turn
    text: str = ""                    # the reply shown to the user


class SessionMemory:
    def __init__(self, session_id: str, user_id: str | None, corpus: str, max_turns: int = 40) -> None:
        self.session_id, self.user_id, self.corpus = session_id, user_id, corpus
        self.turns: list[Turn] = []
        self.max_turns = max_turns
        self.touched = time.time()

    @property
    def focus(self) -> tuple[str | None, str | None]:
        """(doc_id, table_id) of the most recent turn that used a table."""
        for t in reversed(self.turns):
            if t.table_id:
                return t.doc_id, t.table_id
        return None, None

    def last_question(self) -> Turn | None:
        """The most recent turn that asked the pipeline something (memory actions are skipped)."""
        for t in reversed(self.turns):
            if t.intent == "ask" and t.question:
                return t
        return None

    def add(self, turn: Turn) -> None:
        self.turns.append(turn)
        del self.turns[: max(0, len(self.turns) - self.max_turns)]
        self.touched = time.time()

    def view(self) -> dict:
        doc_id, table_id = self.focus
        return {"session_id": self.session_id, "user_id": self.user_id, "corpus": self.corpus,
                "focus": {"doc_id": doc_id, "table_id": table_id}, "turns": [asdict(t) for t in self.turns]}


class SessionStore:
    """Sessions live in process memory: bounded in number and dropped after an idle period."""

    def __init__(self, max_sessions: int = 500, idle_s: float = 7200) -> None:
        self.max_sessions, self.idle_s = max_sessions, idle_s
        self._sessions: dict[str, SessionMemory] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str | None) -> SessionMemory | None:
        with self._lock:
            return self._sessions.get(session_id) if session_id else None

    def open(self, session_id: str | None, user_id: str | None, corpus: str) -> SessionMemory:
        with self._lock:
            now = time.time()
            for sid in [s for s, m in self._sessions.items() if now - m.touched > self.idle_s]:
                del self._sessions[sid]
            mem = self._sessions.get(session_id) if session_id else None
            if mem is None:
                if len(self._sessions) >= self.max_sessions:      # drop the least recently used conversation
                    del self._sessions[min(self._sessions, key=lambda s: self._sessions[s].touched)]
                mem = SessionMemory(session_id or uuid.uuid4().hex[:16], user_id, corpus)
                self._sessions[mem.session_id] = mem
            return mem


class UserMemory:
    """Long-term memory per user in SQLite: named tables, preferences, question history."""

    def __init__(self, path: str = "") -> None:
        self.path = path or ":memory:"
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS pins (user_id TEXT, name TEXT, doc_id TEXT, table_id TEXT, created REAL, PRIMARY KEY (user_id, name));
                CREATE TABLE IF NOT EXISTS prefs (user_id TEXT, key TEXT, value TEXT, updated REAL, PRIMARY KEY (user_id, key));
                CREATE TABLE IF NOT EXISTS history (user_id TEXT, session_id TEXT, question TEXT, answer TEXT, table_id TEXT, created REAL);
                CREATE INDEX IF NOT EXISTS history_user ON history (user_id, created);
            """)

    @staticmethod
    def check_user(user_id: str) -> str:
        if not USER_ID.match(user_id or ""):
            raise ValueError("user id must be 1-64 characters of letters, digits, '_', '.', '-'")
        return user_id

    # ---- named tables ------------------------------------------------------------------------
    def pin(self, user_id: str, name: str, doc_id: str | None, table_id: str) -> None:
        name = " ".join(name.split())[:40]
        if not name:
            raise ValueError("a pinned table needs a name")
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO pins VALUES (?, ?, ?, ?, ?)", (self.check_user(user_id), name, doc_id, table_id, time.time()))

    def unpin(self, user_id: str, name: str) -> bool:
        with self._lock, self._db:
            return self._db.execute("DELETE FROM pins WHERE user_id = ? AND name = ?", (self.check_user(user_id), name)).rowcount > 0

    def pins(self, user_id: str) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT name, doc_id, table_id FROM pins WHERE user_id = ? ORDER BY created", (self.check_user(user_id),)).fetchall()
        return [{"name": n, "doc_id": d, "table_id": t} for n, d, t in rows]

    def find_pin(self, user_id: str, name: str) -> dict | None:
        wanted = " ".join(name.split()).lower()
        return next((p for p in self.pins(user_id) if p["name"].lower() == wanted), None)

    # ---- preferences -------------------------------------------------------------------------
    def set_pref(self, user_id: str, key: str, value: str) -> None:
        if key not in PREFS or value not in PREFS[key]:
            raise ValueError(f"unknown preference {key}={value}; allowed: {PREFS}")
        with self._lock, self._db:
            self._db.execute("INSERT OR REPLACE INTO prefs VALUES (?, ?, ?, ?)", (self.check_user(user_id), key, value, time.time()))

    def prefs(self, user_id: str) -> dict:
        with self._lock:
            return dict(self._db.execute("SELECT key, value FROM prefs WHERE user_id = ?", (self.check_user(user_id),)).fetchall())

    # ---- history -----------------------------------------------------------------------------
    def log(self, user_id: str, session_id: str, question: str, answer: str | None, table_id: str | None) -> None:
        with self._lock, self._db:
            self._db.execute("INSERT INTO history VALUES (?, ?, ?, ?, ?, ?)", (self.check_user(user_id), session_id, question, answer, table_id, time.time()))

    def recent(self, user_id: str, n: int = 5, exclude_session: str | None = None) -> list[dict]:
        with self._lock:
            rows = self._db.execute("SELECT session_id, question, answer, table_id FROM history WHERE user_id = ? AND session_id IS NOT ? "
                                    "ORDER BY created DESC LIMIT ?", (self.check_user(user_id), exclude_session, n)).fetchall()
        return [{"session_id": s, "question": q, "answer": a, "table_id": t} for s, q, a, t in rows]

    # ---- everything --------------------------------------------------------------------------
    def view(self, user_id: str) -> dict:
        return {"user_id": self.check_user(user_id), "pins": self.pins(user_id), "prefs": self.prefs(user_id), "recent": self.recent(user_id, 10)}

    def forget(self, user_id: str) -> dict:
        self.check_user(user_id)
        with self._lock, self._db:
            return {t: self._db.execute(f"DELETE FROM {t} WHERE user_id = ?", (user_id,)).rowcount for t in ("pins", "prefs", "history")}
