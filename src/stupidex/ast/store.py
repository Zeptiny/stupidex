import logging
import sqlite3
from pathlib import Path

from stupidex.ast.symbols import Symbol
from stupidex.config import AST_INDEX_DB, PROJECT_AST_DIR

logger = logging.getLogger(__name__)

_DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    file_path TEXT PRIMARY KEY,
    hash TEXT NOT NULL DEFAULT '',
    symbol_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    start_line INTEGER NOT NULL,
    start_column INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    end_column INTEGER NOT NULL,
    char_start INTEGER NOT NULL,
    char_end INTEGER NOT NULL,
    FOREIGN KEY (file_path) REFERENCES files(file_path)
);

CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class ASTStore:
    def __init__(self, project_path: str):
        self.project_path = project_path
        self.ast_dir = Path(project_path) / PROJECT_AST_DIR
        self.db_path = self.ast_dir / AST_INDEX_DB
        self._post_write_callbacks: list = []

    def _ensure_dir(self) -> None:
        self.ast_dir.mkdir(parents=True, exist_ok=True)

    def init_db(self) -> None:
        self._ensure_dir()
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.executescript(_DB_SCHEMA)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Corrupted symbols.db, rebuilding: %s", e)
            if self.db_path.exists():
                self.db_path.unlink()
            conn = sqlite3.connect(str(self.db_path))
            conn.executescript(_DB_SCHEMA)
            conn.commit()
            conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        self._ensure_dir()
        conn = None
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("SELECT 1 FROM files LIMIT 1")
            return conn
        except Exception as e:
            logger.error("Corrupted symbols.db, rebuilding: %s", e)
            if conn is not None:
                conn.close()
            if self.db_path.exists():
                self.db_path.unlink()
            conn = sqlite3.connect(str(self.db_path))
            conn.executescript(_DB_SCHEMA)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            return conn

    def upsert_file(
        self, file_path: str, file_hash: str, symbols: list[Symbol]
    ) -> None:
        conn = self._get_conn()
        try:
            conn.execute("DELETE FROM symbols WHERE file_path = ?", (file_path,))

            if symbols:
                symbol_data = [
                    (
                        file_path,
                        s.name,
                        s.type,
                        s.kind,
                        s.start_line,
                        s.start_column,
                        s.end_line,
                        s.end_column,
                        s.char_start,
                        s.char_end,
                    )
                    for s in symbols
                ]
                conn.executemany(
                    "INSERT INTO symbols "
                    "(file_path, name, type, kind, start_line, start_column, "
                    "end_line, end_column, char_start, char_end) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    symbol_data,
                )

            conn.execute(
                "INSERT OR REPLACE INTO files (file_path, hash, symbol_count) "
                "VALUES (?, ?, ?)",
                (file_path, file_hash, len(symbols)),
            )

            conn.commit()
        finally:
            conn.close()

    def get_symbols_by_name(
        self, name: str, type_filter: str = "both"
    ) -> list[dict]:
        conn = self._get_conn()
        try:
            if type_filter == "both":
                cursor = conn.execute(
                    "SELECT file_path, name, type, kind, start_line, start_column, "
                    "end_line, end_column, char_start, char_end "
                    "FROM symbols WHERE name = ?",
                    (name,),
                )
            else:
                cursor = conn.execute(
                    "SELECT file_path, name, type, kind, start_line, start_column, "
                    "end_line, end_column, char_start, char_end "
                    "FROM symbols WHERE name = ? AND type = ?",
                    (name, type_filter),
                )
            return [
                {
                    "file_path": row[0],
                    "name": row[1],
                    "type": row[2],
                    "kind": row[3],
                    "start_line": row[4],
                    "start_column": row[5],
                    "end_line": row[6],
                    "end_column": row[7],
                    "char_start": row[8],
                    "char_end": row[9],
                }
                for row in cursor.fetchall()
            ]
        finally:
            conn.close()

    def get_file_hash(self, file_path: str) -> str:
        if not self.db_path.exists():
            return ""
        conn = self._get_conn()
        try:
            row = conn.execute(
                "SELECT hash FROM files WHERE file_path = ?", (file_path,)
            ).fetchone()
            return row[0] if row else ""
        finally:
            conn.close()

    def get_all_file_hashes(self) -> dict[str, str]:
        if not self.db_path.exists():
            return {}
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT file_path, hash FROM files").fetchall()
            return {row[0]: row[1] for row in rows}
        finally:
            conn.close()

    def register_post_write_callback(self, callback) -> None:
        self._post_write_callbacks.append(callback)

    def clear(self) -> None:
        if self.db_path.exists():
            self.db_path.unlink()
