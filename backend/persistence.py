"""Persistence layer for conversations, messages, and response preferences."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


DEFAULT_APP_PERSISTENCE_DB_URL = "sqlite:///chat_state.db"


def get_app_persistence_db_url() -> str:
    configured_url = os.environ.get("APP_PERSISTENCE_DB_URL", "").strip()
    return configured_url or DEFAULT_APP_PERSISTENCE_DB_URL


def create_default_response_preferences() -> dict[str, Any]:
    return {
        "adjustment_feedback": [],
    }


def build_approved_style_notes(answer: str) -> str:
    trimmed = answer.strip()
    notes: list[str] = []

    if "[1]" in trimmed or "[2]" in trimmed or "[3]" in trimmed:
        notes.append("Keep citations close to the claims they support.")
    if "- " in trimmed:
        notes.append("Use short bullet points when they improve readability.")
    else:
        notes.append("Keep the structure direct and easy to scan.")
    if len(trimmed) <= 220:
        notes.append("Stay concise.")
    else:
        notes.append("Keep the explanation focused and avoid unnecessary detail.")

    return " ".join(notes)


class PersistenceStore:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.kind = self._detect_kind(db_url)
        self._sqlite_lock = threading.Lock()
        self._sqlite_connection: Optional[sqlite3.Connection] = None

        if self.kind == "sqlite":
            self._sqlite_connection = self._build_sqlite_connection(db_url)

        self.ensure_schema()

    @staticmethod
    def _detect_kind(db_url: str) -> str:
        normalized = db_url.strip().lower()
        if normalized.startswith("sqlite:///"):
            return "sqlite"
        if normalized.startswith("postgresql://") or normalized.startswith("postgres://"):
            return "postgres"
        raise ValueError(
            "APP_PERSISTENCE_DB_URL must start with sqlite:/// or postgresql://"
        )

    def _build_sqlite_connection(self, db_url: str) -> sqlite3.Connection:
        raw_path = db_url[len("sqlite:///") :]
        db_path = Path(raw_path)
        if not db_path.is_absolute():
            db_path = Path(__file__).resolve().parent.parent / db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)

        connection = sqlite3.connect(str(db_path), check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _connect_postgres(self):
        return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)

    def _normalize_sql(self, sql: str) -> str:
        if self.kind == "postgres":
            return sql.replace("?", "%s")
        return sql

    def _fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if self.kind == "sqlite":
            assert self._sqlite_connection is not None
            with self._sqlite_lock:
                cursor = self._sqlite_connection.execute(sql, params)
                rows = cursor.fetchall()
            return [dict(row) for row in rows]

        normalized_sql = self._normalize_sql(sql)
        with self._connect_postgres() as connection:
            with connection.cursor() as cursor:
                cursor.execute(normalized_sql, params)
                rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def _fetchone(
        self, sql: str, params: tuple[Any, ...] = ()
    ) -> Optional[dict[str, Any]]:
        rows = self._fetchall(sql, params)
        return rows[0] if rows else None

    def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        if self.kind == "sqlite":
            assert self._sqlite_connection is not None
            with self._sqlite_lock:
                self._sqlite_connection.execute(sql, params)
                self._sqlite_connection.commit()
            return

        normalized_sql = self._normalize_sql(sql)
        with self._connect_postgres() as connection:
            with connection.cursor() as cursor:
                cursor.execute(normalized_sql, params)
            connection.commit()

    def ensure_schema(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                client_id TEXT PRIMARY KEY,
                preferences_json TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                client_id TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                client_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                run_id TEXT,
                sources_json TEXT NOT NULL DEFAULT '[]',
                feedback_rating TEXT,
                feedback_comment TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_client_id
            ON conversations (client_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_position
            ON messages (conversation_id, position)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_messages_client_id
            ON messages (client_id)
            """,
        ]

        for statement in statements:
            self._execute(statement)

    def ensure_user_profile(self, client_id: str) -> None:
        self._execute(
            """
            INSERT INTO user_profiles (
                client_id,
                preferences_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (client_id) DO NOTHING
            """,
            (
                client_id,
                json.dumps(create_default_response_preferences(), ensure_ascii=False),
            ),
        )

    def get_response_preferences(self, client_id: str) -> dict[str, Any]:
        self.ensure_user_profile(client_id)
        row = self._fetchone(
            "SELECT preferences_json FROM user_profiles WHERE client_id = ?",
            (client_id,),
        )
        if row is None:
            return create_default_response_preferences()

        try:
            return json.loads(row["preferences_json"])
        except (TypeError, json.JSONDecodeError):
            return create_default_response_preferences()

    def save_response_preferences(
        self, client_id: str, preferences: dict[str, Any]
    ) -> dict[str, Any]:
        payload = json.dumps(preferences, ensure_ascii=False)
        self._execute(
            """
            INSERT INTO user_profiles (
                client_id,
                preferences_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (client_id) DO UPDATE SET
                preferences_json = excluded.preferences_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (client_id, payload),
        )
        return preferences

    def clear_response_preferences(self, client_id: str) -> dict[str, Any]:
        preferences = create_default_response_preferences()
        return self.save_response_preferences(client_id, preferences)

    def ensure_conversation(self, conversation_id: str, client_id: str) -> None:
        self.ensure_user_profile(client_id)
        self._execute(
            """
            INSERT INTO conversations (
                conversation_id,
                client_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (conversation_id) DO UPDATE SET
                client_id = excluded.client_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (conversation_id, client_id),
        )

    def _next_message_position(self, conversation_id: str) -> int:
        row = self._fetchone(
            """
            SELECT COALESCE(MAX(position), 0) + 1 AS next_position
            FROM messages
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        )
        return int(row["next_position"]) if row is not None else 1

    def create_message(
        self,
        *,
        message_id: str,
        conversation_id: str,
        client_id: str,
        role: str,
        content: str,
        run_id: Optional[str] = None,
        sources: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        self.ensure_conversation(conversation_id, client_id)
        position = self._next_message_position(conversation_id)
        serialized_sources = json.dumps(sources or [], ensure_ascii=False)

        self._execute(
            """
            INSERT INTO messages (
                message_id,
                conversation_id,
                client_id,
                position,
                role,
                content,
                run_id,
                sources_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                message_id,
                conversation_id,
                client_id,
                position,
                role,
                content,
                run_id,
                serialized_sources,
            ),
        )

        return self.get_message(message_id)

    def get_message(self, message_id: str) -> dict[str, Any]:
        row = self._fetchone(
            """
            SELECT
                message_id,
                conversation_id,
                client_id,
                position,
                role,
                content,
                run_id,
                sources_json,
                feedback_rating,
                feedback_comment,
                created_at
            FROM messages
            WHERE message_id = ?
            """,
            (message_id,),
        )
        if row is None:
            raise KeyError(message_id)
        return self._deserialize_message_row(row)

    def list_conversation_messages(self, conversation_id: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            """
            SELECT
                message_id,
                conversation_id,
                client_id,
                position,
                role,
                content,
                run_id,
                sources_json,
                feedback_rating,
                feedback_comment,
                created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY position ASC
            """,
            (conversation_id,),
        )
        return [self._deserialize_message_row(row) for row in rows]

    def _deserialize_message_row(self, row: dict[str, Any]) -> dict[str, Any]:
        raw_sources = row.get("sources_json") or "[]"
        try:
            sources = json.loads(raw_sources)
        except (TypeError, json.JSONDecodeError):
            sources = []

        feedback_rating = row.get("feedback_rating")
        feedback_comment = row.get("feedback_comment")
        feedback = None
        if feedback_rating:
            feedback = {
                "rating": feedback_rating,
            }
            if feedback_comment:
                feedback["comment"] = feedback_comment

        return {
            "id": row["message_id"],
            "conversationId": row["conversation_id"],
            "clientId": row["client_id"],
            "role": row["role"],
            "rawContent": row["content"],
            "runId": row.get("run_id"),
            "sources": sources,
            "feedback": feedback,
            "status": "complete",
            "createdAt": row.get("created_at"),
        }

    def build_chat_history(self, conversation_id: str) -> list[dict[str, str]]:
        messages = self.list_conversation_messages(conversation_id)
        chat_history: list[dict[str, str]] = []
        pending_human: Optional[str] = None

        for message in messages:
            if message["role"] == "user":
                pending_human = message["rawContent"]
                continue
            if message["role"] == "assistant" and pending_human is not None:
                chat_history.append(
                    {
                        "human": pending_human,
                        "ai": message["rawContent"],
                    }
                )
                pending_human = None

        return chat_history

    def apply_feedback(
        self,
        *,
        client_id: str,
        message_id: str,
        rating: str,
        comment: Optional[str],
    ) -> dict[str, Any]:
        message = self.get_message(message_id)
        if message["clientId"] != client_id:
            raise ValueError("Message does not belong to the provided client")
        if message["role"] != "assistant":
            raise ValueError("Feedback can only be attached to assistant messages")

        trimmed_comment = (comment or "").strip() or None
        self._execute(
            """
            UPDATE messages
            SET feedback_rating = ?, feedback_comment = ?
            WHERE message_id = ?
            """,
            (rating, trimmed_comment, message_id),
        )

        preferences = self.get_response_preferences(client_id)
        if rating == "good":
            preferences["approved_answer"] = {
                "answer": message["rawContent"],
                "notes": build_approved_style_notes(message["rawContent"]),
            }
        elif rating == "bad":
            adjustment_feedback = preferences.get("adjustment_feedback") or []
            adjustment_feedback.append(
                {
                    "comment": trimmed_comment or "The user rejected this answer.",
                    "answer": message["rawContent"],
                }
            )
            preferences["adjustment_feedback"] = adjustment_feedback[-5:]

        return self.save_response_preferences(client_id, preferences)


@lru_cache(maxsize=1)
def get_persistence_store() -> PersistenceStore:
    return PersistenceStore(get_app_persistence_db_url())
