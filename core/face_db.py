# [FILE: core/face_db.py]
import os
import sqlite3
import threading
import numpy as np
from core.logger import get_logger

logger = get_logger(__name__)


class FaceDB:
    """SQLite-backed face recognition database.

    Stores face encodings, display names, and per-video appearance records.
    Thread-safe: each thread gets its own SQLite connection (WAL mode,
    busy_timeout=5000).  A global ``_lock`` serializes read-modify-write
    sequences so that concurrent workers never lose updates.

    On first initialization, if legacy ``encodings.pkl`` / ``names.json``
    files exist they are imported into SQLite and then deleted.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, project_path=None):
        if cls._instance is None:
            cls._instance = super(FaceDB, cls).__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self, project_path=None):
        if self.initialized:
            return
        if project_path is None:
            return

        self.project_path = project_path
        self.db_dir = os.path.join(project_path, "_cyne_db", "faces")
        os.makedirs(self.db_dir, exist_ok=True)

        self.sqlite_path = os.path.join(self.db_dir, "faces.db")

        # Thread-local storage for connections
        self._local = threading.local()
        self._connections = []
        self._conn_lock = threading.Lock()

        self._init_schema()
        self._migrate_legacy()

        # In-memory caches (populated from SQLite)
        self.known_encodings = []
        self.known_ids = []
        self.id_to_name = {}

        self._load_cache()
        self.initialized = True

    # ------------------------------------------------------------------
    # SQLite helpers
    # ------------------------------------------------------------------

    def _get_conn(self):
        """Return a thread-local SQLite connection with WAL mode."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.sqlite_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.conn = conn
            with self._conn_lock:
                self._connections.append(conn)
        return self._local.conn

    def _init_schema(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS face_encodings (
                person_id TEXT NOT NULL,
                encoding  BLOB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS face_names (
                person_id    TEXT PRIMARY KEY,
                display_name TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS face_appearances (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                person_id  TEXT NOT NULL,
                video_path TEXT NOT NULL,
                timestamp  REAL DEFAULT 0,
                confidence REAL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_appearances_person
                ON face_appearances(person_id);
            CREATE INDEX IF NOT EXISTS idx_appearances_video
                ON face_appearances(video_path);
        """)
        conn.commit()

    # ------------------------------------------------------------------
    # Legacy migration  (pickle / json  →  SQLite)
    # ------------------------------------------------------------------

    def _migrate_legacy(self):
        """Import encodings.pkl + names.json into SQLite, then delete them."""
        legacy_enc = os.path.join(self.db_dir, "encodings.pkl")
        legacy_names = os.path.join(self.db_dir, "names.json")

        if not os.path.exists(legacy_enc) and not os.path.exists(legacy_names):
            return

        logger.info("Migrating legacy face data (pickle/json) to SQLite...")
        conn = self._get_conn()

        # --- names.json ---
        id_to_name = {}
        if os.path.exists(legacy_names):
            try:
                import json
                with open(legacy_names, "r") as f:
                    id_to_name = json.load(f)
                for pid, name in id_to_name.items():
                    conn.execute(
                        "INSERT OR IGNORE INTO face_names (person_id, display_name) VALUES (?, ?)",
                        (pid, name),
                    )
            except Exception as e:
                logger.warning(f"Failed to migrate names.json: {e}")

        # --- encodings.pkl ---
        if os.path.exists(legacy_enc):
            try:
                import pickle
                with open(legacy_enc, "rb") as f:
                    data = pickle.load(f)
                ids = data.get("ids", [])
                encodings = data.get("encodings", [])
                for pid, enc in zip(ids, encodings):
                    enc_bytes = np.asarray(enc, dtype=np.float64).tobytes()
                    conn.execute(
                        "INSERT INTO face_encodings (person_id, encoding) VALUES (?, ?)",
                        (pid, enc_bytes),
                    )
                    # Ensure a name row exists
                    name = id_to_name.get(pid, pid)
                    conn.execute(
                        "INSERT OR IGNORE INTO face_names (person_id, display_name) VALUES (?, ?)",
                        (pid, name),
                    )
            except Exception as e:
                logger.warning(f"Failed to migrate encodings.pkl: {e}")

        conn.commit()

        # Remove legacy files
        for path in (legacy_enc, legacy_names):
            try:
                if os.path.exists(path):
                    os.remove(path)
                    logger.info(f"Deleted legacy file: {path}")
            except OSError as e:
                logger.warning(f"Could not delete {path}: {e}")

        logger.info("Legacy face data migration complete")

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _load_cache(self):
        """Populate in-memory caches from SQLite."""
        conn = self._get_conn()

        # Names
        rows = conn.execute("SELECT person_id, display_name FROM face_names").fetchall()
        self.id_to_name = {row["person_id"]: row["display_name"] for row in rows}

        # Encodings
        rows = conn.execute("SELECT person_id, encoding FROM face_encodings").fetchall()
        self.known_ids = []
        self.known_encodings = []
        for row in rows:
            self.known_ids.append(row["person_id"])
            self.known_encodings.append(
                np.frombuffer(row["encoding"], dtype=np.float64)
            )

    # Keep legacy alias so callers that called load() still work
    def load(self):
        with self._lock:
            self._load_cache()

    # ------------------------------------------------------------------
    # Public API  (same signatures as the old pickle-based FaceDB)
    # ------------------------------------------------------------------

    def find_match(self, embedding, threshold=0.6):
        """Find the closest face in the DB.

        Returns ``(person_id, distance)`` or ``(None, 100.0)``.
        """
        with self._lock:
            if not self.known_encodings:
                return None, 100.0

            try:
                known_matrix = np.array(self.known_encodings)
                dists = np.linalg.norm(known_matrix - embedding, axis=1)
                min_index = int(np.argmin(dists))
                min_dist = float(dists[min_index])

                if min_dist < threshold:
                    return self.known_ids[min_index], min_dist
            except Exception as e:
                print(f"Face Match Error: {e}")

            return None, 100.0

    def add_face(self, person_id, encoding):
        with self._lock:
            enc_bytes = np.asarray(encoding, dtype=np.float64).tobytes()
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO face_encodings (person_id, encoding) VALUES (?, ?)",
                (person_id, enc_bytes),
            )
            conn.execute(
                "INSERT OR REPLACE INTO face_names (person_id, display_name) VALUES (?, ?)",
                (person_id, person_id),
            )
            conn.commit()

            # Update cache
            self.known_ids.append(person_id)
            self.known_encodings.append(np.asarray(encoding, dtype=np.float64))
            self.id_to_name[person_id] = person_id

    def rename_person(self, person_id, new_name):
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "UPDATE face_names SET display_name = ? WHERE person_id = ?",
                (new_name, person_id),
            )
            conn.commit()

            if person_id in self.id_to_name:
                self.id_to_name[person_id] = new_name

    def remove_person(self, person_id):
        with self._lock:
            conn = self._get_conn()
            conn.execute("DELETE FROM face_encodings WHERE person_id = ?", (person_id,))
            conn.execute("DELETE FROM face_names WHERE person_id = ?", (person_id,))
            conn.execute("DELETE FROM face_appearances WHERE person_id = ?", (person_id,))
            conn.commit()

            # Update cache
            self.id_to_name.pop(person_id, None)
            new_ids = []
            new_encodings = []
            for pid, enc in zip(self.known_ids, self.known_encodings):
                if pid != person_id:
                    new_ids.append(pid)
                    new_encodings.append(enc)
            self.known_ids = new_ids
            self.known_encodings = new_encodings

    def get_name(self, person_id):
        return self.id_to_name.get(person_id, person_id)

    def get_next_id(self):
        with self._lock:
            return f"Person_{len(self.id_to_name) + 100}"

    # ------------------------------------------------------------------
    # New: face appearances (video-level tracking)
    # ------------------------------------------------------------------

    def add_appearance(self, person_id, video_path, timestamp=0.0, confidence=0.0):
        """Record that *person_id* was seen in *video_path* at *timestamp*."""
        with self._lock:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO face_appearances (person_id, video_path, timestamp, confidence) "
                "VALUES (?, ?, ?, ?)",
                (person_id, video_path, timestamp, confidence),
            )
            conn.commit()

    def get_appearances(self, person_id):
        """Return list of ``{video_path, timestamp, confidence}`` for a person."""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT video_path, timestamp, confidence FROM face_appearances "
                "WHERE person_id = ? ORDER BY video_path, timestamp",
                (person_id,),
            ).fetchall()
            return [
                {"video_path": r["video_path"], "timestamp": r["timestamp"], "confidence": r["confidence"]}
                for r in rows
            ]

    def get_appearances_for_video(self, video_path):
        """Return list of ``{person_id, timestamp, confidence}`` for a video."""
        with self._lock:
            conn = self._get_conn()
            rows = conn.execute(
                "SELECT person_id, timestamp, confidence FROM face_appearances "
                "WHERE video_path = ? ORDER BY timestamp",
                (video_path,),
            ).fetchall()
            return [
                {"person_id": r["person_id"], "timestamp": r["timestamp"], "confidence": r["confidence"]}
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self):
        """Close all thread-local SQLite connections."""
        with self._conn_lock:
            for conn in self._connections:
                try:
                    conn.close()
                except Exception:
                    pass
            self._connections.clear()
        self._local = threading.local()
