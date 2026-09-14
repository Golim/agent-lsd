"""
Telemetry storage sinks.
"""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol

from deception_runtime.logging import StructuredLogger

logger = StructuredLogger(__name__)


class TelemetrySink(Protocol):
    """Protocol for telemetry sinks."""

    def emit(self, event: dict[str, Any]) -> None:
        """Emit an event to the sink."""
        ...

    def flush(self) -> None:
        """Flush any buffered events."""
        ...

    def close(self) -> None:
        """Close the sink and release resources."""
        ...


class NoOpSink:
    """Sink that does nothing (for when telemetry is disabled)."""

    def emit(self, event: dict[str, Any]) -> None:
        """No-op."""
        pass

    def flush(self) -> None:
        """No-op."""
        pass

    def close(self) -> None:
        """No-op."""
        pass


class JsonlFileSink:
    """
    Append-only JSONL file sink.

    Thread-safe with a single lock around file writes.
    """

    def __init__(self, path: str | Path, fsync: bool = False):
        """
        Initialize JSONL sink.

        Args:
            path: Path to JSONL file
            fsync: Whether to fsync after each write
        """
        self.path = Path(path)
        self.fsync = fsync
        self._lock = threading.Lock()

        # Create parent directory if needed
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Open file in append mode
        try:
            self._file = open(self.path, "a", encoding="utf-8")
            logger.info("JSONL sink initialized", path=str(self.path))
        except Exception as e:
            logger.error("Failed to open JSONL sink", path=str(self.path), error=str(e))
            raise

    def emit(self, event: dict[str, Any]) -> None:
        """Write event as JSONL line."""
        with self._lock:
            try:
                line = json.dumps(event, separators=(",", ":"))
                self._file.write(line + "\n")

                if self.fsync:
                    self._file.flush()
                    import os
                    os.fsync(self._file.fileno())
            except Exception as e:
                logger.error("Failed to write event to JSONL", error=str(e))

    def flush(self) -> None:
        """Flush buffered writes."""
        with self._lock:
            try:
                self._file.flush()
            except Exception as e:
                logger.error("Failed to flush JSONL sink", error=str(e))

    def close(self) -> None:
        """Close the file."""
        with self._lock:
            try:
                self._file.close()
                logger.info("JSONL sink closed", path=str(self.path))
            except Exception as e:
                logger.error("Failed to close JSONL sink", error=str(e))


class SqliteSink:
    """
    SQLite database sink.

    Thread-safe using SQLite's built-in connection per thread.
    """

    def __init__(self, db_path: str | Path):
        """
        Initialize SQLite sink.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._lock = threading.Lock()

        # Create parent directory if needed
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database schema
        self._init_db()

        logger.info("SQLite sink initialized", db_path=str(self.db_path))

    def _init_db(self) -> None:
        """Initialize database schema if not exists."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        try:
            cursor = conn.cursor()

            # Create events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    request_id TEXT NOT NULL,
                    challenge_id TEXT NOT NULL,
                    instance_id TEXT,
                    student_id TEXT,
                    route TEXT NOT NULL,
                    method TEXT NOT NULL,
                    status_code INTEGER,
                    user_agent TEXT,
                    remote_addr TEXT,
                    extra_json TEXT
                )
            """)

            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_challenge_timestamp
                ON events(challenge_id, timestamp)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_instance_timestamp
                ON events(instance_id, timestamp)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_event_type_timestamp
                ON events(event_type, timestamp)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_request_id
                ON events(request_id)
            """)

            conn.commit()
            logger.info("SQLite schema initialized")
        except Exception as e:
            logger.error("Failed to initialize SQLite schema", error=str(e))
            raise
        finally:
            conn.close()

    def emit(self, event: dict[str, Any]) -> None:
        """Insert event into database."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            try:
                cursor = conn.cursor()

                # Serialize extra as JSON
                extra_json = json.dumps(event.get("extra", {}))

                cursor.execute("""
                    INSERT INTO events (
                        timestamp, event_type, request_id, challenge_id,
                        instance_id, student_id, route, method,
                        status_code, user_agent, remote_addr, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.get("timestamp"),
                    event.get("event_type"),
                    event.get("request_id"),
                    event.get("challenge_id"),
                    event.get("instance_id"),
                    event.get("student_id"),
                    event.get("route"),
                    event.get("method"),
                    event.get("status_code"),
                    event.get("user_agent"),
                    event.get("remote_addr"),
                    extra_json,
                ))

                conn.commit()
            except Exception as e:
                logger.error("Failed to insert event into SQLite", error=str(e))
                conn.rollback()
            finally:
                conn.close()

    def flush(self) -> None:
        """No-op for SQLite (auto-commit)."""
        pass

    def close(self) -> None:
        """Close database connections."""
        # SQLite connections are per-thread, no global cleanup needed
        logger.info("SQLite sink closed")


def create_sink(sink_type: str, path: str, fsync: bool = False) -> TelemetrySink:
    """
    Create a telemetry sink.

    Args:
        sink_type: Type of sink ('jsonl' or 'sqlite')
        path: File path for the sink
        fsync: Whether to fsync after writes (JSONL only)

    Returns:
        TelemetrySink instance

    Raises:
        ValueError: If sink_type is unknown
    """
    if sink_type == "jsonl":
        return JsonlFileSink(path, fsync=fsync)
    elif sink_type == "sqlite":
        return SqliteSink(path)
    else:
        raise ValueError(f"Unknown sink type: {sink_type}")
