"""
title: Prune
author: classic298
author_url: https://github.com/Classic298
funding_url: https://github.com/Classic298/prune-open-webui
version: 0.10.6
required_open_webui_version: 0.10.2
description: Automatic, throttled database and storage cleanup. Configure retention via Valves (0 = disabled); pruning runs event-driven on one worker only, slowly, so a live instance stays responsive.
"""
# Single-file Event function port of https://github.com/Classic298/prune-open-webui.
# Sections below are copied from that repo (prune_models / prune_core /
# prune_operations / standalone_prune) with the import shim replaced by direct
# open_webui imports, plus throttling (_pace), the event-routing layer and the
# session-gated manual admin UI at the bottom. Automatic pruning is configured
# entirely via Valves; the UI (route_prefix, default /prune) is for manual runs.

import asyncio
from pydantic import BaseModel, Field
from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

# Global throttles, set from the valves on every event dispatch. Deletion sites
# await _pace(), row scans await _scan_pace(), so a pass trickles instead of
# saturating the database or the event loop on a live instance. Manual runs may
# set the run_* overrides for their duration.
_PACE = {
    "rows_per_second": 50,
    "scan_rows_per_second": 0,
    "run_rows_per_second": None,
    "run_scan_rows_per_second": None,
}


async def _pace(rows: int = 1):
    rate = _PACE["run_rows_per_second"]
    if rate is None:
        rate = _PACE["rows_per_second"]
    if rate > 0:
        await asyncio.sleep(min(rows / rate, 30.0))


async def _scan_pace(rows: int = 1):
    # Read-side throttle; at minimum yields the loop so other requests run
    rate = _PACE["run_scan_rows_per_second"]
    if rate is None:
        rate = _PACE["scan_rows_per_second"]
    if rate > 0:
        await asyncio.sleep(min(rows / rate, 30.0))
    else:
        await asyncio.sleep(0)


# Live progress of the current pass, read by the manual UI. Plain dict writes
# only, so vector/storage worker threads can update it too.
_PROGRESS = {"active": False}


def _prog_begin(mode):
    _PROGRESS.update(
        active=True,
        mode=mode,
        stage="Starting",
        stages_done=0,
        done=0,
        total=None,
        started_at=int(time.time()),
    )


def _prog_stage(stage, total=None):
    if not _PROGRESS.get("active"):
        return
    _PROGRESS.update(
        stage=stage,
        stages_done=_PROGRESS.get("stages_done", 0) + 1,
        done=0,
        total=total,
    )


def _prog_tick(n=1, total=None):
    if not _PROGRESS.get("active"):
        return
    _PROGRESS["done"] = _PROGRESS.get("done", 0) + n
    if total is not None:
        _PROGRESS["total"] = total


def _prog_end():
    _PROGRESS["active"] = False



# ============================================================================
# Models (from prune_models.py)
# ============================================================================

from typing import Optional
from pydantic import BaseModel


class PruneDataForm(BaseModel):
    """
    Configuration form for prune operations.

    This model defines all the parameters that can be configured for a prune
    operation, including age-based deletion, orphaned data cleanup, and
    system optimization settings.
    """

    days: Optional[int] = None
    exempt_archived_chats: bool = True
    exempt_pinned_chats: bool = True
    exempt_chats_in_folders: bool = False
    # Retention policy: delete live, owned, in-use KBs by age (DANGEROUS, opt-in)
    delete_knowledge_bases_older_than_days: Optional[int] = None
    knowledge_bases_age_field: str = "created_at"  # 'created_at' or 'updated_at'
    delete_orphaned_chats: bool = True
    # Shared exemptions: keep orphaned resources that a LIVING principal can
    # still access (live user grant, existing group grant, or public '*').
    exempt_shared_orphaned_knowledge_bases: bool = True
    exempt_shared_orphaned_models: bool = True
    exempt_shared_orphaned_prompts: bool = True
    exempt_shared_orphaned_tools: bool = True
    exempt_shared_orphaned_notes: bool = True
    exempt_shared_orphaned_skills: bool = True
    # Skip files younger than this in orphan sweeps: upload and first
    # reference (message send / KB add) are separate requests.
    orphan_file_grace_hours: int = 24
    delete_orphaned_tools: bool = False
    delete_orphaned_functions: bool = False
    delete_orphaned_prompts: bool = True
    delete_orphaned_knowledge_bases: bool = True
    delete_orphaned_kb_metadata: bool = True
    delete_orphaned_memories: bool = True
    delete_orphaned_models: bool = True
    delete_orphaned_notes: bool = True
    delete_orphaned_skills: bool = False
    delete_orphaned_folders: bool = True
    delete_orphaned_chat_messages: bool = True
    delete_orphaned_automations: bool = True
    # Channel pruning
    channel_message_max_age_days: Optional[int] = (
        None  # age-based channel message cleanup; opt-in
    )
    exempt_pinned_channel_messages: bool = True
    delete_orphaned_channels: bool = (
        False  # channels owned by deleted users (shared infra — off by default)
    )
    delete_orphaned_channel_messages: bool = (
        True  # messages whose channel no longer exists
    )
    audio_cache_max_age_days: Optional[int] = (
        None  # Changed from 30 to None - must be explicitly enabled
    )
    delete_inactive_users_days: Optional[int] = None
    exempt_admin_users: bool = True
    exempt_pending_users: bool = True
    run_vacuum: bool = False
    dry_run: bool = True


class PrunePreviewResult(BaseModel):
    """
    Preview result showing counts of items that would be deleted.

    This model is returned during dry-run operations to show the user
    exactly what will be deleted without making any changes.
    """

    inactive_users: int = 0
    old_chats: int = 0
    old_knowledge_bases: int = 0
    orphaned_chats: int = 0
    orphaned_files: int = 0
    orphaned_tools: int = 0
    orphaned_functions: int = 0
    orphaned_prompts: int = 0
    orphaned_knowledge_bases: int = 0
    orphaned_models: int = 0
    orphaned_notes: int = 0
    orphaned_skills: int = 0
    orphaned_folders: int = 0
    orphaned_uploads: int = 0
    orphaned_vector_collections: int = 0
    orphaned_kb_metadata: int = 0
    orphaned_memories: int = 0
    orphaned_chat_messages: int = 0
    orphaned_automations: int = 0
    orphaned_automation_runs: int = 0
    old_channel_messages: int = 0
    orphaned_channels: int = 0
    orphaned_channel_messages: int = 0
    audio_cache_files: int = 0

    def total_items(self) -> int:
        """Calculate total items that would be deleted."""
        return (
            self.inactive_users
            + self.old_chats
            + self.old_knowledge_bases
            + self.orphaned_chats
            + self.orphaned_files
            + self.orphaned_tools
            + self.orphaned_functions
            + self.orphaned_prompts
            + self.orphaned_knowledge_bases
            + self.orphaned_models
            + self.orphaned_notes
            + self.orphaned_skills
            + self.orphaned_folders
            + self.orphaned_uploads
            + self.orphaned_vector_collections
            + self.orphaned_kb_metadata
            + self.orphaned_memories
            + self.orphaned_chat_messages
            + self.orphaned_automations
            + self.orphaned_automation_runs
            + self.old_channel_messages
            + self.orphaned_channels
            + self.orphaned_channel_messages
            + self.audio_cache_files
        )

    def has_items(self) -> bool:
        """Check if any items would be deleted."""
        return self.total_items() > 0

    def get_summary_dict(self) -> dict:
        """Get summary as dictionary for display."""
        return {
            "Users": {
                "Inactive users": self.inactive_users,
            },
            "Chats": {
                "Old chats (age-based)": self.old_chats,
                "Orphaned chats": self.orphaned_chats,
                "Orphaned chat messages": self.orphaned_chat_messages,
            },
            "Automations": {
                "Orphaned automations": self.orphaned_automations,
                "Orphaned automation runs": self.orphaned_automation_runs,
            },
            "Channels": {
                "Old channel messages (age-based)": self.old_channel_messages,
                "Orphaned channels": self.orphaned_channels,
                "Orphaned channel messages": self.orphaned_channel_messages,
            },
            "Files": {
                "Orphaned file records": self.orphaned_files,
                "Orphaned upload files": self.orphaned_uploads,
            },
            "Workspace": {
                "Orphaned tools": self.orphaned_tools,
                "Orphaned functions": self.orphaned_functions,
                "Orphaned prompts": self.orphaned_prompts,
                "Orphaned knowledge bases": self.orphaned_knowledge_bases,
                "Old knowledge bases (age-based)": self.old_knowledge_bases,
                "Orphaned models": self.orphaned_models,
                "Orphaned notes": self.orphaned_notes,
                "Orphaned skills": self.orphaned_skills,
            },
            "Organization": {
                "Orphaned folders": self.orphaned_folders,
            },
            "Storage": {
                "Orphaned vector collections": self.orphaned_vector_collections,
                "Orphaned KB metadata embeddings": self.orphaned_kb_metadata,
                "Orphaned memories": self.orphaned_memories,
            },
            "Cache": {
                "Old audio cache files": self.audio_cache_files,
            },
        }


# ============================================================================
# Core: lock + vector database cleaners (from prune_core.py)
# ============================================================================

import logging
import json
import uuid
import os
import re
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator, Optional, Set, Tuple
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

# Optional database-specific imports
try:
    from sqlalchemy import text, bindparam
except ImportError:
    text = None

try:
    from pymilvus import utility, Collection
except ImportError:
    utility = None
    Collection = None

try:
    from qdrant_client.models import models as qdrant_models
except ImportError:
    qdrant_models = None

log = logging.getLogger(__name__)


class PruneLock:
    """
    Simple file-based locking mechanism to prevent concurrent prune operations.

    This uses a lock file with timestamp to prevent multiple admins from running
    prune simultaneously, which could cause race conditions and data corruption.
    """

    LOCK_FILE = None  # Will be set by init
    LOCK_TIMEOUT = timedelta(hours=2)  # Safety timeout

    @classmethod
    def init(cls, cache_dir: Path):
        """Initialize lock file path with cache directory."""
        cls.LOCK_FILE = Path(cache_dir) / ".prune.lock"

    @classmethod
    def acquire(cls) -> bool:
        """
        Try to acquire the lock. Returns True if acquired, False if already locked.

        If lock file exists but is stale (older than timeout), automatically
        removes it and acquires a new lock.
        """
        if cls.LOCK_FILE is None:
            raise RuntimeError(
                "PruneLock not initialized. Call PruneLock.init() first."
            )

        try:
            # Check if lock file exists
            if cls.LOCK_FILE.exists():
                # Read lock file to check if it's stale
                try:
                    with open(cls.LOCK_FILE, "r") as f:
                        lock_data = json.load(f)
                        lock_time = datetime.fromisoformat(lock_data["timestamp"])
                        operation_id = lock_data.get("operation_id", "unknown")

                        # Check if lock is stale
                        if datetime.utcnow() - lock_time > cls.LOCK_TIMEOUT:
                            log.warning(
                                f"Found stale lock from {lock_time} (operation {operation_id}), removing"
                            )
                            cls.LOCK_FILE.unlink()
                        else:
                            # Lock is still valid
                            log.warning(
                                f"Prune operation already in progress (started {lock_time}, operation {operation_id})"
                            )
                            return False
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    # Corrupt lock file, remove it
                    log.warning(f"Found corrupt lock file, removing: {e}")
                    cls.LOCK_FILE.unlink()

            # Create lock file
            operation_id = str(uuid.uuid4())[:8]
            lock_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "operation_id": operation_id,
                "pid": os.getpid(),
            }

            # Ensure parent directory exists
            cls.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

            with open(cls.LOCK_FILE, "w") as f:
                json.dump(lock_data, f)

            log.info(f"Acquired prune lock (operation {operation_id})")
            return True

        except Exception as e:
            log.error(f"Error acquiring prune lock: {e}")
            return False

    @classmethod
    def release(cls) -> None:
        """Release the lock by removing the lock file."""
        if cls.LOCK_FILE is None:
            return

        try:
            if cls.LOCK_FILE.exists():
                cls.LOCK_FILE.unlink()
                log.info("Released prune lock")
        except Exception as e:
            log.error(f"Error releasing prune lock: {e}")


UUID_PATTERN = re.compile(
    r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$"
)

# Any UUID-shaped substring. JSON columns are scanned as raw text and the
# matches intersected with the real file ids: a strict superset of the old
# per-field dict walk (id/file_id/fileId/file_ids/fileIds/url/src), an order
# of magnitude cheaper than json-decoding every row, and any overmatch only
# PRESERVES a file, never deletes one.
UUID_ANYWHERE_PATTERN = re.compile(
    r"[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}"
)


def collect_file_ids_from_text(text_val, out: Set[str], valid_ids: Set[str], odd_ids=()):
    """Collect referenced file ids from a JSON column's raw text."""
    if not text_val:
        return
    if isinstance(text_val, (bytes, bytearray)):
        text_val = text_val.decode("utf-8", "ignore")  # some drivers CAST json to bytes
    elif not isinstance(text_val, str):
        text_val = str(text_val)
    out.update(valid_ids.intersection(UUID_ANYWHERE_PATTERN.findall(text_val)))
    # A non-UUID id with special chars stores escaped in json, raw in jsonb; match
    # both forms. Over-matching only ever preserves a file.
    for odd_id in odd_ids:
        json_escaped_id = json.dumps(odd_id)[1:-1]
        if odd_id in text_val or json_escaped_id in text_val:
            out.add(odd_id)


def _collect_file_ids_from_texts(text_values, valid_ids, odd_ids=()):
    """Regex-scan a chunk of JSON column texts and return the referenced file
    ids. Runs in a worker thread (via asyncio.to_thread): the match work is
    CPU-bound and would otherwise starve the request loop on a live instance
    during a manual preview or run."""
    found: Set[str] = set()
    for text_val in text_values:
        try:
            collect_file_ids_from_text(text_val, found, valid_ids, odd_ids)
        except Exception as e:
            log.debug(f"Error scanning row text: {e}")
    return found


# Open WebUI stores one metadata embedding per knowledge base (its name +
# description) in this shared collection, used for semantic search across KBs.
# Separate from each KB's own {kb_id} collection that holds file/chunk vectors.
KNOWLEDGE_BASES_COLLECTION = "knowledge-bases"


class VectorDatabaseCleaner(ABC):
    """
    Abstract base class for vector database cleanup operations.

    This interface defines the contract that all vector database implementations
    must follow. Community contributors can implement support for new vector
    databases by extending this class.

    Supported operations:
    - Count orphaned collections (for dry-run preview)
    - Cleanup orphaned collections (actual deletion)
    - Delete individual collections by name
    """

    @abstractmethod
    def count_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> int:
        """
        Count how many orphaned vector collections would be deleted.

        Args:
            active_file_ids: Set of file IDs that are still referenced
            active_kb_ids: Set of knowledge base IDs that are still active
            active_user_ids: Set of user IDs that are still active (optional, for multitenancy)

        Returns:
            Number of orphaned collections that would be deleted
        """
        pass

    @abstractmethod
    def cleanup_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> tuple[int, Optional[str]]:
        """
        Actually delete orphaned vector collections.

        Args:
            active_file_ids: Set of file IDs that are still referenced
            active_kb_ids: Set of knowledge base IDs that are still active
            active_user_ids: Set of user IDs that are still active (optional, for multitenancy)

        Returns:
            Tuple of (deleted_count, error_message)
            - deleted_count: Number of collections that were deleted
            - error_message: None on success, error description on failure
        """
        pass

    @abstractmethod
    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a specific vector collection by name.

        Args:
            collection_name: Name of the collection to delete

        Returns:
            True if deletion was successful, False otherwise
        """
        pass

    def iter_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Generator[Tuple[str, str], None, None]:
        """
        Yield (orphaned_id, context) for each orphaned vector item.

        Used by the export feature to list individual orphaned items.
        Default implementation yields nothing. Subclasses override to
        provide actual iteration.

        Args:
            active_file_ids: Set of file IDs that are still referenced
            active_kb_ids: Set of knowledge base IDs that are still active
            active_user_ids: Set of user IDs that are still active

        Yields:
            (orphaned_id, context_string) — e.g. ("file-abc-123", "chromadb")
        """
        return
        yield  # pragma: no cover — makes this a generator

    # ── Knowledge base metadata embeddings (shared 'knowledge-bases' collection) ──
    #
    # These default implementations work for any backend whose client follows
    # Open WebUI's unified VectorDBBase interface (get/delete/has_collection),
    # so individual cleaners do not need to override them. Backends without a
    # client (e.g. NoOp) fall through to a safe no-op via getattr.

    def _kb_metadata_ids(self) -> Optional[Set[str]]:
        """Return the KB ids present in the shared metadata collection.

        Returns None when the collection or client is unavailable (so callers
        can distinguish "nothing to do" from "empty"). Reads only the ids —
        the same id-extraction as any other collection — so backends that
        override _collection_point_ids for an ids-only fetch (e.g. PGVector)
        avoid dragging every KB's text and vector over the wire. Best-effort.
        """
        return self._collection_point_ids(KNOWLEDGE_BASES_COLLECTION)

    def delete_kb_metadata(self, kb_ids) -> int:
        """Remove specific KB ids from the shared metadata collection.

        Mirrors Open WebUI's remove_knowledge_base_metadata_embedding. Used when
        a KB is deleted (by age or as orphaned) so no ghost remains in KB search.
        Best-effort; returns the number of ids requested for deletion.
        """
        client = getattr(self, "vector_db_client", None)
        ids = [str(i) for i in (kb_ids or []) if i]
        if client is None or not ids:
            return 0
        try:
            if not client.has_collection(KNOWLEDGE_BASES_COLLECTION):
                return 0
            client.delete(collection_name=KNOWLEDGE_BASES_COLLECTION, ids=ids)
            return len(ids)
        except Exception as e:
            log.debug(f"Failed to delete KB metadata embeddings: {e}")
            return 0

    def count_orphaned_kb_metadata(self, active_kb_ids: Set[str]) -> int:
        """Count KB metadata entries whose knowledge base no longer exists."""
        present = self._kb_metadata_ids()
        if not present:
            return 0
        return sum(1 for kb_id in present if kb_id not in active_kb_ids)

    def cleanup_orphaned_kb_metadata(self, active_kb_ids: Set[str]) -> int:
        """Delete KB metadata entries whose knowledge base no longer exists."""
        present = self._kb_metadata_ids()
        if not present:
            return 0
        orphaned = [kb_id for kb_id in present if kb_id not in active_kb_ids]
        if not orphaned:
            return 0
        deleted = self.delete_kb_metadata(orphaned)
        if deleted:
            log.info(f"Deleted {deleted} orphaned knowledge base metadata embeddings")
        return deleted

    def iter_orphaned_kb_metadata(
        self, active_kb_ids: Set[str]
    ) -> Generator[Tuple[str, str], None, None]:
        """Yield (kb_id, context) for each orphaned KB metadata entry."""
        present = self._kb_metadata_ids() or set()
        for kb_id in present:
            if kb_id not in active_kb_ids:
                yield (kb_id, KNOWLEDGE_BASES_COLLECTION)

    # ── Memories (per-user 'user-memory-{uid}' collections) ──
    #
    # Open WebUI stores one vector point per memory, keyed by memory.id. When a
    # user deletes an individual memory the point can be left behind, so these
    # methods reconcile each active user's memory collection against the memory
    # ids still in the database. Generic over the unified client; NoOp-safe.

    def _collection_point_ids(self, collection_name: str) -> Optional[Set[str]]:
        """Return the point ids present in a collection, or None if unavailable."""
        client = getattr(self, "vector_db_client", None)
        if client is None:
            return None
        try:
            if not client.has_collection(collection_name):
                return None
            result = client.get(collection_name)
        except Exception as e:
            log.debug(f"Could not read collection {collection_name}: {e}")
            return None

        ids: Set[str] = set()
        raw = getattr(result, "ids", None) if result is not None else None
        for entry in raw or []:
            if isinstance(entry, (list, tuple)):
                ids.update(str(i) for i in entry if i)
            elif entry:
                ids.add(str(entry))
        return ids

    # How many per-user memory collections to probe concurrently when no bulk
    # path exists. Each probe is an independent, blocking round trip to the
    # vector store, so a small thread pool collapses N sequential network waits
    # into roughly N/pool_size — this is what makes "Reconciling memory
    # embeddings" crawl at one user per round trip on large installs. Backends
    # whose client is not safe to call from multiple threads (e.g. PGVector's
    # shared SQLAlchemy session) set this to 1 to stay sequential.
    _MEMORY_PROBE_WORKERS = 8

    def _present_memory_ids_by_user(
        self, uids: "list"
    ) -> Optional[dict]:
        """Bulk-fetch {uid: {present point id, ...}} for user memory collections.

        Returns None when the backend has no bulk path, signalling the caller to
        probe each collection individually. Backends that can enumerate every
        memory point in a single query (e.g. PGVector) override this to avoid
        the per-user round trips that make reconciliation crawl. The point ids
        returned MUST be in the same id space as the generic client's get()
        (i.e. the resource ids the database rows are keyed by), so counts and
        deletions stay correct.
        """
        return None

    def _iter_present_memory_ids(
        self, uids, tick: bool = True
    ) -> Generator[Tuple[str, Set[str]], None, None]:
        """Yield (uid, present_point_ids) for each user's memory collection.

        Uses the backend bulk path when available; otherwise fans the
        independent per-user probes out across a small thread pool so one slow
        round trip does not stall the rest. Progress is ticked once per user
        (from the consuming thread) unless ``tick`` is False.
        """
        uid_list = [str(u) for u in uids]
        if not uid_list:
            return

        bulk = self._present_memory_ids_by_user(uid_list)
        if bulk is not None:
            for uid in uid_list:
                if tick:
                    _prog_tick()
                yield uid, (bulk.get(uid) or set())
            return

        def _probe(uid: str) -> Tuple[str, Set[str]]:
            return uid, (self._collection_point_ids(f"user-memory-{uid}") or set())

        workers = max(1, min(self._MEMORY_PROBE_WORKERS, len(uid_list)))
        if workers == 1:
            for uid in uid_list:
                if tick:
                    _prog_tick()
                yield _probe(uid)
            return

        # ThreadPoolExecutor.map preserves input order and yields each result as
        # it becomes ready, so progress advances smoothly while many probes run
        # concurrently underneath.
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for uid, present in pool.map(_probe, uid_list):
                if tick:
                    _prog_tick()
                yield uid, present

    def count_orphaned_memories(self, valid_ids_by_user: dict) -> int:
        """Count memories whose database row no longer exists, per active user."""
        valid_ids_by_user = valid_ids_by_user or {}
        total = 0
        for uid, present in self._iter_present_memory_ids(valid_ids_by_user.keys()):
            if not present:
                continue
            valid = valid_ids_by_user.get(uid) or set()
            total += sum(1 for pid in present if pid not in valid)
        return total

    def cleanup_orphaned_memories(self, valid_ids_by_user: dict) -> int:
        """Delete memories whose database row no longer exists, per active user."""
        client = getattr(self, "vector_db_client", None)
        if client is None:
            return 0
        valid_ids_by_user = valid_ids_by_user or {}
        deleted = 0
        for uid, present in self._iter_present_memory_ids(valid_ids_by_user.keys()):
            if not present:
                continue
            valid = valid_ids_by_user.get(uid) or set()
            orphans = [pid for pid in present if pid not in valid]
            if not orphans:
                continue
            collection = f"user-memory-{uid}"
            try:
                client.delete(collection_name=collection, ids=orphans)
                deleted += len(orphans)
            except Exception as e:
                log.debug(f"Failed to delete orphaned memories for {uid}: {e}")
        if deleted:
            log.info(f"Deleted {deleted} orphaned memories")
        return deleted

    def iter_orphaned_memories(
        self, valid_ids_by_user: dict
    ) -> Generator[Tuple[str, str], None, None]:
        """Yield (point_id, context) for each orphaned memory."""
        valid_ids_by_user = valid_ids_by_user or {}
        # Export listing, not the progress-tracked prune stage: don't tick.
        for uid, present in self._iter_present_memory_ids(
            valid_ids_by_user.keys(), tick=False
        ):
            valid = valid_ids_by_user.get(uid) or set()
            for pid in present:
                if pid not in valid:
                    yield (pid, f"user-memory-{uid}")


class ChromaDatabaseCleaner(VectorDatabaseCleaner):
    """
    ChromaDB-specific implementation of vector database cleanup.

    Handles ChromaDB's specific storage structure including:
    - SQLite metadata database (chroma.sqlite3)
    - Physical vector storage directories
    - Collection name to UUID mapping
    - Segment-based storage architecture
    """

    def __init__(self, vector_db_client, cache_dir: Path):
        """Initialize ChromaDB cleaner with paths."""
        self.vector_db_client = vector_db_client
        self.vector_dir = Path(cache_dir).parent / "vector_db"
        self.chroma_db_path = self.vector_dir / "chroma.sqlite3"

    def count_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> int:
        """Count orphaned ChromaDB collections for preview."""
        if not self.chroma_db_path.exists():
            return 0

        expected_collections = self._build_expected_collections(
            active_file_ids, active_kb_ids, active_user_ids
        )
        uuid_to_collection = self._get_collection_mappings()

        count = 0
        try:
            for collection_dir in self.vector_dir.iterdir():
                if not collection_dir.is_dir() or collection_dir.name.startswith("."):
                    continue

                dir_uuid = collection_dir.name
                collection_name = uuid_to_collection.get(dir_uuid)

                if (
                    collection_name is None
                    or collection_name not in expected_collections
                ):
                    count += 1
        except Exception as e:
            log.debug(f"Error counting orphaned ChromaDB collections: {e}")

        return count

    def iter_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Generator[Tuple[str, str], None, None]:
        """Yield (collection_name, context) for each orphaned ChromaDB collection."""
        if not self.chroma_db_path.exists():
            return

        expected_collections = self._build_expected_collections(
            active_file_ids, active_kb_ids, active_user_ids
        )
        uuid_to_collection = self._get_collection_mappings()

        try:
            for collection_dir in self.vector_dir.iterdir():
                if not collection_dir.is_dir() or collection_dir.name.startswith("."):
                    continue

                dir_uuid = collection_dir.name
                collection_name = uuid_to_collection.get(dir_uuid)

                if (
                    collection_name is None
                    or collection_name not in expected_collections
                ):
                    yield (collection_name or dir_uuid, "chromadb")
        except Exception as e:
            log.debug(f"Error iterating orphaned ChromaDB collections: {e}")

    def cleanup_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> tuple[int, Optional[str]]:
        """Actually delete orphaned ChromaDB collections and database records."""
        if not self.chroma_db_path.exists():
            return (0, None)

        expected_collections = self._build_expected_collections(
            active_file_ids, active_kb_ids, active_user_ids
        )
        uuid_to_collection = self._get_collection_mappings()

        deleted_count = 0
        errors = []

        # Delete mapped orphans through the client first: Chroma releases its
        # segment handles and removes the directory itself, which plain rmtree
        # cannot do on Windows (an open data_level0.bin locks the directory).
        client = getattr(self, "vector_db_client", None)
        if client is not None:
            for dir_uuid, collection_name in list(uuid_to_collection.items()):
                if collection_name in expected_collections:
                    continue
                try:
                    client.delete_collection(collection_name=collection_name)
                    deleted_count += 1
                    _prog_tick()
                    uuid_to_collection.pop(dir_uuid, None)
                    log.info(f"Deleted orphaned ChromaDB collection: {collection_name}")
                except Exception as e:
                    # Fall through to the directory sweep below
                    log.debug(f"Client delete failed for {collection_name}: {e}")

        # Then clean up orphaned database records
        try:
            deleted_count += self._cleanup_orphaned_database_records()
        except Exception as e:
            error_msg = f"ChromaDB database cleanup failed: {e}"
            log.error(error_msg)
            errors.append(error_msg)

        # Finally sweep leftover physical directories (strays with no mapping)
        def rmtree_or_defer(path, label):
            try:
                shutil.rmtree(path)
                log.info(f"Deleted orphaned ChromaDB directory: {label}")
                return 1
            except OSError as e:
                if isinstance(e, PermissionError) or getattr(e, "winerror", None) == 32:
                    # Windows: the running server still holds the mmap; the
                    # mapping is gone, a sweep after the next restart reclaims it
                    log.info(f"Deferred locked ChromaDB directory {label} (reclaimed after restart)")
                else:
                    errors.append(f"Failed to delete directory {label}: {e}")
                    log.error(errors[-1])
                return 0

        try:
            for collection_dir in self.vector_dir.iterdir():
                if not collection_dir.is_dir() or collection_dir.name.startswith("."):
                    continue

                _prog_tick()
                dir_uuid = collection_dir.name
                collection_name = uuid_to_collection.get(dir_uuid)

                # Delete if no corresponding collection name or collection is not expected
                if collection_name is None:
                    deleted_count += rmtree_or_defer(collection_dir, f"(no mapping) {dir_uuid}")
                elif collection_name not in expected_collections:
                    deleted_count += rmtree_or_defer(collection_dir, f"{collection_name} ({dir_uuid})")
                else:
                    log.debug(
                        f"Keeping expected collection: {collection_name} ({dir_uuid})"
                    )

        except Exception as e:
            error_msg = f"ChromaDB directory cleanup failed: {e}"
            log.error(error_msg)
            errors.append(error_msg)

        if deleted_count > 0:
            log.info(f"Deleted {deleted_count} orphaned ChromaDB collections")

        # Return error if any critical failures occurred
        if errors:
            return (deleted_count, "; ".join(errors))
        return (deleted_count, None)

    def delete_collection(self, collection_name: str) -> bool:
        """Delete a specific ChromaDB collection by name."""
        try:
            # Attempt to delete via ChromaDB client first
            try:
                self.vector_db_client.delete_collection(collection_name=collection_name)
                log.debug(f"Deleted ChromaDB collection via client: {collection_name}")
            except Exception as e:
                log.debug(
                    f"Collection {collection_name} may not exist in ChromaDB: {e}"
                )

            # Also clean up physical directory if it exists
            # Note: ChromaDB uses UUID directories, so we'd need to map collection name to UUID
            # For now, let the cleanup_orphaned_collections method handle physical cleanup
            return True

        except Exception as e:
            log.error(f"Error deleting ChromaDB collection {collection_name}: {e}")
            return False

    def _build_expected_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Set[str]:
        """Build set of collection names that should exist."""
        expected_collections = set()

        # File collections use "file-{id}" pattern
        for file_id in active_file_ids:
            expected_collections.add(f"file-{file_id}")

        # Knowledge base collections use the KB ID directly
        for kb_id in active_kb_ids:
            expected_collections.add(kb_id)

        # Preserve active users' memory collections (user-memory-{id}); only a
        # deleted user's memory collection should be treated as orphaned.
        for user_id in active_user_ids or set():
            expected_collections.add(f"user-memory-{user_id}")

        # Shared KB-metadata collection is pruned per-entry, never wholesale.
        expected_collections.add(KNOWLEDGE_BASES_COLLECTION)

        return expected_collections

    def _get_collection_mappings(self) -> dict:
        """Get mapping from ChromaDB directory UUID to collection name."""
        uuid_to_collection = {}

        try:
            with sqlite3.connect(str(self.chroma_db_path)) as conn:
                # First, get collection ID to name mapping
                collection_id_to_name = {}
                cursor = conn.execute("SELECT id, name FROM collections")
                for collection_id, collection_name in cursor.fetchall():
                    collection_id_to_name[collection_id] = collection_name

                # Then, get segment ID to collection mapping (segments are the directory UUIDs)
                cursor = conn.execute(
                    "SELECT id, collection FROM segments WHERE scope = 'VECTOR'"
                )
                for segment_id, collection_id in cursor.fetchall():
                    if collection_id in collection_id_to_name:
                        collection_name = collection_id_to_name[collection_id]
                        uuid_to_collection[segment_id] = collection_name

            log.debug(f"Found {len(uuid_to_collection)} ChromaDB vector segments")

        except Exception as e:
            log.error(f"Error reading ChromaDB metadata: {e}")

        return uuid_to_collection

    def _cleanup_orphaned_database_records(self) -> int:
        """
        Clean up orphaned database records that ChromaDB's delete_collection() method leaves behind.

        This is the key fix for the file size issue - ChromaDB doesn't properly cascade
        deletions, leaving orphaned embeddings, metadata, and FTS data that prevent
        VACUUM from reclaiming space.

        Returns:
            Number of orphaned records cleaned up
        """
        cleaned_records = 0

        try:
            with sqlite3.connect(str(self.chroma_db_path)) as conn:
                # Count orphaned records before cleanup
                cursor = conn.execute(
                    """
                    SELECT COUNT(*) FROM embeddings
                    WHERE segment_id NOT IN (SELECT id FROM segments)
                """
                )
                orphaned_embeddings = cursor.fetchone()[0]

                if orphaned_embeddings == 0:
                    log.debug("No orphaned ChromaDB embeddings found")
                    return 0

                log.info(
                    f"Cleaning up {orphaned_embeddings} orphaned ChromaDB embeddings and related data"
                )

                # Delete orphaned embedding_metadata first (child records)
                cursor = conn.execute(
                    """
                    DELETE FROM embedding_metadata
                    WHERE id IN (
                        SELECT id FROM embeddings
                        WHERE segment_id NOT IN (SELECT id FROM segments)
                    )
                """
                )
                metadata_deleted = cursor.rowcount
                cleaned_records += metadata_deleted

                # Delete orphaned embeddings
                cursor = conn.execute(
                    """
                    DELETE FROM embeddings
                    WHERE segment_id NOT IN (SELECT id FROM segments)
                """
                )
                embeddings_deleted = cursor.rowcount
                cleaned_records += embeddings_deleted

                # Selectively clean FTS while preserving active content
                fts_cleaned = self._cleanup_fts_selectively(conn)
                log.info(f"FTS cleanup: preserved {fts_cleaned} valid text entries")

                # Clean up orphaned collection and segment metadata
                cursor = conn.execute(
                    """
                    DELETE FROM collection_metadata
                    WHERE collection_id NOT IN (SELECT id FROM collections)
                """
                )
                collection_meta_deleted = cursor.rowcount
                cleaned_records += collection_meta_deleted

                cursor = conn.execute(
                    """
                    DELETE FROM segment_metadata
                    WHERE segment_id NOT IN (SELECT id FROM segments)
                """
                )
                segment_meta_deleted = cursor.rowcount
                cleaned_records += segment_meta_deleted

                # Clean up orphaned max_seq_id records
                cursor = conn.execute(
                    """
                    DELETE FROM max_seq_id
                    WHERE segment_id NOT IN (SELECT id FROM segments)
                """
                )
                seq_id_deleted = cursor.rowcount
                cleaned_records += seq_id_deleted

                # Force FTS index rebuild - this is crucial for VACUUM to work properly
                conn.execute(
                    "INSERT INTO embedding_fulltext_search(embedding_fulltext_search) VALUES('rebuild')"
                )

                # Commit changes
                conn.commit()

                log.info(
                    f"ChromaDB cleanup: {embeddings_deleted} embeddings, {metadata_deleted} metadata, "
                    f"{collection_meta_deleted} collection metadata, {segment_meta_deleted} segment metadata, "
                    f"{seq_id_deleted} sequence IDs"
                )

                # Log database size before VACUUM for diagnostic purposes
                db_size_mb = self.chroma_db_path.stat().st_size / (1024 * 1024)
                log.info(
                    f"ChromaDB size after cleanup, before VACUUM: {db_size_mb:.1f}MB (VACUUM needed to reclaim space)"
                )

        except Exception as e:
            log.error(f"Error cleaning orphaned ChromaDB database records: {e}")
            raise

        return cleaned_records

    def _cleanup_fts_selectively(self, conn) -> int:
        """
        Selectively clean FTS content with atomic operations, preserving only data from active embeddings.

        This method prevents destroying valid search data by:
        1. Creating and validating temporary table with valid content
        2. Using atomic transactions for DELETE/INSERT operations
        3. Rolling back on failure to preserve existing data
        4. Conservative fallback: skip FTS cleanup if validation fails

        Returns:
            Number of valid FTS entries preserved, or -1 if FTS cleanup was skipped
        """
        try:
            # Step 1: Create temporary table with valid content
            conn.execute(
                """
                CREATE TEMPORARY TABLE temp_valid_fts AS
                SELECT DISTINCT em.string_value
                FROM embedding_metadata em
                JOIN embeddings e ON em.id = e.id
                JOIN segments s ON e.segment_id = s.id
                WHERE em.string_value IS NOT NULL
                  AND em.string_value != ''
            """
            )

            # Step 2: Validate temp table creation and count records
            cursor = conn.execute("SELECT COUNT(*) FROM temp_valid_fts")
            valid_count = cursor.fetchone()[0]

            # Step 3: Validate temp table is accessible
            try:
                conn.execute("SELECT 1 FROM temp_valid_fts LIMIT 1")
                temp_table_ok = True
            except Exception:
                temp_table_ok = False

            # Step 4: Only proceed if validation passed
            if not temp_table_ok:
                log.warning(
                    "FTS temp table validation failed, skipping FTS cleanup for safety"
                )
                conn.execute("DROP TABLE IF EXISTS temp_valid_fts")
                return -1  # Signal FTS cleanup was skipped

            # Step 5: FTS cleanup operation (already in transaction)
            try:
                # Delete all FTS content
                conn.execute("DELETE FROM embedding_fulltext_search")

                # Re-insert only valid content if any exists
                if valid_count > 0:
                    conn.execute(
                        """
                        INSERT INTO embedding_fulltext_search(string_value)
                        SELECT string_value FROM temp_valid_fts
                    """
                    )
                    log.debug(f"Preserved {valid_count} valid FTS entries")
                else:
                    log.debug("No valid FTS content found, cleared all entries")

                # Rebuild FTS index
                conn.execute(
                    "INSERT INTO embedding_fulltext_search(embedding_fulltext_search) VALUES('rebuild')"
                )

            except Exception as e:
                log.error(f"FTS cleanup failed: {e}")
                conn.execute("DROP TABLE IF EXISTS temp_valid_fts")
                return -1  # Signal FTS cleanup failed

            # Step 6: Clean up temporary table
            conn.execute("DROP TABLE IF EXISTS temp_valid_fts")

            return valid_count

        except Exception as e:
            log.error(f"FTS cleanup validation failed, leaving FTS untouched: {e}")
            # Conservative approach: don't touch FTS if anything goes wrong
            try:
                conn.execute("DROP TABLE IF EXISTS temp_valid_fts")
            except Exception:
                pass
            return -1  # Signal FTS cleanup was skipped


class PGVectorDatabaseCleaner(VectorDatabaseCleaner):
    """
    PGVector database cleanup implementation.

    Leverages the existing PGVector client's delete() method for simple,
    reliable collection cleanup while maintaining comprehensive error handling
    and safety features.
    """

    # PGVector shares one SQLAlchemy session; never probe it from worker
    # threads. The bulk override below removes the need for per-user probes
    # entirely, but this keeps the fallback path (if the bulk query fails)
    # sequential and session-safe.
    _MEMORY_PROBE_WORKERS = 1

    def __init__(self, vector_db_client):
        """Initialize PGVector cleaner with client."""
        self.vector_db_client = vector_db_client
        # Validate that we can access the PGVector client
        try:
            if hasattr(vector_db_client, "session") and vector_db_client.session:
                self.session = vector_db_client.session
                log.debug("PGVector cleaner initialized successfully")
            else:
                raise Exception("PGVector client session not available")
        except Exception as e:
            log.error(f"Failed to initialize PGVector client for cleanup: {e}")
            self.session = None

    def count_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> int:
        """Count orphaned PGVector collections for preview."""
        if not self.session:
            log.warning(
                "PGVector session not available for counting orphaned collections"
            )
            return 0

        try:
            orphaned_collections = self._get_orphaned_collections(
                active_file_ids, active_kb_ids, active_user_ids
            )
            self.session.rollback()  # Read-only transaction
            return len(orphaned_collections)

        except Exception as e:
            if self.session:
                self.session.rollback()
            log.error(f"Error counting orphaned PGVector collections: {e}")
            return 0

    def iter_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Generator[Tuple[str, str], None, None]:
        """Yield (collection_name, context) for each orphaned PGVector collection."""
        if not self.session:
            return

        try:
            orphaned_collections = self._get_orphaned_collections(
                active_file_ids, active_kb_ids, active_user_ids
            )
            self.session.rollback()
            for name in orphaned_collections:
                yield (name, "pgvector")
        except Exception as e:
            if self.session:
                self.session.rollback()
            log.debug(f"Error iterating orphaned PGVector collections: {e}")

    def cleanup_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> tuple[int, Optional[str]]:
        """
        Delete orphaned PGVector collections using the existing client's delete method.

        This is the "super easy" approach suggested by @recrudesce - just use the
        existing PGVector client's delete() method for each orphaned collection.
        """
        if not self.session:
            error_msg = "PGVector session not available for cleanup"
            log.warning(error_msg)
            return (0, error_msg)

        try:
            orphaned_collections = self._get_orphaned_collections(
                active_file_ids, active_kb_ids, active_user_ids
            )

            if not orphaned_collections:
                log.debug("No orphaned PGVector collections found")
                return (0, None)

            deleted_count = 0
            log.info(
                f"Deleting {len(orphaned_collections)} orphaned PGVector collections"
            )

            # SIMPLIFIED DELETION: Use existing PGVector client delete method
            for collection_name in orphaned_collections:
                try:
                    # This is @recrudesce's "super easy" approach:
                    # Just call the existing delete method!
                    self.vector_db_client.delete(collection_name)
                    deleted_count += 1
                    log.debug(f"Deleted PGVector collection: {collection_name}")

                except Exception as e:
                    log.error(
                        f"Failed to delete PGVector collection '{collection_name}': {e}"
                    )
                    # Continue with other collections even if one fails
                    continue

            # CRITICAL: Clean up orphaned chunks within active KB collections
            # KB collections may contain chunks referencing deleted files
            # This handles the case where a file is deleted but the KB collection remains active
            # NOTE: We use the active_file_ids set instead of querying the `file` table directly,
            # because in split-DB deployments the `file` table lives in a separate database
            # and cannot be referenced from the vector database.
            orphaned_chunks_deleted = 0
            try:
                if self.session and active_file_ids:
                    log.debug("Cleaning orphaned chunks from active KB collections")
                    # First, find all distinct file_ids referenced by chunks
                    file_id_result = self.session.execute(
                        text("""
                        SELECT DISTINCT dc.vmetadata->>'file_id' AS file_id
                        FROM document_chunk dc
                        WHERE dc.vmetadata ? 'file_id'
                          AND dc.vmetadata->>'file_id' IS NOT NULL
                    """)
                    )
                    referenced_file_ids = {row[0] for row in file_id_result}

                    # Determine which referenced file_ids are orphaned (not in active set)
                    orphaned_file_ids = referenced_file_ids - active_file_ids
                    if orphaned_file_ids:
                        # Delete chunks referencing orphaned file_ids in batches
                        orphaned_list = list(orphaned_file_ids)
                        batch_size = 500
                        for i in range(0, len(orphaned_list), batch_size):
                            batch = orphaned_list[i : i + batch_size]
                            result = self.session.execute(
                                text("""
                                    DELETE FROM document_chunk dc
                                    WHERE dc.vmetadata ? 'file_id'
                                      AND dc.vmetadata->>'file_id' IN :file_ids
                                """).bindparams(bindparam("file_ids", expanding=True)),
                                {"file_ids": batch},
                            )
                            orphaned_chunks_deleted += result.rowcount
                        self.session.commit()
                    if orphaned_chunks_deleted > 0:
                        log.info(
                            f"Deleted {orphaned_chunks_deleted} orphaned chunks from active collections"
                        )
                elif self.session:
                    log.debug(
                        "Cleaning orphaned chunks from active KB collections (no active files)"
                    )
                    # If there are no active file IDs, all chunks with file_id metadata are orphaned
                    result = self.session.execute(
                        text("""
                        DELETE FROM document_chunk dc
                        WHERE dc.vmetadata ? 'file_id'
                          AND dc.vmetadata->>'file_id' IS NOT NULL
                    """)
                    )
                    orphaned_chunks_deleted = result.rowcount
                    self.session.commit()
                    if orphaned_chunks_deleted > 0:
                        log.info(
                            f"Deleted {orphaned_chunks_deleted} orphaned chunks from active collections"
                        )
            except Exception as e:
                log.error(f"Failed to clean orphaned chunks: {e}")
                if self.session:
                    self.session.rollback()

            total_deleted = deleted_count + orphaned_chunks_deleted
            if total_deleted > 0:
                log.info(
                    f"Successfully deleted {deleted_count} orphaned collections and {orphaned_chunks_deleted} orphaned chunks"
                )

            return (deleted_count, None)

        except Exception as e:
            if self.session:
                self.session.rollback()
            error_msg = f"PGVector cleanup failed: {e}"
            log.error(error_msg)
            return (0, error_msg)

    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a specific PGVector collection using the existing client method.

        Super simple - just call the existing delete method!
        """
        try:
            # @recrudesce's "super easy" approach: use existing client!
            self.vector_db_client.delete(collection_name)
            log.debug(f"Deleted PGVector collection: {collection_name}")
            return True

        except Exception as e:
            log.error(f"Error deleting PGVector collection '{collection_name}': {e}")
            return False

    def _get_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Set[str]:
        """
        Find collections that exist in PGVector but are no longer referenced.

        This is the only "complex" part - discovery. The actual deletion is simple!
        """
        try:
            expected_collections = self._build_expected_collections(
                active_file_ids, active_kb_ids, active_user_ids
            )

            # Query distinct collection names from document_chunk table
            result = self.session.execute(
                text("SELECT DISTINCT collection_name FROM document_chunk")
            ).fetchall()

            existing_collections = {row[0] for row in result}
            orphaned_collections = existing_collections - expected_collections

            log.debug(
                f"Found {len(existing_collections)} existing collections, "
                f"{len(expected_collections)} expected, "
                f"{len(orphaned_collections)} orphaned"
            )

            return orphaned_collections

        except Exception as e:
            log.error(f"Error finding orphaned PGVector collections: {e}")
            return set()

    def _build_expected_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Set[str]:
        """Build set of collection names that should exist."""
        expected_collections = set()

        # File collections use "file-{id}" pattern (same as ChromaDB)
        for file_id in active_file_ids:
            expected_collections.add(f"file-{file_id}")

        # Knowledge base collections use the KB ID directly (same as ChromaDB)
        for kb_id in active_kb_ids:
            expected_collections.add(kb_id)

        # Preserve active users' memory collections (user-memory-{id}); only a
        # deleted user's memory collection should be treated as orphaned.
        for user_id in active_user_ids or set():
            expected_collections.add(f"user-memory-{user_id}")

        # Shared KB-metadata collection is pruned per-entry, never wholesale.
        expected_collections.add(KNOWLEDGE_BASES_COLLECTION)

        return expected_collections

    def _collection_point_ids(self, collection_name: str) -> Optional[Set[str]]:
        """Read one collection's point ids straight from document_chunk.

        The generic base version calls client.get(), which materialises every
        row's text and vector just to hand back the ids. Here we select only
        the id column. Used for the shared KB-metadata collection and as the
        per-user memory fallback when the bulk scan is unavailable; runs on the
        shared session, so it stays sequential (see _MEMORY_PROBE_WORKERS).
        A missing collection simply yields an empty set, which every caller
        treats the same as "nothing to reconcile".
        """
        if not self.session or text is None:
            return super()._collection_point_ids(collection_name)
        try:
            rows = self.session.execute(
                text("SELECT id FROM document_chunk WHERE collection_name = :c"),
                {"c": collection_name},
            )
            ids = {str(pid) for (pid,) in rows if pid is not None}
            self.session.rollback()  # read-only transaction
            return ids
        except Exception as e:
            if self.session:
                self.session.rollback()
            log.debug(f"PGVector id-only fetch failed for {collection_name}: {e}")
            return super()._collection_point_ids(collection_name)

    def _present_memory_ids_by_user(self, uids: "list") -> Optional[dict]:
        """Enumerate every user's memory point ids in one query.

        Every memory embedding lives as a row in the shared document_chunk
        table keyed by (collection_name, id), where collection_name is
        'user-memory-{uid}' and id is the memory row id — the same id space the
        generic get() exposes. A single scan therefore replaces one existence
        check plus one heavy per-user get() (which would also load the vector
        column) for each of potentially thousands of users. Returns None on any
        failure so the caller falls back to the sequential per-user probe.
        """
        if not self.session or text is None:
            return None

        wanted = {str(u) for u in uids}
        if not wanted:
            return {}

        prefix = "user-memory-"
        present = {uid: set() for uid in wanted}
        try:
            rows = self.session.execute(
                text(
                    "SELECT collection_name, id FROM document_chunk "
                    "WHERE collection_name LIKE 'user-memory-%'"
                )
            )
            for collection_name, pid in rows:
                if not collection_name or pid is None:
                    continue
                if not str(collection_name).startswith(prefix):
                    continue
                uid = str(collection_name)[len(prefix) :]
                bucket = present.get(uid)
                if bucket is not None:  # only active users we were asked about
                    bucket.add(str(pid))
            self.session.rollback()  # read-only transaction
        except Exception as e:
            if self.session:
                self.session.rollback()
            log.debug(
                f"PGVector bulk memory id scan failed, using per-user probe: {e}"
            )
            return None

        return present


def _ensure_milvus_default_connection():
    """utility.*/Collection() use pymilvus' global 'default' alias, which the
    standard-mode Open WebUI client never opens at init (only lazily in
    query()). Connect it if missing so cleanup works on a fresh process."""
    try:
        from pymilvus import connections

        if connections.has_connection("default"):
            return
        try:
            from open_webui.config import MILVUS_URI, MILVUS_TOKEN, MILVUS_DB
        except ImportError:
            from backend.open_webui.config import MILVUS_URI, MILVUS_TOKEN, MILVUS_DB
        connections.connect(uri=MILVUS_URI, token=MILVUS_TOKEN, db_name=MILVUS_DB)
    except Exception as e:
        log.debug(f"Could not establish Milvus default connection: {e}")


class MilvusDatabaseCleaner(VectorDatabaseCleaner):
    """
    Milvus database cleanup implementation (standard mode).

    Handles Milvus's collection-based storage where each collection is independent.
    Collections use the pattern: "{prefix}_{collection_name}" where collection_name
    is typically "file-{id}" for files or knowledge base IDs.
    """

    def __init__(self, vector_db_client):
        """Initialize Milvus cleaner with client."""
        self.vector_db_client = vector_db_client
        self.collection_prefix = getattr(
            vector_db_client, "collection_prefix", "open_webui"
        )
        log.debug(f"Milvus cleaner initialized with prefix: {self.collection_prefix}")

    def count_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> int:
        """Count orphaned Milvus collections for preview."""
        try:
            expected_collections = self._build_expected_collections(
                active_file_ids, active_kb_ids, active_user_ids
            )

            # List all collections
            all_collections = self.vector_db_client.client.list_collections()

            # Count collections with our prefix that are not expected
            count = 0
            for collection_name in all_collections:
                if collection_name.startswith(f"{self.collection_prefix}_"):
                    # Extract the original name (remove prefix)
                    original_name = collection_name[len(self.collection_prefix) + 1 :]
                    # Restore dashes (Milvus converts - to _)
                    original_name = original_name.replace("_", "-")

                    if original_name not in expected_collections:
                        count += 1
                        log.debug(
                            f"Found orphaned Milvus collection: {collection_name}"
                        )

            return count

        except Exception as e:
            log.error(f"Error counting orphaned Milvus collections: {e}")
            return 0

    def iter_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Generator[Tuple[str, str], None, None]:
        """Yield (original_name, full_collection_name) for each orphaned Milvus collection."""
        try:
            expected_collections = self._build_expected_collections(
                active_file_ids, active_kb_ids, active_user_ids
            )
            all_collections = self.vector_db_client.client.list_collections()

            for collection_name in all_collections:
                if collection_name.startswith(f"{self.collection_prefix}_"):
                    original_name = collection_name[len(self.collection_prefix) + 1 :]
                    original_name = original_name.replace("_", "-")

                    if original_name not in expected_collections:
                        yield (original_name, collection_name)
        except Exception as e:
            log.debug(f"Error iterating orphaned Milvus collections: {e}")

    def cleanup_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> tuple[int, Optional[str]]:
        """Actually delete orphaned Milvus collections."""
        try:
            _ensure_milvus_default_connection()
            expected_collections = self._build_expected_collections(
                active_file_ids, active_kb_ids, active_user_ids
            )

            # List all collections
            all_collections = self.vector_db_client.client.list_collections()

            deleted_count = 0
            errors = []

            for collection_name in all_collections:
                if collection_name.startswith(f"{self.collection_prefix}_"):
                    # Extract the original name (remove prefix)
                    original_name = collection_name[len(self.collection_prefix) + 1 :]
                    # Restore dashes (Milvus converts - to _)
                    original_name = original_name.replace("_", "-")

                    if original_name not in expected_collections:
                        try:
                            # Use utility.drop_collection instead of client method
                            utility.drop_collection(collection_name)
                            deleted_count += 1
                            log.info(
                                f"Deleted orphaned Milvus collection: {collection_name}"
                            )
                        except Exception as e:
                            error_msg = (
                                f"Failed to delete collection {collection_name}: {e}"
                            )
                            log.error(error_msg)
                            errors.append(error_msg)

            if deleted_count > 0:
                log.info(f"Deleted {deleted_count} orphaned Milvus collections")

            if errors:
                return (deleted_count, "; ".join(errors))
            return (deleted_count, None)

        except Exception as e:
            error_msg = f"Milvus cleanup failed: {e}"
            log.error(error_msg)
            return (0, error_msg)

    def delete_collection(self, collection_name: str) -> bool:
        """Delete a specific Milvus collection by name."""
        try:
            _ensure_milvus_default_connection()
            # Convert dashes to underscores (Milvus naming convention)
            collection_name = collection_name.replace("-", "_")
            full_name = f"{self.collection_prefix}_{collection_name}"

            # Check if collection exists using utility module
            if utility.has_collection(full_name):
                utility.drop_collection(full_name)
                log.debug(f"Deleted Milvus collection: {full_name}")
                return True
            else:
                log.debug(f"Milvus collection does not exist: {full_name}")
                return True  # Not existing is effectively deleted

        except Exception as e:
            log.error(f"Error deleting Milvus collection '{collection_name}': {e}")
            return False

    def _build_expected_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Set[str]:
        """Build set of collection names that should exist."""
        expected_collections = set()

        # File collections use "file-{id}" pattern
        for file_id in active_file_ids:
            expected_collections.add(f"file-{file_id}")

        # Knowledge base collections use the KB ID directly
        for kb_id in active_kb_ids:
            expected_collections.add(kb_id)

        # Preserve active users' memory collections (user-memory-{id}); only a
        # deleted user's memory collection should be treated as orphaned.
        for user_id in active_user_ids or set():
            expected_collections.add(f"user-memory-{user_id}")

        # Shared KB-metadata collection is pruned per-entry, never wholesale.
        expected_collections.add(KNOWLEDGE_BASES_COLLECTION)

        return expected_collections


# Milvus delete filters are interpolated strings with no parameter binding; only
# ids matching Open WebUI's own resource_id charset may reach one. Mirrors core.
_MILVUS_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,255}$")


class MilvusMultitenancyDatabaseCleaner(VectorDatabaseCleaner):
    """
    Milvus multitenancy database cleanup implementation.

    Handles Milvus's multitenancy mode where multiple logical collections
    share physical collections using a resource_id field for partitioning.

    In multitenancy mode, there are shared collections like:
    - {prefix}_memories - for user memories
    - {prefix}_knowledge - for knowledge bases
    - {prefix}_files - for file-based collections
    - {prefix}_web_search - for web search results
    - {prefix}_hash_based - for hash-based collections

    Each shared collection contains data from multiple logical collections,
    distinguished by the resource_id field.
    """

    def __init__(self, vector_db_client):
        """Initialize Milvus multitenancy cleaner with client."""
        self.vector_db_client = vector_db_client
        self.collection_prefix = getattr(
            vector_db_client, "collection_prefix", "open_webui"
        )

        # Get shared collection names
        self.shared_collections = getattr(
            vector_db_client,
            "shared_collections",
            [
                f"{self.collection_prefix}_memories",
                f"{self.collection_prefix}_knowledge",
                f"{self.collection_prefix}_files",
                f"{self.collection_prefix}_web_search",
                f"{self.collection_prefix}_hash_based",
            ],
        )
        log.debug(
            f"Milvus multitenancy cleaner initialized with prefix: {self.collection_prefix}"
        )
        log.debug(f"Shared collections: {self.shared_collections}")

    def _skip_shared_collection(self, collection_name, active_user_ids) -> bool:
        # Memory tenants can't be classified orphaned without the active-user set,
        # so protect them all when it is unknown rather than wiping every memory.
        return active_user_ids is None and collection_name.endswith("_memories")

    def count_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> int:
        """
        Count orphaned resource_ids across all shared collections.

        In multitenancy mode, we count distinct resource_ids that are not
        in our expected set across all shared collections.
        """
        try:
            expected_resource_ids = self._build_expected_resource_ids(
                active_file_ids, active_kb_ids, active_user_ids
            )

            count = 0

            # Import pymilvus utilities
            for shared_collection_name in self.shared_collections:
                if self._skip_shared_collection(shared_collection_name, active_user_ids):
                    continue
                if not utility.has_collection(shared_collection_name):
                    continue

                try:
                    collection = Collection(shared_collection_name)
                    collection.load()

                    # Query ALL resource_ids with pagination using query_iterator
                    # (offset + limit must be < 16384, so iterator is the correct approach)
                    all_resource_ids = set()

                    iterator = collection.query_iterator(
                        expr="",  # Empty expression to query all records
                        output_fields=["resource_id"],
                        batch_size=1000,
                    )

                    batch_count = 0
                    while True:
                        results = iterator.next()
                        if not results:
                            iterator.close()
                            break

                        # Collect resource_ids from this batch
                        batch_resource_ids = {res["resource_id"] for res in results}
                        all_resource_ids.update(batch_resource_ids)
                        batch_count += 1

                        if batch_count % 10 == 0:
                            log.debug(
                                f"Fetched {len(all_resource_ids)} resource_ids so far from {shared_collection_name} ({batch_count} batches)"
                            )

                    log.info(
                        f"Total resource_ids in {shared_collection_name}: {len(all_resource_ids)}"
                    )

                    # Count orphaned ones
                    for resource_id in all_resource_ids:
                        if resource_id not in expected_resource_ids:
                            count += 1
                            log.debug(
                                f"Found orphaned resource_id in {shared_collection_name}: {resource_id}"
                            )

                except Exception as e:
                    log.error(
                        f"Error checking shared collection {shared_collection_name}: {e}"
                    )

            return count

        except Exception as e:
            log.error(f"Error counting orphaned Milvus multitenancy collections: {e}")
            return 0

    def iter_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Generator[Tuple[str, str], None, None]:
        """Yield (resource_id, shared_collection_name) for each orphaned Milvus MT resource."""
        try:
            expected_resource_ids = self._build_expected_resource_ids(
                active_file_ids, active_kb_ids, active_user_ids
            )

            for shared_collection_name in self.shared_collections:
                if self._skip_shared_collection(shared_collection_name, active_user_ids):
                    continue
                if not utility.has_collection(shared_collection_name):
                    continue

                try:
                    collection = Collection(shared_collection_name)
                    collection.load()

                    all_resource_ids = set()
                    iterator = collection.query_iterator(
                        expr="",
                        output_fields=["resource_id"],
                        batch_size=1000,
                    )

                    while True:
                        results = iterator.next()
                        if not results:
                            iterator.close()
                            break
                        all_resource_ids.update(res["resource_id"] for res in results)

                    for resource_id in all_resource_ids:
                        if resource_id not in expected_resource_ids:
                            yield (resource_id, shared_collection_name)

                except Exception as e:
                    log.debug(
                        f"Error iterating shared collection {shared_collection_name}: {e}"
                    )

        except Exception as e:
            log.debug(f"Error iterating orphaned Milvus MT collections: {e}")

    def cleanup_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> tuple[int, Optional[str]]:
        """
        Delete orphaned resource_ids from shared collections.

        In multitenancy mode, we delete records by resource_id filter
        from the shared collections.
        """
        try:
            expected_resource_ids = self._build_expected_resource_ids(
                active_file_ids, active_kb_ids, active_user_ids
            )

            deleted_count = 0
            errors = []

            # Import pymilvus utilities
            for shared_collection_name in self.shared_collections:
                if self._skip_shared_collection(shared_collection_name, active_user_ids):
                    continue
                if not utility.has_collection(shared_collection_name):
                    continue

                try:
                    collection = Collection(shared_collection_name)
                    collection.load()

                    # Query ALL resource_ids with pagination using query_iterator
                    # (offset + limit must be < 16384, so iterator is the correct approach)
                    all_resource_ids = set()

                    iterator = collection.query_iterator(
                        expr="",  # Empty expression to query all records
                        output_fields=["resource_id"],
                        batch_size=1000,
                    )

                    batch_count = 0
                    while True:
                        results = iterator.next()
                        if not results:
                            iterator.close()
                            break

                        # Collect resource_ids from this batch
                        batch_resource_ids = {res["resource_id"] for res in results}
                        all_resource_ids.update(batch_resource_ids)
                        batch_count += 1

                        if batch_count % 10 == 0:
                            log.debug(
                                f"Fetched {len(all_resource_ids)} resource_ids so far from {shared_collection_name} ({batch_count} batches)"
                            )

                    log.info(
                        f"Total resource_ids in {shared_collection_name}: {len(all_resource_ids)}"
                    )

                    # Get unique orphaned resource_ids
                    orphaned_ids = [
                        rid
                        for rid in all_resource_ids
                        if rid not in expected_resource_ids
                    ]

                    log.info(
                        f"Found {len(orphaned_ids)} orphaned resource_ids in {shared_collection_name}"
                    )

                    # Delete each orphaned resource_id
                    for resource_id in orphaned_ids:
                        if not _MILVUS_RESOURCE_ID_RE.match(str(resource_id)):
                            log.warning(
                                f"Skipping unsafe resource_id in {shared_collection_name}: {resource_id!r}"
                            )
                            continue
                        try:
                            # Delete by resource_id filter expression
                            expr = f"resource_id == '{resource_id}'"
                            collection.delete(expr)
                            deleted_count += 1
                            log.info(
                                f"Deleted orphaned resource_id from {shared_collection_name}: {resource_id}"
                            )
                        except Exception as e:
                            error_msg = f"Failed to delete resource_id {resource_id} from {shared_collection_name}: {e}"
                            log.error(error_msg)
                            errors.append(error_msg)

                    # Flush after all deletions in this collection
                    if orphaned_ids:
                        collection.flush()
                        log.debug(f"Flushed deletions for {shared_collection_name}")

                except Exception as e:
                    error_msg = f"Error processing shared collection {shared_collection_name}: {e}"
                    log.error(error_msg)
                    errors.append(error_msg)

            if deleted_count > 0:
                log.info(
                    f"Deleted {deleted_count} orphaned Milvus multitenancy resource_ids"
                )

            if errors:
                return (deleted_count, "; ".join(errors))
            return (deleted_count, None)

        except Exception as e:
            error_msg = f"Milvus multitenancy cleanup failed: {e}"
            log.error(error_msg)
            return (0, error_msg)

    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a specific logical collection in multitenancy mode.

        This deletes all records with the matching resource_id from
        the appropriate shared collection.
        """
        try:
            # Use the reference implementation's _get_collection_and_resource_id logic
            # to determine which shared collection contains this resource_id
            resource_id = collection_name

            if not _MILVUS_RESOURCE_ID_RE.match(str(resource_id)):
                log.warning(f"Refusing unsafe Milvus resource_id: {resource_id!r}")
                return False

            # Determine which shared collection based on naming pattern
            if collection_name.startswith("user-memory-"):
                mt_collection = f"{self.collection_prefix}_memories"
            elif collection_name.startswith("file-"):
                mt_collection = f"{self.collection_prefix}_files"
            elif collection_name.startswith("web-search-"):
                mt_collection = f"{self.collection_prefix}_web_search"
            elif len(collection_name) == 63 and all(
                c in "0123456789abcdef" for c in collection_name
            ):
                mt_collection = f"{self.collection_prefix}_hash_based"
            else:
                mt_collection = f"{self.collection_prefix}_knowledge"

            # Check if the shared collection exists
            if not utility.has_collection(mt_collection):
                log.debug(f"Shared collection {mt_collection} does not exist")
                return True  # Not existing is effectively deleted

            # Delete by resource_id
            collection = Collection(mt_collection)
            collection.load()
            expr = f"resource_id == '{resource_id}'"
            collection.delete(expr)
            collection.flush()

            log.debug(
                f"Deleted Milvus multitenancy collection: {collection_name} from {mt_collection}"
            )
            return True

        except Exception as e:
            log.error(
                f"Error deleting Milvus multitenancy collection '{collection_name}': {e}"
            )
            return False

    def _build_expected_resource_ids(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Set[str]:
        """
        Build set of resource_ids that should exist across all shared collections.

        This provides 100% coverage by identifying ALL resource_ids that should be preserved.
        Any resource_id NOT in this set will be deleted as orphaned, which includes:
        - Orphaned file collections (files deleted from DB)
        - Orphaned knowledge bases (KBs deleted from DB)
        - Orphaned user memories (users deleted from DB)
        - Web-search collections (ephemeral cache, not tracked in DB)
        - Hash-based collections (temporary content hashes, not tracked in DB)

        This matches ChromaDB/PGVector behavior where ONLY DB-tracked items are preserved.

        Args:
            active_file_ids: Active file IDs from Files table
            active_kb_ids: Active knowledge base IDs from Knowledges table
            active_user_ids: Active user IDs from Users table (optional)

        Returns:
            Set of expected resource_ids across all 5 shared collections
        """
        expected_resource_ids = set()

        # FILE_COLLECTION: file-{id} pattern
        for file_id in active_file_ids:
            expected_resource_ids.add(f"file-{file_id}")

        # KNOWLEDGE_COLLECTION: KB ID directly (fallback for unrecognized patterns)
        for kb_id in active_kb_ids:
            expected_resource_ids.add(kb_id)

        # MEMORY_COLLECTION: user-memory-{user_id} pattern
        if active_user_ids is not None:
            for user_id in active_user_ids:
                expected_resource_ids.add(f"user-memory-{user_id}")

        # Shared KB-metadata collection is pruned per-entry, never wholesale.
        expected_resource_ids.add(KNOWLEDGE_BASES_COLLECTION)

        # WEB_SEARCH_COLLECTION: web-search-{hash} patterns
        # These are NOT in expected set → will be deleted as orphaned ✓
        # Rationale: Ephemeral caches, not tracked in DB, safe to clean

        # HASH_BASED_COLLECTION: {63-char-hex} patterns
        # These are NOT in expected set → will be deleted as orphaned ✓
        # Rationale: Temporary content hashes, not tracked in DB, safe to clean

        return expected_resource_ids


class QdrantDatabaseCleaner(VectorDatabaseCleaner):
    """
    Qdrant vector database cleaner for standard (non-multitenancy) mode.

    In standard mode, each file/KB gets its own collection with naming:
    - {prefix}_file-{file_id}
    - {prefix}_{kb_id}

    Collections are deleted entirely when orphaned.
    """

    def __init__(self, vector_db_client):
        self.vector_db_client = vector_db_client
        self.client = vector_db_client.client
        self.collection_prefix = vector_db_client.collection_prefix

    def count_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> int:
        """Count orphaned Qdrant collections."""
        try:
            expected_collections = self._build_expected_collections(
                active_file_ids, active_kb_ids, active_user_ids
            )

            # Get all collections with our prefix
            all_collections = self.client.get_collections().collections
            count = 0

            for collection in all_collections:
                collection_name = collection.name
                if collection_name.startswith(f"{self.collection_prefix}_"):
                    # Remove prefix to get original name
                    original_name = collection_name[len(self.collection_prefix) + 1 :]

                    if original_name not in expected_collections:
                        count += 1

        except Exception as e:
            log.error(f"Error counting orphaned Qdrant collections: {e}")
            return 0

        return count

    def iter_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Generator[Tuple[str, str], None, None]:
        """Yield (original_name, full_collection_name) for each orphaned Qdrant collection."""
        try:
            expected_collections = self._build_expected_collections(
                active_file_ids, active_kb_ids, active_user_ids
            )
            all_collections = self.client.get_collections().collections

            for collection in all_collections:
                collection_name = collection.name
                if collection_name.startswith(f"{self.collection_prefix}_"):
                    original_name = collection_name[len(self.collection_prefix) + 1 :]
                    if original_name not in expected_collections:
                        yield (original_name, collection_name)
        except Exception as e:
            log.debug(f"Error iterating orphaned Qdrant collections: {e}")

    def cleanup_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> tuple[int, Optional[str]]:
        """Delete orphaned Qdrant collections."""
        try:
            expected_collections = self._build_expected_collections(
                active_file_ids, active_kb_ids, active_user_ids
            )

            # Get all collections with our prefix
            all_collections = self.client.get_collections().collections
            deleted_count = 0
            errors = []

            for collection in all_collections:
                collection_name = collection.name
                if collection_name.startswith(f"{self.collection_prefix}_"):
                    # Remove prefix to get original name
                    original_name = collection_name[len(self.collection_prefix) + 1 :]

                    if original_name not in expected_collections:
                        try:
                            self.client.delete_collection(
                                collection_name=collection_name
                            )
                            deleted_count += 1
                            log.info(
                                f"Deleted orphaned Qdrant collection: {original_name}"
                            )
                        except Exception as e:
                            error_msg = f"Failed to delete Qdrant collection {collection_name}: {e}"
                            log.error(error_msg)
                            errors.append(error_msg)

        except Exception as e:
            error_msg = f"Qdrant cleanup failed: {e}"
            log.error(error_msg)
            return (0, error_msg)

        if errors:
            return (deleted_count, "; ".join(errors))
        return (deleted_count, None)

    def delete_collection(self, collection_name: str) -> bool:
        """Delete a specific Qdrant collection by name."""
        try:
            full_name = f"{self.collection_prefix}_{collection_name}"
            if self.client.collection_exists(collection_name=full_name):
                self.client.delete_collection(collection_name=full_name)
                log.debug(f"Deleted Qdrant collection: {collection_name}")
            return True
        except Exception as e:
            log.error(f"Error deleting Qdrant collection {collection_name}: {e}")
            return False

    def _build_expected_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Set[str]:
        """Build set of expected collection names (without prefix)."""
        expected_collections = set()

        # File collections use file-{id} pattern
        for file_id in active_file_ids:
            expected_collections.add(f"file-{file_id}")

        # Knowledge base collections use the KB ID directly
        for kb_id in active_kb_ids:
            expected_collections.add(kb_id)

        # Preserve active users' memory collections (user-memory-{id}); only a
        # deleted user's memory collection should be treated as orphaned.
        for user_id in active_user_ids or set():
            expected_collections.add(f"user-memory-{user_id}")

        # Shared KB-metadata collection is pruned per-entry, never wholesale.
        expected_collections.add(KNOWLEDGE_BASES_COLLECTION)

        return expected_collections


class QdrantMultitenancyDatabaseCleaner(VectorDatabaseCleaner):
    """
    Qdrant multitenancy vector database cleaner.

    In multitenancy mode, there are 5 shared collections:
    - {prefix}_memories - for user-memory-{user_id}
    - {prefix}_files - for file-{file_id}
    - {prefix}_knowledge - for {kb_id} (default)
    - {prefix}_web-search - for web-search-{hash} (ephemeral)
    - {prefix}_hash-based - for {63-char-hex} (temporary)

    Each collection stores points with a tenant_id field. Cleanup deletes
    orphaned tenant_ids (not entire collections).

    Uses scroll() with pagination to handle unlimited tenant IDs without
    exceeding memory limits.
    """

    def __init__(self, vector_db_client):
        self.vector_db_client = vector_db_client
        self.client = vector_db_client.client
        self.collection_prefix = vector_db_client.collection_prefix

        # Shared collection names
        self.shared_collections = [
            f"{self.collection_prefix}_memories",
            f"{self.collection_prefix}_files",
            f"{self.collection_prefix}_knowledge",
            f"{self.collection_prefix}_web-search",
            f"{self.collection_prefix}_hash-based",
        ]

    def count_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> int:
        """
        Count orphaned tenant_ids across all shared collections.

        Uses Qdrant's scroll() API with pagination for memory efficiency.
        """
        try:
            expected_tenant_ids = self._build_expected_tenant_ids(
                active_file_ids, active_kb_ids, active_user_ids or set()
            )

            log.info(
                f"Qdrant multitenancy: {len(active_kb_ids)} active KBs, {len(active_file_ids)} active files, {len(active_user_ids or set())} active users"
            )
            log.info(
                f"Qdrant multitenancy: Built {len(expected_tenant_ids)} expected tenant_ids"
            )
            log.debug(f"Expected tenant_ids sample: {list(expected_tenant_ids)[:10]}")

            orphaned_count = 0

            for collection_name in self.shared_collections:
                if not self.client.collection_exists(collection_name=collection_name):
                    continue

                try:
                    # Get all unique tenant_ids in this collection using scroll
                    # Qdrant doesn't have a direct "get unique values" API, so we scroll through points
                    all_tenant_ids = set()
                    offset = None

                    while True:
                        # Scroll through points in batches
                        scroll_result = self.client.scroll(
                            collection_name=collection_name,
                            limit=1000,  # Batch size
                            offset=offset,
                            with_payload=True,
                            with_vectors=False,  # Don't need vectors, save bandwidth
                        )

                        points, next_offset = scroll_result

                        if not points:
                            break

                        # Extract unique tenant_ids from this batch
                        for point in points:
                            if "tenant_id" in point.payload:
                                all_tenant_ids.add(point.payload["tenant_id"])

                        # Check if there are more results
                        if next_offset is None:
                            break

                        offset = next_offset

                    log.debug(
                        f"Found {len(all_tenant_ids)} tenant_ids in {collection_name}"
                    )

                    # Count orphaned tenant_ids
                    orphaned_in_this_collection = []
                    for tenant_id in all_tenant_ids:
                        if tenant_id not in expected_tenant_ids:
                            orphaned_count += 1
                            orphaned_in_this_collection.append(tenant_id)

                    if orphaned_in_this_collection:
                        log.warning(
                            f"Found {len(orphaned_in_this_collection)} orphaned tenant_ids in {collection_name}: {orphaned_in_this_collection}"
                        )

                except Exception as e:
                    log.error(
                        f"Error scanning Qdrant collection {collection_name}: {e}"
                    )

        except Exception as e:
            log.error(f"Error counting orphaned Qdrant multitenancy tenant_ids: {e}")
            return 0

        return orphaned_count

    def iter_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> Generator[Tuple[str, str], None, None]:
        """Yield (tenant_id, shared_collection_name) for each orphaned Qdrant MT tenant."""
        try:
            expected_tenant_ids = self._build_expected_tenant_ids(
                active_file_ids, active_kb_ids, active_user_ids or set()
            )

            for collection_name in self.shared_collections:
                if not self.client.collection_exists(collection_name=collection_name):
                    continue

                try:
                    all_tenant_ids = set()
                    offset = None

                    while True:
                        scroll_result = self.client.scroll(
                            collection_name=collection_name,
                            limit=1000,
                            offset=offset,
                            with_payload=True,
                            with_vectors=False,
                        )

                        points, next_offset = scroll_result
                        if not points:
                            break

                        for point in points:
                            if "tenant_id" in point.payload:
                                all_tenant_ids.add(point.payload["tenant_id"])

                        if next_offset is None:
                            break
                        offset = next_offset

                    for tenant_id in all_tenant_ids:
                        if tenant_id not in expected_tenant_ids:
                            yield (tenant_id, collection_name)

                except Exception as e:
                    log.debug(
                        f"Error iterating Qdrant collection {collection_name}: {e}"
                    )

        except Exception as e:
            log.debug(f"Error iterating orphaned Qdrant MT tenant_ids: {e}")

    def cleanup_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> tuple[int, Optional[str]]:
        """
        Delete orphaned tenant_ids from shared collections.

        Uses scroll() for memory-safe iteration and batched deletions.
        """
        try:
            expected_tenant_ids = self._build_expected_tenant_ids(
                active_file_ids, active_kb_ids, active_user_ids or set()
            )

            log.info(
                f"Qdrant multitenancy cleanup: {len(active_kb_ids)} active KBs, {len(active_file_ids)} active files, {len(active_user_ids or set())} active users"
            )
            log.info(
                f"Qdrant multitenancy cleanup: Built {len(expected_tenant_ids)} expected tenant_ids"
            )

            deleted_count = 0
            errors = []

            for collection_name in self.shared_collections:
                if not self.client.collection_exists(collection_name=collection_name):
                    continue

                try:
                    # Get all unique tenant_ids using scroll (memory-safe)
                    all_tenant_ids = set()
                    offset = None

                    while True:
                        scroll_result = self.client.scroll(
                            collection_name=collection_name,
                            limit=1000,  # Batch size
                            offset=offset,
                            with_payload=True,
                            with_vectors=False,
                        )

                        points, next_offset = scroll_result

                        if not points:
                            break

                        # Extract unique tenant_ids
                        for point in points:
                            if "tenant_id" in point.payload:
                                all_tenant_ids.add(point.payload["tenant_id"])

                        if next_offset is None:
                            break

                        offset = next_offset

                    log.info(
                        f"Total tenant_ids in {collection_name}: {len(all_tenant_ids)}"
                    )

                    # Delete orphaned tenant_ids
                    orphaned_tenant_ids = [
                        tid for tid in all_tenant_ids if tid not in expected_tenant_ids
                    ]

                    if orphaned_tenant_ids:
                        log.warning(
                            f"Found {len(orphaned_tenant_ids)} orphaned tenant_ids in {collection_name}: {orphaned_tenant_ids}"
                        )
                    else:
                        log.info(f"No orphaned tenant_ids found in {collection_name}")

                    for tenant_id in orphaned_tenant_ids:
                        try:
                            # Delete all points with this tenant_id
                            self.client.delete(
                                collection_name=collection_name,
                                points_selector=qdrant_models.FilterSelector(
                                    filter=qdrant_models.Filter(
                                        must=[
                                            qdrant_models.FieldCondition(
                                                key="tenant_id",
                                                match=qdrant_models.MatchValue(
                                                    value=tenant_id
                                                ),
                                            )
                                        ]
                                    )
                                ),
                            )
                            deleted_count += 1
                            log.debug(
                                f"Deleted orphaned tenant_id from {collection_name}: {tenant_id}"
                            )
                        except Exception as e:
                            error_msg = f"Failed to delete tenant_id {tenant_id} from {collection_name}: {e}"
                            log.error(error_msg)
                            errors.append(error_msg)

                except Exception as e:
                    error_msg = (
                        f"Error processing Qdrant collection {collection_name}: {e}"
                    )
                    log.error(error_msg)
                    errors.append(error_msg)

        except Exception as e:
            error_msg = f"Qdrant multitenancy cleanup failed: {e}"
            log.error(error_msg)
            return (0, error_msg)

        if errors:
            return (deleted_count, "; ".join(errors))
        return (deleted_count, None)

    def delete_collection(self, collection_name: str) -> bool:
        """Delete a specific tenant_id from the appropriate shared collection."""
        try:
            # Determine which shared collection and tenant_id
            tenant_id = collection_name

            # Map collection name to shared collection (same logic as backend)
            if collection_name.startswith("user-memory-"):
                mt_collection = f"{self.collection_prefix}_memories"
            elif collection_name.startswith("file-"):
                mt_collection = f"{self.collection_prefix}_files"
            elif collection_name.startswith("web-search-"):
                mt_collection = f"{self.collection_prefix}_web-search"
            elif len(collection_name) == 63 and all(
                c in "0123456789abcdef" for c in collection_name
            ):
                mt_collection = f"{self.collection_prefix}_hash-based"
            else:
                mt_collection = f"{self.collection_prefix}_knowledge"

            if not self.client.collection_exists(collection_name=mt_collection):
                return True

            # Delete all points with this tenant_id
            self.client.delete(
                collection_name=mt_collection,
                points_selector=qdrant_models.FilterSelector(
                    filter=qdrant_models.Filter(
                        must=[
                            qdrant_models.FieldCondition(
                                key="tenant_id",
                                match=qdrant_models.MatchValue(value=tenant_id),
                            )
                        ]
                    )
                ),
            )
            log.debug(f"Deleted Qdrant tenant_id: {tenant_id} from {mt_collection}")
            return True
        except Exception as e:
            log.error(f"Error deleting Qdrant tenant_id {collection_name}: {e}")
            return False

    def _build_expected_tenant_ids(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Set[str],
    ) -> Set[str]:
        """
        Build set of expected tenant_ids.

        Tenant IDs are the same as collection names in the mapping:
        - file-{file_id} for files
        - {kb_id} for knowledge bases
        - user-memory-{user_id} for memories
        - web-search-{hash} (ephemeral - always orphaned)
        - {63-char-hex} (temporary - always orphaned)
        """
        expected_tenant_ids = set()

        # File tenant_ids: file-{id}
        file_tenant_ids_count = 0
        for file_id in active_file_ids:
            expected_tenant_ids.add(f"file-{file_id}")
            file_tenant_ids_count += 1

        # Knowledge base tenant_ids: {kb_id}
        kb_tenant_ids_count = 0
        kb_ids_sample = []
        for kb_id in active_kb_ids:
            expected_tenant_ids.add(kb_id)
            kb_tenant_ids_count += 1
            if kb_tenant_ids_count <= 5:  # Sample first 5 for logging
                kb_ids_sample.append(kb_id)

        # User memory tenant_ids: user-memory-{user_id}
        memory_tenant_ids_count = 0
        for user_id in active_user_ids:
            expected_tenant_ids.add(f"user-memory-{user_id}")
            memory_tenant_ids_count += 1

        # Shared KB-metadata collection is pruned per-entry, never wholesale.
        expected_tenant_ids.add(KNOWLEDGE_BASES_COLLECTION)

        log.debug(
            f"Built expected tenant_ids: {file_tenant_ids_count} files, {kb_tenant_ids_count} KBs, {memory_tenant_ids_count} memories"
        )
        if kb_ids_sample:
            log.debug(f"Sample KB IDs added as tenant_ids: {kb_ids_sample}")

        # Note: web-search-* and hash-based are ephemeral/temporary
        # They are NOT added to expected set, so they will be cleaned up

        return expected_tenant_ids


class NoOpVectorDatabaseCleaner(VectorDatabaseCleaner):
    """
    No-operation implementation for unsupported vector databases.

    This implementation does nothing and is used when the configured
    vector database is not supported by the cleanup system.
    """

    def count_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> int:
        """No orphaned collections to count for unsupported databases."""
        return 0

    def cleanup_orphaned_collections(
        self,
        active_file_ids: Set[str],
        active_kb_ids: Set[str],
        active_user_ids: Optional[Set[str]] = None,
    ) -> tuple[int, Optional[str]]:
        """No collections to cleanup for unsupported databases."""
        return (0, None)

    def delete_collection(self, collection_name: str) -> bool:
        """No collection to delete for unsupported databases."""
        return True


def get_vector_database_cleaner(
    vector_db_type: str,
    vector_db_client,
    cache_dir: Path,
    enable_milvus_multitenancy: bool = False,
    enable_qdrant_multitenancy: bool = False,
) -> VectorDatabaseCleaner:
    """
    Factory function to get the appropriate vector database cleaner.

    This function detects the configured vector database type and returns
    the appropriate cleaner implementation. Community contributors can
    extend this function to support additional vector databases.

    Multitenancy detection uses the Open WebUI config flags
    (ENABLE_MILVUS_MULTITENANCY_MODE, ENABLE_QDRANT_MULTITENANCY_MODE).

    Supported databases:
    - ChromaDB: SQLite-based vector database with directory storage
    - PGVector: PostgreSQL extension for vector operations
    - Milvus: Standalone vector database with standard collections
    - Milvus Multitenancy: Milvus with shared collections and resource_id partitioning
    - Qdrant: Standalone vector database with standard collections
    - Qdrant Multitenancy: Qdrant with shared collections and tenant_id filtering

    Returns:
        VectorDatabaseCleaner: Appropriate implementation for the configured database
    """
    vector_db_type = vector_db_type.lower()

    if "chroma" in vector_db_type:
        log.debug("Using ChromaDB cleaner")
        return ChromaDatabaseCleaner(vector_db_client, cache_dir)
    elif "pgvector" in vector_db_type:
        log.debug("Using PGVector cleaner")
        return PGVectorDatabaseCleaner(vector_db_client)
    elif "milvus" in vector_db_type:
        if enable_milvus_multitenancy:
            log.debug("Using Milvus Multitenancy cleaner")
            return MilvusMultitenancyDatabaseCleaner(vector_db_client)
        else:
            log.debug("Using Milvus standard cleaner")
            return MilvusDatabaseCleaner(vector_db_client)
    elif "qdrant" in vector_db_type:
        if enable_qdrant_multitenancy:
            log.debug("Using Qdrant Multitenancy cleaner")
            return QdrantMultitenancyDatabaseCleaner(vector_db_client)
        else:
            log.debug("Using Qdrant standard cleaner")
            return QdrantDatabaseCleaner(vector_db_client)
    else:
        log.debug(
            f"No specific cleaner for vector database type: {vector_db_type}, using no-op cleaner"
        )
        return NoOpVectorDatabaseCleaner()


# ============================================================================
# Operations (from prune_operations.py, throttled)
# ============================================================================

import asyncio
import inspect
import logging
import os
import time
from pathlib import Path
from typing import Iterator, Optional, Set, Tuple, Callable, Any
from sqlalchemy import select, text, func, and_, or_, not_, delete, update, cast, Text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

# Exception types raised for missing tables across database dialects.
# SQLite raises OperationalError; PostgreSQL raises ProgrammingError.
_TABLE_MISSING_ERRORS = (OperationalError, ProgrammingError)


def _is_table_missing_error(exc: Exception) -> bool:
    """Return True if the exception indicates a missing table or relation."""
    msg = str(exc).lower()
    # SQLite: "no such table: xxx"
    # PostgreSQL: 'relation "xxx" does not exist' / 'undefined table'
    return (
        "no such table" in msg
        or ("relation" in msg and "does not exist" in msg)
        or "undefined table" in msg
    )


async def retry_on_db_lock(
    func: Callable, max_retries: int = 3, base_delay: float = 0.5
) -> Any:
    """
    Retry an async database operation if it fails due to database lock.
    Uses exponential backoff: 0.5s, 1s, 2s

    Args:
        func: Async function to retry
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds (doubles each retry)

    Returns:
        Result from the function

    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except OperationalError as e:
            last_exception = e
            if "database is locked" in str(e).lower() and attempt < max_retries:
                delay = base_delay * (2**attempt)
                log.warning(
                    f"Database locked, retrying in {delay}s (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(delay)
            else:
                raise

    # This should never be reached, but just in case
    raise last_exception


async def stream_rows(db, *columns, filter_clause=None, batch_size=5000):
    """
    Yield rows in batches using keyset pagination on the first column.

    Unlike stream_results=True (server-side cursors), this approach
    guarantees bounded memory regardless of DB driver or transaction
    configuration.  Each batch executes a fresh LIMIT query.

    IMPORTANT: The first column is used as the keyset cursor and must be
    both **unique** and **non-nullable**.  Non-unique keys can cause rows
    to be silently skipped at batch boundaries (WHERE col > last_key skips
    remaining rows with the same value).  NULLs are excluded automatically
    to prevent infinite re-fetch.

    Args:
        db: SQLAlchemy async session
        *columns: One or more ORM column descriptors to SELECT.
                  The first column is used for ordering/keysetting
                  and MUST be unique (typically a primary key).
        filter_clause: Optional SQLAlchemy filter expression
        batch_size: Number of rows per batch (default 5000)

    Raises:
        ValueError: If no columns are provided or batch_size is invalid

    Yields:
        Row tuples from the query
    """
    if not columns:
        raise ValueError("stream_rows requires at least one column")
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")

    order_col = columns[0]
    base_stmt = select(*columns).where(order_col.isnot(None))
    if filter_clause is not None:
        base_stmt = base_stmt.where(filter_clause)
    base_stmt = base_stmt.order_by(order_col)

    last_key = None
    while True:
        stmt = base_stmt
        if last_key is not None:
            stmt = stmt.where(order_col > last_key)
        stmt = stmt.limit(batch_size)
        result = await db.execute(stmt)
        batch = result.fetchall()
        if not batch:
            break
        # Yield the event loop (and honor the scan throttle) between batches
        await _scan_pace(len(batch))
        for row in batch:
            yield row
        last_key = batch[-1][0]
        if len(batch) < batch_size:
            break


async def _count_rows(db, table, filter_clause=None) -> int:
    """Cheap COUNT(*) used only for progress totals."""
    try:
        stmt = select(func.count()).select_from(table)
        if filter_clause is not None:
            stmt = stmt.where(filter_clause)
        return (await db.execute(stmt)).scalar_one_or_none() or 0
    except Exception:
        return 0


# Direct Open WebUI imports — this module runs inside the Open WebUI process.
from open_webui.models.users import User, Users
from open_webui.models.auths import Auths
from open_webui.models.chats import Chat, Chats, ChatFile
from open_webui.models.chat_messages import ChatMessage
from open_webui.models.messages import Message, MessageReaction, Messages
from open_webui.models.memories import Memory, Memories
from open_webui.models.files import File, Files
from open_webui.models.notes import Note, Notes
from open_webui.models.prompts import Prompt, Prompts
from open_webui.models.models import Model, Models
from open_webui.models.knowledge import Knowledge, Knowledges
from open_webui.models.functions import Function, Functions
from open_webui.models.tools import Tool, Tools
from open_webui.models.skills import Skill, Skills
from open_webui.models.folders import Folder, Folders, FolderModel
from open_webui.internal.db import get_async_db, get_async_db_context
from open_webui.config import CACHE_DIR, UPLOAD_DIR, STORAGE_PROVIDER
from open_webui.config import (
    ENABLE_QDRANT_MULTITENANCY_MODE,
    ENABLE_MILVUS_MULTITENANCY_MODE,
)
from open_webui.storage.provider import Storage

try:
    from open_webui.config import S3_KEY_PREFIX
except ImportError:
    S3_KEY_PREFIX = ""

try:
    from open_webui.models.automations import Automation, AutomationRun
except ImportError:
    Automation = None
    AutomationRun = None

try:
    from open_webui.models.channels import (
        Channel,
        ChannelMember,
        ChannelFile,
        Channels,
    )
except ImportError:
    Channel = ChannelMember = ChannelFile = Channels = None
try:
    from open_webui.models.channels import ChannelWebhook
except ImportError:
    ChannelWebhook = None
try:
    from open_webui.models.access_grants import AccessGrant
except ImportError:
    AccessGrant = None

try:
    from open_webui.retrieval.vector.factory import VECTOR_DB_CLIENT, VECTOR_DB
except ImportError:
    VECTOR_DB_CLIENT = None
    VECTOR_DB = None


def get_sync_engine():
    """VACUUM cannot run inside an async transaction; use the sync engine."""
    from open_webui.internal.db import engine

    return engine



async def get_memory_ids_by_user(active_user_ids: Optional[Set[str]] = None) -> dict:
    """Return {user_id: {memory_id, ...}} for reconciling memory vector points.

    When active_user_ids is given, the result is keyed by exactly those users
    (each with at least an empty set) so callers probe every active user's
    memory collection, including users who deleted all of their memories.
    """

    async def _scan():
        result = {}
        if active_user_ids is not None:
            result = {str(uid): set() for uid in active_user_ids}
        async with get_async_db() as db:
            async for mid, uid in stream_rows(db, Memory.id, Memory.user_id):
                uid_str = str(uid)
                if active_user_ids is not None and uid_str not in result:
                    continue
                result.setdefault(uid_str, set()).add(str(mid))
        return result

    return await retry_on_db_lock(_scan)


async def get_kb_user_map() -> dict:
    """Return {kb_id: user_id} from the knowledge table using lightweight SQL.

    This replaces Knowledges.get_knowledge_bases() which can OOM on large
    databases because SQLAlchemy eager-loads File objects through the
    knowledge_file relationship, pulling hundreds of MB of JSONB into memory.

    Raises on failure — callers (prune execution) must not proceed with an
    empty preservation set, as that could cause over-deletion.
    """

    async def _scan():
        result = {}
        async with get_async_db() as db:
            async for kb_id, uid in stream_rows(db, Knowledge.id, Knowledge.user_id):
                result[str(kb_id)] = str(uid)
        return result

    return await retry_on_db_lock(_scan)


async def get_shared_resource_ids(
    resource_type: str, active_user_ids: Set[str]
) -> Set[str]:
    """Resource ids of the given type that a LIVING principal can still reach.

    A grant keeps a resource shared when its principal is a live user, an
    existing group (groups outlive their members), or the public '*' wildcard.
    Grants pointing only at deleted users or vanished groups do not count, so
    a once-shared resource nobody alive can open is treated as private.
    Raises on unexpected errors: failing open here would delete shared data.
    """
    if AccessGrant is None:
        return set()
    try:
        async with get_async_db_context() as db:
            live_group_ids = set()
            try:
                result = await db.execute(text('SELECT id FROM "group"'))
                live_group_ids = {str(row[0]) for row in result.fetchall()}
            except _TABLE_MISSING_ERRORS as e:
                if not _is_table_missing_error(e):
                    raise

            shared: Set[str] = set()
            result = await db.execute(
                text(
                    "SELECT resource_id, principal_type, principal_id "
                    "FROM access_grant WHERE resource_type = :rt"
                ),
                {"rt": resource_type},
            )
            for rid, ptype, pid in result.fetchall():
                pid_str = str(pid)
                if ptype == "user" and (pid_str == "*" or pid_str in active_user_ids):
                    shared.add(str(rid))
                elif ptype == "group" and pid_str in live_group_ids:
                    shared.add(str(rid))
            return shared
    except _TABLE_MISSING_ERRORS as e:
        if _is_table_missing_error(e):
            log.debug(f"access_grant table does not exist: {e}")
            return set()
        raise


async def get_preserved_kb_ids(form_data, active_user_ids: Set[str]) -> Set[str]:
    """The single KB preservation decision every consumer follows.

    Preserved = owned by a live user, plus ALL ghost KBs when orphaned-KB
    deletion is disabled (the off-flag protects contents, not just the row),
    plus ghost KBs a living principal can still access when the shared
    exemption is on. File references, vector collections, metadata embeddings
    and the deletion loop all consume this one set.
    """
    kb_map = await get_kb_user_map()
    preserved = {kb_id for kb_id, uid in kb_map.items() if uid in active_user_ids}
    ghost = set(kb_map) - preserved

    if not getattr(form_data, "delete_orphaned_knowledge_bases", True):
        return set(kb_map)

    if ghost and getattr(form_data, "exempt_shared_orphaned_knowledge_bases", True):
        shared = await get_shared_resource_ids("knowledge", active_user_ids)
        kept = ghost & shared
        if kept:
            sample = sorted(kept)[:10]
            log.info(
                f"Keeping {len(kept)} ownerless SHARED knowledge bases "
                f"(exempt_shared_orphaned_knowledge_bases): {sample}"
                f"{' ...' if len(kept) > 10 else ''}"
            )
        preserved |= kept
    return preserved


async def get_all_file_row_ids() -> Set[str]:
    """Return the ids of ALL existing file rows.

    Vector collections must follow file rows exactly like storage bytes do: a
    grace-protected or sweep-deferred row keeps its embeddings, otherwise a
    file uploaded minutes before a prune would survive as row and bytes but
    silently lose its vectors. Raises on failure.
    """
    async with get_async_db_context() as db:
        return {str(fid) async for (fid,) in stream_rows(db, File.id)}


async def cleanup_dangling_junction_rows() -> int:
    """Delete chat_file/knowledge_file/channel_file rows whose parent is gone.

    SQLite never enforces the declared ON DELETE CASCADE (Open WebUI does not
    set PRAGMA foreign_keys), so chat/KB/channel deletions strand junction
    rows. Stale chat_file rows are worse than cruft: the reference scan would
    trust them and pin deleted chats' attachments as active forever.
    """
    deleted = 0
    statements = [
        (
            "chat_file",
            "DELETE FROM chat_file WHERE chat_id NOT IN (SELECT id FROM chat)",
        ),
        (
            "knowledge_file",
            "DELETE FROM knowledge_file WHERE knowledge_id NOT IN (SELECT id FROM knowledge)",
        ),
        (
            "channel_file",
            "DELETE FROM channel_file WHERE channel_id NOT IN (SELECT id FROM channel)",
        ),
    ]
    for table, stmt in statements:
        try:
            async with get_async_db_context() as db:
                result = await db.execute(text(stmt))
                await db.commit()
                if result.rowcount and result.rowcount > 0:
                    deleted += result.rowcount
                    log.info(f"Deleted {result.rowcount} dangling {table} rows")
        except _TABLE_MISSING_ERRORS as e:
            if _is_table_missing_error(e):
                log.debug(f"{table} hygiene skipped (table missing): {e}")
            else:
                raise
    return deleted


# API Compatibility Helpers
async def get_all_folders(db: Optional[AsyncSession] = None):
    """
    Get all folders from database.
    Compatibility helper for newer Folders API that doesn't have get_all_folders().

    Args:
        db: Optional database session to reuse (for efficient bulk operations)
    """
    try:
        # Try new API first - if get_all_folders exists, use it
        if hasattr(Folders, "get_all_folders"):
            # Check if the method supports db parameter
            if "db" in inspect.signature(Folders.get_all_folders).parameters:
                return await Folders.get_all_folders(db=db)
            else:
                return await Folders.get_all_folders()

        # Otherwise query directly from database
        async with get_async_db_context(db) as session:
            result = await session.execute(select(Folder))
            folders = result.scalars().all()
            # Convert to FolderModel instances
            return [FolderModel.model_validate(f) for f in folders]
    except Exception as e:
        log.error(f"Error getting all folders: {e}")
        return []


async def count_inactive_users(
    inactive_days: Optional[int],
    exempt_admin: bool,
    exempt_pending: bool,
    all_users=None,
) -> int:
    """Count users that would be deleted for inactivity.

    Args:
        inactive_days: Number of days of inactivity before deletion
        exempt_admin: Whether to exempt admin users
        exempt_pending: Whether to exempt pending users
        all_users: Optional pre-fetched list of users to avoid duplicate queries
    """
    if inactive_days is None:
        return 0

    cutoff_time = int(time.time()) - (inactive_days * 86400)
    count = 0

    try:
        if all_users is not None:
            for user in all_users:
                if exempt_admin and user.role == "admin":
                    continue
                if exempt_pending and user.role == "pending":
                    continue
                if user.last_active_at < cutoff_time:
                    count += 1
            return count

        # No pre-fetched list: SQL COUNT instead of materializing every user
        # row (this path runs on event-triggered rechecks in server contexts).
        # NULL roles must stay counted, matching the Python filter above.
        conditions = [User.last_active_at < cutoff_time]
        if exempt_admin:
            conditions.append(or_(User.role != "admin", User.role == None))
        if exempt_pending:
            conditions.append(or_(User.role != "pending", User.role == None))
        async with get_async_db_context() as db:
            result = await db.execute(
                select(func.count(User.id)).where(and_(*conditions))
            )
            return result.scalar_one_or_none() or 0
    except Exception as e:
        log.debug(f"Error counting inactive users: {e}")

    return count


async def count_old_chats(
    days: Optional[int],
    exempt_archived: bool,
    exempt_in_folders: bool,
    exempt_pinned: bool = False,
) -> int:
    """Count chats that would be deleted by age.

    Uses a SQL COUNT query instead of loading full ORM objects,
    avoiding the expensive deserialization of large JSONB chat columns.
    """
    if days is None:
        return 0

    cutoff_time = int(time.time()) - (days * 86400)

    try:
        async with get_async_db_context() as db:
            # Build filter conditions
            conditions = [Chat.updated_at < cutoff_time]

            if exempt_archived:
                conditions.append(or_(Chat.archived == False, Chat.archived == None))

            if exempt_pinned and hasattr(Chat, "pinned"):
                conditions.append(or_(Chat.pinned == False, Chat.pinned == None))

            if exempt_in_folders:
                folder_conditions = []
                if hasattr(Chat, "folder_id"):
                    folder_conditions.append(Chat.folder_id == None)
                if folder_conditions:
                    conditions.append(and_(*folder_conditions))

            result = await db.execute(
                select(func.count(Chat.id)).where(and_(*conditions))
            )
            return result.scalar_one_or_none() or 0
    except Exception as e:
        log.debug(f"Error counting old chats: {e}")
        return 0


def _knowledge_age_column(age_field: str):
    """Resolve the timestamp column used for KB age comparisons."""
    return Knowledge.updated_at if age_field == "updated_at" else Knowledge.created_at


async def count_old_knowledge_bases(
    days: Optional[int], age_field: str = "created_at"
) -> int:
    """Count knowledge bases that would be deleted by age.

    age_field selects the timestamp: 'created_at' (default) or 'updated_at'.
    This is a retention policy: it targets live, owned, in-use KBs, not orphans.
    """
    # days<=0 would set the cutoff to now and match every KB; never retention-all
    if not days or days <= 0:
        return 0

    cutoff_time = int(time.time()) - (days * 86400)
    age_col = _knowledge_age_column(age_field)

    try:
        async with get_async_db_context() as db:
            result = await db.execute(
                select(func.count(Knowledge.id)).where(age_col < cutoff_time)
            )
            return result.scalar_one_or_none() or 0
    except Exception as e:
        log.debug(f"Error counting old knowledge bases: {e}")
        return 0


async def _dereference_knowledge_from_models(deleted_kb_ids: Set[str]) -> int:
    """Strip deleted KB ids from every model's meta.knowledge list.

    Mirrors Open WebUI's delete_knowledge_by_id router so age-deleted KBs do
    not leave dangling references in workspace models. Best-effort: a failure
    here never blocks KB deletion.
    """
    if not deleted_kb_ids:
        return 0

    updated = 0
    try:
        async with get_async_db() as db:
            async for mid, meta in stream_rows(db, Model.id, Model.meta):
                if not isinstance(meta, dict):
                    continue
                kb_list = meta.get("knowledge")
                if not isinstance(kb_list, list) or not kb_list:
                    continue
                new_list = [
                    k
                    for k in kb_list
                    if not (isinstance(k, dict) and str(k.get("id")) in deleted_kb_ids)
                ]
                if len(new_list) != len(kb_list):
                    new_meta = dict(meta)
                    new_meta["knowledge"] = new_list
                    await db.execute(
                        update(Model).where(Model.id == mid).values(meta=new_meta)
                    )
                    updated += 1
            await db.commit()
        if updated:
            log.info(f"De-referenced deleted knowledge bases from {updated} models")
    except Exception as e:
        log.warning(f"Failed to de-reference knowledge bases from models: {e}")
    return updated


async def delete_old_knowledge_bases(
    days: Optional[int], vector_cleaner, age_field: str = "created_at"
) -> int:
    """Delete knowledge bases older than `days`, by created_at (default) or updated_at.

    DANGER: deletes live, owned, in-use KBs regardless of whether the owner
    still exists — a retention policy, not orphan cleanup. Mirrors Open WebUI's
    own KB deletion: drops the KB vector collection, the KB row, and removes the
    KB from any model's meta.knowledge. The KB's now-unreferenced files are
    reclaimed by the normal orphan sweep that runs afterwards.
    """
    # days<=0 would delete every KB (see count_old_knowledge_bases)
    if not days or days <= 0:
        return 0

    cutoff_time = int(time.time()) - (days * 86400)
    age_col = _knowledge_age_column(age_field)
    deleted = 0
    deleted_ids = []

    try:
        async with get_async_db() as db:
            async for (kb_id,) in stream_rows(
                db, Knowledge.id, filter_clause=(age_col < cutoff_time)
            ):
                _prog_tick()
                try:
                    if vector_cleaner is not None:
                        await asyncio.to_thread(
                            vector_cleaner.delete_collection, kb_id
                        )
                except Exception as e:
                    log.warning(
                        f"Failed to delete vector collection for KB {kb_id}: {e}"
                    )
                await Knowledges.delete_knowledge_by_id(kb_id, db=db)
                deleted_ids.append(str(kb_id))
                deleted += 1
                await db.commit()
                await _pace()
    except Exception as e:
        log.error(f"Error deleting old knowledge bases: {e}")

    if deleted_ids:
        # Remove each KB's metadata embedding from the shared KB-search
        # collection (mirrors Open WebUI's own KB deletion). Best-effort.
        try:
            if vector_cleaner is not None:
                await asyncio.to_thread(
                    vector_cleaner.delete_kb_metadata, deleted_ids
                )
        except Exception as e:
            log.warning(f"Failed to delete KB metadata embeddings: {e}")
        await _dereference_knowledge_from_models(set(deleted_ids))
        log.info(
            f"Deleted {deleted} knowledge bases older than {days} days (by {age_field})"
        )
    return deleted


async def count_orphaned_records(
    form_data: PruneDataForm, active_file_ids: Set[str], active_user_ids: Set[str]
) -> dict:
    """Count orphaned database records that would be deleted.

    Uses SQL COUNT queries instead of loading full ORM objects,
    avoiding the expensive deserialization of large JSONB columns
    (chat history, tool specs, function content, etc.).
    """
    counts = {
        "chats": 0,
        "files": 0,
        "tools": 0,
        "functions": 0,
        "prompts": 0,
        "knowledge_bases": 0,
        "models": 0,
        "notes": 0,
        "skills": 0,
        "folders": 0,
        "chat_messages": 0,
        "automations": 0,
        "automation_runs": 0,
        "channels": 0,
        "channel_messages": 0,
    }

    try:
        async with get_async_db_context() as db:
            # Reference-only and grace-aware, byte-for-byte matching the execute
            # sweep (owner ignored: a departed uploader's still-referenced file
            # is kept). Streamed + filtered in Python to avoid SQL IN() blowing
            # past SQLite's ~999-parameter limit on large instances.
            _prog_stage("Counting orphaned files", await _count_rows(db, File))
            orphaned_file_count = 0
            grace_cutoff = int(time.time()) - max(
                0, int(getattr(form_data, "orphan_file_grace_hours", 0) or 0)
            ) * 3600
            async for fid, _uid, created_at in stream_rows(
                db, File.id, File.user_id, File.created_at
            ):
                _prog_tick()
                if created_at is not None and created_at > grace_cutoff:
                    continue  # freshly uploaded; may not be referenced yet
                if str(fid) not in active_file_ids:
                    orphaned_file_count += 1
            counts["files"] = orphaned_file_count

            # Count other orphaned records by user ownership
            _table_flag_map = [
                ("chats", Chat, Chat.user_id, form_data.delete_orphaned_chats),
                ("tools", Tool, Tool.user_id, form_data.delete_orphaned_tools),
                (
                    "functions",
                    Function,
                    Function.user_id,
                    form_data.delete_orphaned_functions,
                ),
                ("prompts", Prompt, Prompt.user_id, form_data.delete_orphaned_prompts),
                (
                    "knowledge_bases",
                    Knowledge,
                    Knowledge.user_id,
                    form_data.delete_orphaned_knowledge_bases,
                ),
                ("models", Model, Model.user_id, form_data.delete_orphaned_models),
                ("notes", Note, Note.user_id, form_data.delete_orphaned_notes),
                ("skills", Skill, Skill.user_id, form_data.delete_orphaned_skills),
                ("folders", Folder, Folder.user_id, form_data.delete_orphaned_folders),
            ]

            # Shared exemptions: an orphaned resource a LIVING principal can
            # still reach is kept, so it must not be counted either.
            _shared_exempt = {}
            for cnt_key, rtype, enabled_flag, exempt_flag in (
                (
                    "knowledge_bases",
                    "knowledge",
                    form_data.delete_orphaned_knowledge_bases,
                    getattr(form_data, "exempt_shared_orphaned_knowledge_bases", True),
                ),
                (
                    "models",
                    "model",
                    form_data.delete_orphaned_models,
                    getattr(form_data, "exempt_shared_orphaned_models", True),
                ),
                (
                    "prompts",
                    "prompt",
                    form_data.delete_orphaned_prompts,
                    getattr(form_data, "exempt_shared_orphaned_prompts", True),
                ),
                (
                    "tools",
                    "tool",
                    form_data.delete_orphaned_tools,
                    getattr(form_data, "exempt_shared_orphaned_tools", True),
                ),
                (
                    "notes",
                    "note",
                    form_data.delete_orphaned_notes,
                    getattr(form_data, "exempt_shared_orphaned_notes", True),
                ),
                (
                    "skills",
                    "skill",
                    form_data.delete_orphaned_skills,
                    getattr(form_data, "exempt_shared_orphaned_skills", True),
                ),
            ):
                if enabled_flag and exempt_flag and active_user_ids:
                    _shared_exempt[cnt_key] = await get_shared_resource_ids(
                        rtype, active_user_ids
                    )

            for key, table_cls, user_id_col, enabled in _table_flag_map:
                if enabled and active_user_ids:
                    # Stream and filter in Python, matching execution exactly:
                    # SQL IN() binds one parameter per user (breaks past
                    # SQLite's limit on large instances) and SQL NOT IN never
                    # counts NULL owners while execution deletes them.
                    _prog_stage(
                        f"Counting orphaned {key.replace('_', ' ')}",
                        await _count_rows(db, table_cls),
                    )
                    exempt_ids = _shared_exempt.get(key, set())
                    n = 0
                    async for _rid, row_uid in stream_rows(
                        db, table_cls.id, user_id_col
                    ):
                        _prog_tick()
                        if (
                            str(row_uid) not in active_user_ids
                            and str(_rid) not in exempt_ids
                        ):
                            n += 1
                    counts[key] = n

            # Count orphaned chat_messages (chat_id references a chat that no longer exists)
            if form_data.delete_orphaned_chat_messages:
                _prog_stage("Counting orphaned chat messages")
                try:
                    result = await db.execute(
                        select(func.count(ChatMessage.id)).where(
                            not_(ChatMessage.chat_id.in_(select(Chat.id)))
                        )
                    )
                    counts["chat_messages"] = result.scalar_one_or_none() or 0
                except _TABLE_MISSING_ERRORS as e:
                    if _is_table_missing_error(e):
                        log.debug(f"chat_message table does not exist: {e}")
                    else:
                        raise

            # Count orphaned automations and their runs
            if form_data.delete_orphaned_automations and Automation is not None:
                _prog_stage("Counting orphaned automations")
                try:
                    orphaned_auto_count = 0
                    orphaned_auto_ids = set()
                    # Also build the full set of automation IDs during this
                    # scan to reuse for orphaned-run counting below, avoiding
                    # a redundant second table scan.
                    all_auto_ids = set()
                    async for auto_id, auto_uid in stream_rows(
                        db, Automation.id, Automation.user_id
                    ):
                        all_auto_ids.add(auto_id)
                        if str(auto_uid) not in active_user_ids:
                            orphaned_auto_count += 1
                            orphaned_auto_ids.add(auto_id)
                    counts["automations"] = orphaned_auto_count
                except _TABLE_MISSING_ERRORS as e:
                    if _is_table_missing_error(e):
                        log.debug(f"automation table does not exist: {e}")
                        orphaned_auto_ids = set()
                        all_auto_ids = set()
                    else:
                        raise

                # Count orphaned automation_runs: runs whose parent automation
                # no longer exists OR whose parent will be deleted as orphaned.
                # This ensures preview totals match what execution will delete.
                #
                # We stream run IDs and check set membership in Python to
                # avoid SQLite's ~999 parameter limit on large instances.
                if AutomationRun is not None:
                    try:
                        orphaned_run_count = 0
                        async for _, parent_id in stream_rows(
                            db, AutomationRun.id, AutomationRun.automation_id
                        ):
                            if (
                                parent_id is None
                                or parent_id not in all_auto_ids
                                or parent_id in orphaned_auto_ids
                            ):
                                orphaned_run_count += 1
                        counts["automation_runs"] = orphaned_run_count
                    except _TABLE_MISSING_ERRORS as e:
                        if _is_table_missing_error(e):
                            log.debug(f"automation_run table does not exist: {e}")
                        else:
                            raise

            # Count orphaned channels and channel messages together. Messages
            # inside channels that will themselves be deleted as orphaned are
            # included, so preview totals match what execution deletes (the
            # automation counter got the same treatment).
            if (
                form_data.delete_orphaned_channels
                or form_data.delete_orphaned_channel_messages
            ) and Channel is not None:
                _prog_stage("Counting orphaned channels and messages")
                try:
                    all_channel_ids = set()
                    orphan_channel_ids = set()
                    async for ch_id, ch_uid in stream_rows(
                        db, Channel.id, Channel.user_id
                    ):
                        all_channel_ids.add(ch_id)
                        if active_user_ids and str(ch_uid) not in active_user_ids:
                            orphan_channel_ids.add(ch_id)
                    if form_data.delete_orphaned_channels:
                        counts["channels"] = len(orphan_channel_ids)

                    n = 0
                    async for _mid, m_ch_id in stream_rows(
                        db, Message.id, Message.channel_id
                    ):
                        if m_ch_id is None:
                            continue
                        if (
                            form_data.delete_orphaned_channel_messages
                            and m_ch_id not in all_channel_ids
                        ):
                            n += 1
                        elif (
                            form_data.delete_orphaned_channels
                            and m_ch_id in orphan_channel_ids
                        ):
                            n += 1
                    counts["channel_messages"] = n
                except _TABLE_MISSING_ERRORS as e:
                    if _is_table_missing_error(e):
                        log.debug(f"channel/message table does not exist: {e}")
                    else:
                        raise

    except Exception as e:
        log.debug(f"Error counting orphaned records: {e}")

    return counts


async def count_orphaned_chat_messages() -> int:
    """Count orphaned chat_message rows whose parent chat no longer exists.

    These are left behind on SQLite because it does not enforce
    ON DELETE CASCADE unless PRAGMA foreign_keys is enabled.
    """
    try:
        async with get_async_db_context() as db:
            result = await db.execute(
                select(func.count(ChatMessage.id)).where(
                    not_(ChatMessage.chat_id.in_(select(Chat.id)))
                )
            )
            return result.scalar_one_or_none() or 0
    except Exception as e:
        log.debug(f"Error counting orphaned chat_messages: {e}")
        return 0


async def delete_orphaned_chat_messages() -> int:
    """Delete chat_message rows whose parent chat no longer exists.

    Returns the number of rows deleted.
    """
    try:
        async with get_async_db_context() as db:
            # Collect orphaned IDs first
            orphaned_ids = []
            result = await db.execute(
                select(ChatMessage.id).where(
                    not_(ChatMessage.chat_id.in_(select(Chat.id)))
                )
            )
            orphaned_ids = [row[0] for row in result.fetchall()]

            if not orphaned_ids:
                return 0

            # Delete in batches to avoid SQLite variable limits
            deleted = 0
            batch_size = 500
            _prog_tick(0, len(orphaned_ids))
            for i in range(0, len(orphaned_ids), batch_size):
                batch = orphaned_ids[i : i + batch_size]
                result = await db.execute(
                    delete(ChatMessage).where(ChatMessage.id.in_(batch))
                )
                deleted += result.rowcount
                _prog_tick(len(batch))
                await db.commit()
                await _pace(len(batch))
            await db.commit()

            if deleted > 0:
                log.info(f"Deleted {deleted} orphaned chat_message rows")
            return deleted
    except Exception as e:
        log.error(f"Error deleting orphaned chat_messages: {e}")
        return 0


async def _delete_channel_messages_by_ids(db, message_ids: list) -> int:
    """Delete channel `message` rows plus their reactions and channel_file links.

    SQLite-safe (does not rely on FK CASCADE). The attached files themselves are
    cleaned afterwards by the orphaned-file / upload / vector pass, which already
    scans message.data and so drops anything no longer referenced.
    """
    if not message_ids:
        return 0
    deleted = 0
    batch_size = 500
    for i in range(0, len(message_ids), batch_size):
        batch = message_ids[i : i + batch_size]
        if MessageReaction is not None:
            await db.execute(
                delete(MessageReaction).where(MessageReaction.message_id.in_(batch))
            )
        if ChannelFile is not None:
            await db.execute(
                delete(ChannelFile).where(ChannelFile.message_id.in_(batch))
            )
        result = await db.execute(delete(Message).where(Message.id.in_(batch)))
        deleted += result.rowcount or 0
        _prog_tick(len(batch))
        await db.commit()
        await _pace(len(batch))
    return deleted


def _old_channel_message_filter(cutoff_ns: int, exempt_pinned: bool):
    """Build the WHERE clause for age-based channel message pruning."""
    conditions = [
        Message.channel_id.isnot(None),
        Message.created_at.isnot(None),
        Message.created_at < cutoff_ns,
    ]
    if exempt_pinned and hasattr(Message, "is_pinned"):
        conditions.append(or_(Message.is_pinned == False, Message.is_pinned == None))
    return and_(*conditions)


async def count_old_channel_messages(
    max_age_days: Optional[int], exempt_pinned: bool = True
) -> int:
    """Count channel messages older than max_age_days (channel_message.created_at is ns)."""
    if max_age_days is None or Message is None:
        return 0
    cutoff_ns = (int(time.time()) - max_age_days * 86400) * 1_000_000_000
    try:
        async with get_async_db_context() as db:
            result = await db.execute(
                select(func.count(Message.id)).where(
                    _old_channel_message_filter(cutoff_ns, exempt_pinned)
                )
            )
            return result.scalar_one_or_none() or 0
    except _TABLE_MISSING_ERRORS as e:
        if _is_table_missing_error(e):
            log.debug(f"message table does not exist: {e}")
            return 0
        raise
    except Exception as e:
        log.debug(f"Error counting old channel messages: {e}")
        return 0


async def delete_old_channel_messages(
    max_age_days: Optional[int], exempt_pinned: bool = True
) -> int:
    """Delete channel messages older than max_age_days. Pinned messages exempt by default."""
    if max_age_days is None or Message is None:
        return 0
    cutoff_ns = (int(time.time()) - max_age_days * 86400) * 1_000_000_000
    try:
        async with get_async_db_context() as db:
            result = await db.execute(
                select(Message.id).where(
                    _old_channel_message_filter(cutoff_ns, exempt_pinned)
                )
            )
            ids = [row[0] for row in result.fetchall()]
            if not ids:
                return 0
            _prog_tick(0, len(ids))
            deleted = await _delete_channel_messages_by_ids(db, ids)
            await db.commit()
            if deleted > 0:
                log.info(
                    f"Deleted {deleted} channel messages older than {max_age_days} days"
                )
            return deleted
    except _TABLE_MISSING_ERRORS as e:
        if _is_table_missing_error(e):
            log.debug(f"message table does not exist: {e}")
            return 0
        raise
    except Exception as e:
        log.error(f"Error deleting old channel messages: {e}")
        return 0


async def count_orphaned_channel_messages() -> int:
    """Count channel messages whose channel no longer exists (dangling)."""
    if Message is None or Channel is None:
        return 0
    try:
        async with get_async_db_context() as db:
            result = await db.execute(
                select(func.count(Message.id)).where(
                    and_(
                        Message.channel_id.isnot(None),
                        not_(Message.channel_id.in_(select(Channel.id))),
                    )
                )
            )
            return result.scalar_one_or_none() or 0
    except _TABLE_MISSING_ERRORS as e:
        if _is_table_missing_error(e):
            return 0
        raise
    except Exception as e:
        log.debug(f"Error counting orphaned channel messages: {e}")
        return 0


async def delete_orphaned_channel_messages() -> int:
    """Delete channel messages whose channel no longer exists."""
    if Message is None or Channel is None:
        return 0
    try:
        async with get_async_db_context() as db:
            result = await db.execute(
                select(Message.id).where(
                    and_(
                        Message.channel_id.isnot(None),
                        not_(Message.channel_id.in_(select(Channel.id))),
                    )
                )
            )
            ids = [row[0] for row in result.fetchall()]
            if not ids:
                return 0
            _prog_tick(0, len(ids))
            deleted = await _delete_channel_messages_by_ids(db, ids)
            await db.commit()
            if deleted > 0:
                log.info(f"Deleted {deleted} orphaned channel messages")
            return deleted
    except _TABLE_MISSING_ERRORS as e:
        if _is_table_missing_error(e):
            log.debug(f"channel/message table does not exist: {e}")
            return 0
        raise
    except Exception as e:
        log.error(f"Error deleting orphaned channel messages: {e}")
        return 0


async def count_orphaned_channels(active_user_ids: Set[str]) -> int:
    """Count channels whose owner is no longer an active user."""
    if Channel is None or not active_user_ids:
        return 0
    try:
        async with get_async_db_context() as db:
            result = await db.execute(
                select(func.count())
                .select_from(Channel)
                .where(not_(Channel.user_id.in_(active_user_ids)))
            )
            return result.scalar_one_or_none() or 0
    except _TABLE_MISSING_ERRORS as e:
        if _is_table_missing_error(e):
            return 0
        raise
    except Exception as e:
        log.debug(f"Error counting orphaned channels: {e}")
        return 0


async def delete_orphaned_channels(active_user_ids: Set[str]) -> int:
    """Delete channels owned by deleted users, plus their messages, reactions,
    members, file links, webhooks and access grants. Attached files are cleaned
    by the later orphaned-file pass. Returns the number of channels deleted.

    Everything runs on a single session and commits once: the OWUI manager method
    is avoided because it opens a second connection (session sharing may be off),
    which deadlocks SQLite's single writer mid-transaction.
    """
    if Channel is None or not active_user_ids:
        return 0
    try:
        async with get_async_db_context() as db:
            orphan_ids = []
            async for cid, uid in stream_rows(db, Channel.id, Channel.user_id):
                if str(uid) not in active_user_ids:
                    orphan_ids.append(cid)
            if not orphan_ids:
                return 0

            deleted_channels = 0
            batch_size = 200
            for i in range(0, len(orphan_ids), batch_size):
                batch = orphan_ids[i : i + batch_size]

                msg_result = await db.execute(
                    select(Message.id).where(Message.channel_id.in_(batch))
                )
                await _delete_channel_messages_by_ids(
                    db, [row[0] for row in msg_result.fetchall()]
                )

                if ChannelFile is not None:
                    await db.execute(
                        delete(ChannelFile).where(ChannelFile.channel_id.in_(batch))
                    )
                if ChannelMember is not None:
                    await db.execute(
                        delete(ChannelMember).where(ChannelMember.channel_id.in_(batch))
                    )
                if ChannelWebhook is not None:
                    await db.execute(
                        delete(ChannelWebhook).where(
                            ChannelWebhook.channel_id.in_(batch)
                        )
                    )
                if AccessGrant is not None:
                    try:
                        await db.execute(
                            delete(AccessGrant).where(
                                and_(
                                    AccessGrant.resource_type == "channel",
                                    AccessGrant.resource_id.in_(batch),
                                )
                            )
                        )
                    except _TABLE_MISSING_ERRORS as e:
                        if not _is_table_missing_error(e):
                            raise

                result = await db.execute(delete(Channel).where(Channel.id.in_(batch)))
                deleted_channels += result.rowcount or 0
                await db.commit()
                await _pace(len(batch))

            await db.commit()
            if deleted_channels > 0:
                log.info(f"Deleted {deleted_channels} orphaned channels")
            return deleted_channels
    except _TABLE_MISSING_ERRORS as e:
        if _is_table_missing_error(e):
            log.debug(f"channel table does not exist: {e}")
            return 0
        raise
    except Exception as e:
        log.error(f"Error deleting orphaned channels: {e}")
        return 0


def iter_storage_objects() -> Iterator[Tuple[str, str, Optional[int]]]:
    """
    Yield (ref, display_name, size_bytes) for every object in the configured
    storage backend. `ref` matches the format stored in File.path and is safe
    to pass to Storage.delete_file().

    size_bytes is best-effort — may be None for remote backends where listing
    pages don't include a byte count (or it's expensive to fetch per-object).
    """
    provider = (STORAGE_PROVIDER or "local").lower()

    if provider == "local":
        upload_dir = (
            Path(UPLOAD_DIR) if UPLOAD_DIR else (Path(CACHE_DIR).parent / "uploads")
        )
        if not upload_dir.exists():
            return
        for p in upload_dir.iterdir():
            if not p.is_file():
                continue
            try:
                size = p.stat().st_size
            except OSError:
                size = None
            yield (str(p), p.name, size)
        return

    if provider == "s3":
        # Reuse the already-configured boto3 client on the Storage singleton.
        bucket = Storage.bucket_name
        key_prefix = S3_KEY_PREFIX or ""
        paginator = Storage.s3_client.get_paginator("list_objects_v2")
        paginate_kwargs = {"Bucket": bucket}
        if key_prefix:
            paginate_kwargs["Prefix"] = key_prefix
        for page in paginator.paginate(**paginate_kwargs):
            for obj in page.get("Contents", []) or []:
                key = obj["Key"]
                # Mirrors the safety check in S3StorageProvider.delete_all_files
                if key_prefix and not key.startswith(key_prefix):
                    continue
                yield (f"s3://{bucket}/{key}", key.rsplit("/", 1)[-1], obj.get("Size"))
        return

    if provider == "gcs":
        bucket_name = Storage.bucket_name
        for blob in Storage.bucket.list_blobs():
            yield (
                f"gs://{bucket_name}/{blob.name}",
                blob.name,
                getattr(blob, "size", None),
            )
        return

    if provider == "azure":
        endpoint = Storage.endpoint
        container = Storage.container_name
        for blob in Storage.container_client.list_blobs():
            size = None
            try:
                size = blob.size
            except AttributeError:
                pass
            yield (f"{endpoint}/{container}/{blob.name}", blob.name, size)
        return

    log.warning(f"Unknown STORAGE_PROVIDER '{provider}' — orphan storage scan skipped")


async def _get_active_file_paths(active_file_ids: Set[str]) -> Set[str]:
    """Return the storage refs of ALL existing file rows.

    Any file row (referenced or not) protects its storage object; the DB
    orphan pass removes unreferenced rows first, so whatever still has a row
    must keep its bytes. Raises on failure: an empty set here would classify
    EVERY stored object as orphaned and delete it. Paths are also added
    normalized so a non-canonical UPLOAD_DIR (trailing slash, mixed
    separators) cannot make every ref mismatch.
    """
    async with get_async_db_context() as db:
        active_paths: Set[str] = set()
        async for _fid, path in stream_rows(db, File.id, File.path):
            if path:
                active_paths.add(path)
                active_paths.add(os.path.normpath(path))
                # Basename too: after a DATA_DIR/UPLOAD_DIR migration every
                # row carries the old prefix; exact-path matching would then
                # classify ALL local uploads as orphans. Open WebUI's own
                # local delete/get resolve by basename as well.
                active_paths.add(os.path.basename(path))
        return active_paths


async def count_orphaned_uploads(active_file_ids: Set[str]) -> int:
    """Count orphaned objects in the configured storage backend (local/S3/GCS/Azure)."""
    active_paths = await _get_active_file_paths(active_file_ids)

    provider = (STORAGE_PROVIDER or "local").lower()

    def _count() -> int:
        n = 0
        for ref, name, _size in iter_storage_objects():
            _prog_tick()
            if ref in active_paths or name in active_paths:
                continue
            # GCS/Azure delete_file cannot round-trip nested blob names and
            # could target the wrong key; skip them (foreign objects anyway)
            if provider in ("gcs", "azure") and "/" in name:
                continue
            n += 1
        return n

    try:
        return await asyncio.to_thread(_count)
    except Exception as e:
        log.debug(f"Error counting orphaned storage objects: {e}")
        return 0


def count_audio_cache_files(max_age_days: Optional[int]) -> int:
    """Count audio cache files that would be deleted."""
    if max_age_days is None:
        return 0

    cutoff_time = time.time() - (max_age_days * 86400)
    count = 0

    audio_dirs = [
        Path(CACHE_DIR) / "audio" / "speech",
        Path(CACHE_DIR) / "audio" / "transcriptions",
    ]

    for audio_dir in audio_dirs:
        if not audio_dir.exists():
            continue

        try:
            for file_path in audio_dir.iterdir():
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    count += 1
        except Exception as e:
            log.debug(f"Error counting audio files in {audio_dir}: {e}")

    return count


async def get_active_file_ids(
    knowledge_bases=None, active_user_ids=None, preserved_kb_ids=None
) -> Set[str]:
    """
    Get all file IDs that are actively referenced by knowledge bases, chats, folders, messages, and models.

    Uses lightweight SQL queries (streaming only IDs / small columns) to avoid
    loading full ORM objects with large JSONB payload into memory.

    Args:
        knowledge_bases: Deprecated, ignored.  Kept for call-site compatibility.
        active_user_ids: Optional set of active user IDs to filter knowledge bases
        preserved_kb_ids: When given, the exact KB set whose file references
            count (overrides the ownership filter); pass get_preserved_kb_ids()
            so exemptions and the off-flag protect KB contents consistently.
    """
    active_file_ids = set()

    # Defensively normalize to Set[str] — callers may pass UUID objects
    if active_user_ids is not None:
        active_user_ids = {str(uid) for uid in active_user_ids}

    try:
        # Preload all valid file IDs to avoid N database queries during validation.
        # Stream only IDs — never load full File ORM objects (which include large
        # JSONB data/meta columns that cause OOM on large databases).
        _prog_stage("Indexing file rows")

        async def _load_file_ids():
            async with get_async_db() as db:
                return {str(fid) async for (fid,) in stream_rows(db, File.id)}

        all_file_ids = await retry_on_db_lock(_load_file_ids)
        log.debug(f"Preloaded {len(all_file_ids)} file IDs for validation")
        # File ids not shaped like UUIDs (third-party inserts) get a substring
        # match in the text scans below; the UUID regex alone would miss them
        odd_file_ids = tuple(
            fid for fid in all_file_ids if not UUID_PATTERN.match(fid)
        )

        if preserved_kb_ids is not None:
            # CRITICAL: only preserved/active KBs may keep files alive; a KB
            # slated for deletion must not protect its contents, and a KB the
            # preservation decision keeps (off-flag, shared exemption) must.
            active_kb_ids = set(preserved_kb_ids)
        else:
            # Build active KB IDs using lightweight SQL (just id + user_id).
            # Knowledges.get_knowledge_bases() must NOT be used here — on databases
            # with many files it eager-loads File objects through the knowledge_file
            # relationship, pulling hundreds of MB of JSONB into memory.
            kb_user_map = await get_kb_user_map()
            active_kb_ids = set()
            for kb_id, user_id in kb_user_map.items():
                if active_user_ids is None or user_id in active_user_ids:
                    active_kb_ids.add(kb_id)
        log.debug(f"Found {len(active_kb_ids)} active knowledge bases")

        # Query the knowledge_file junction table directly for file IDs.
        # This replaces the N+1 pattern of Knowledges.get_files_by_id() per KB,
        # and avoids loading full File ORM objects (large JSONB data/meta columns).
        _prog_stage("Scanning attachment links")

        async def scan_knowledge_files():
            async with get_async_db() as db:
                result = await db.execute(
                    text("SELECT knowledge_id, file_id FROM knowledge_file")
                )
                kf_count = 0
                while True:
                    rows = result.fetchmany(5000)
                    if not rows:
                        break
                    await _scan_pace(len(rows))
                    _prog_tick(len(rows))
                    for kb_id, file_id in rows:
                        kf_count += 1
                        # Normalize to str — text() queries can return
                        # driver-native types (e.g. uuid.UUID on Postgres)
                        file_id_str = str(file_id) if file_id else None
                        kb_id_str = str(kb_id) if kb_id else None
                        if kb_id_str in active_kb_ids and file_id_str in all_file_ids:
                            active_file_ids.add(file_id_str)
                log.debug(
                    f"Scanned {kf_count} knowledge_file entries for file references"
                )

        try:
            await retry_on_db_lock(scan_knowledge_files)
        except _TABLE_MISSING_ERRORS as e:
            if _is_table_missing_error(e):
                log.debug(
                    f"knowledge_file table does not exist (pre-v0.6.41 schema): {e}"
                )
            else:
                raise  # Transient DB errors must abort, not produce incomplete sets

        # Scan chat_file junction table (cheap — just UUIDs, no JSONB).
        # Since v0.6.41+ chat files are stored in a dedicated junction table.
        # Use fetchmany (not stream_rows) because chat_file.file_id is
        # non-unique — keyset pagination requires a unique cursor column.
        async def scan_chat_files():
            async with get_async_db() as db:
                # JOIN on chat existence: without PRAGMA foreign_keys, SQLite
                # keeps chat_file rows of deleted chats, and trusting them
                # would pin those attachments as active forever.
                result = await db.execute(
                    text(
                        "SELECT cf.file_id FROM chat_file cf "
                        "JOIN chat c ON c.id = cf.chat_id"
                    )
                )
                chat_file_count = 0
                while True:
                    rows = result.fetchmany(5000)
                    if not rows:
                        break
                    await _scan_pace(len(rows))
                    _prog_tick(len(rows))
                    for (file_id,) in rows:
                        chat_file_count += 1
                        # Normalize to str — text() queries can return
                        # driver-native types (e.g. uuid.UUID on Postgres)
                        file_id_str = str(file_id) if file_id else None
                        if file_id_str and file_id_str in all_file_ids:
                            active_file_ids.add(file_id_str)
                log.debug(
                    f"Scanned {chat_file_count} chat_file entries for file references"
                )

        try:
            await retry_on_db_lock(scan_chat_files)
        except _TABLE_MISSING_ERRORS as e:
            if _is_table_missing_error(e):
                log.debug(f"chat_file table does not exist (pre-v0.6.41 schema): {e}")
            else:
                raise  # Transient DB errors must abort, not produce incomplete sets

        # Scan channel_file junction. Channel uploads get their row at upload
        # time; the message may not be posted yet, so Message.data alone would
        # miss them and the upload would be classified orphaned.
        async def scan_channel_files():
            async with get_async_db() as db:
                result = await db.execute(
                    text(
                        "SELECT cf.file_id FROM channel_file cf "
                        "JOIN channel c ON c.id = cf.channel_id"
                    )
                )
                while True:
                    rows = result.fetchmany(5000)
                    if not rows:
                        break
                    await _scan_pace(len(rows))
                    _prog_tick(len(rows))
                    for (file_id,) in rows:
                        file_id_str = str(file_id) if file_id else None
                        if file_id_str and file_id_str in all_file_ids:
                            active_file_ids.add(file_id_str)

        try:
            await retry_on_db_lock(scan_channel_files)
        except _TABLE_MISSING_ERRORS as e:
            if _is_table_missing_error(e):
                log.debug(f"channel_file table does not exist: {e}")
            else:
                raise

        # JSON columns are selected as raw text (CAST) and regex-scanned:
        # no json decode, no dict tree, no event-loop-starving recursion.
        async def scan_text_refs(label, table, id_col, json_cols, batch_size=100):
            async def _scan():
                n = 0
                async with get_async_db() as db:
                    total = await _count_rows(db, table)
                    _prog_stage(label, total)
                    # Buffer the raw JSON texts and regex-scan them in a worker
                    # thread. The match work is CPU-bound; doing it inline would
                    # monopolize this worker's event loop and make the whole app
                    # crawl while a preview or run scans a large database.
                    chunk = []

                    async def _flush():
                        if not chunk:
                            return
                        found = await asyncio.to_thread(
                            _collect_file_ids_from_texts,
                            chunk,
                            all_file_ids,
                            odd_file_ids,
                        )
                        active_file_ids.update(found)
                        chunk.clear()

                    async for row in stream_rows(
                        db,
                        id_col,
                        *[cast(c, Text) for c in json_cols],
                        batch_size=batch_size,
                    ):
                        n += 1
                        _prog_tick()
                        for text_val in row[1:]:
                            if text_val:
                                chunk.append(text_val)
                        if len(chunk) >= batch_size:
                            await _flush()
                    await _flush()
                return n

            try:
                return await retry_on_db_lock(_scan)
            except _TABLE_MISSING_ERRORS as e:
                if _is_table_missing_error(e):
                    log.debug(f"{label} skipped (table missing): {e}")
                    return 0
                raise

        # Always scan legacy chat.chat JSON as well — during upgrades from
        # pre-v0.6.41 databases, some file references may exist only in the
        # JSON column while newer chats use chat_file.  Skipping this when
        # chat_file is non-empty is unsafe for partially-migrated schemas.
        # Each row's JSON can be megabytes, so keep the batch size small.
        chat_count = await scan_text_refs(
            "Scanning chats for file references", Chat, Chat.id, [Chat.chat],
            batch_size=50,
        )
        log.debug(f"Scanned {chat_count} chats (legacy JSON) for file references")

        # Folders (Folder.items/data may not exist on older schemas)
        folder_cols = [c for c in (getattr(Folder, "items", None),
                                   getattr(Folder, "data", None)) if c is not None]
        if folder_cols:
            await scan_text_refs(
                "Scanning folders", Folder, Folder.id, folder_cols
            )
        else:
            log.debug("Folder.items/data attributes not present — skipping folder scan")

        # Standalone (channel) messages
        if hasattr(Message, "data"):
            await scan_text_refs(
                "Scanning channel messages", Message, Message.id, [Message.data]
            )
        else:
            log.debug("Message.data attribute not present — skipping message scan")

        # Models (params and meta fields)
        model_cols = [c for c in (getattr(Model, "params", None),
                                  getattr(Model, "meta", None)) if c is not None]
        if model_cols:
            await scan_text_refs(
                "Scanning models", Model, Model.id, model_cols
            )
        else:
            log.debug("Model.params/meta attributes not present — skipping model scan")

        # Notes store attachments in note.data.files as {"id": ...} entries
        if hasattr(Note, "data"):
            await scan_text_refs(
                "Scanning notes", Note, Note.id, [Note.data]
            )
        else:
            log.debug("Note.data attribute not present — skipping note scan")

        # chat_message mirror (v0.6.41+): redundant with Chat.chat today, cheap
        # insurance should a future version stop mirroring into Chat.chat.
        chat_message_cols = [c for c in (getattr(ChatMessage, "files", None),
                                         getattr(ChatMessage, "content", None)) if c is not None]
        if chat_message_cols:
            await scan_text_refs(
                "Scanning chat messages", ChatMessage, ChatMessage.id, chat_message_cols
            )

    except Exception:
        # Do NOT return an empty set — callers use this for deletion decisions.
        # An empty preservation set would mark ALL files as orphaned.
        raise

    log.info(f"Found {len(active_file_ids)} active file IDs")
    return active_file_ids


async def safe_delete_file_by_id(
    file_id: str, vector_cleaner, db: Optional[AsyncSession] = None
) -> bool:
    """
    Safely delete a file record and its associated vector collections and physical storage.

    This function mirrors the cleanup logic from Open WebUI's delete_file_by_id endpoint:
    1. Cleans KB vector embeddings (filter by file_id and hash)
    2. Deletes the standalone file-{id} vector collection
    3. Deletes the file record from DB (Postgres CASCADEs chat_file/channel_file/
       knowledge_file; SQLite does not enforce FKs, so cleanup_dangling_junction_rows
       sweeps those strays separately)
    4. Deletes the physical file from storage

    Args:
        file_id: The file ID to delete
        vector_cleaner: Vector database cleaner instance
        db: Optional database session to reuse (for efficient bulk operations)

    Returns:
        True if deletion succeeded, False otherwise
    """
    try:
        async with get_async_db_context(db) as session:
            file_record = await Files.get_file_by_id(file_id, db=session)
            if not file_record:
                return True

            # Clean KB vector embeddings (mirrors delete_file_by_id endpoint logic)
            # This removes embeddings from knowledge base collections that reference this file
            try:
                knowledges = await Knowledges.get_knowledges_by_file_id(
                    file_id, db=session
                )
                # Cleaners expose no .delete(); per-point deletion goes through
                # the unified vector client (absent on NoOp deployments).
                client = getattr(vector_cleaner, "vector_db_client", None)
                for kb in knowledges:
                    if client is None:
                        break
                    try:
                        await asyncio.to_thread(
                            client.delete,
                            collection_name=kb.id,
                            filter={"file_id": file_id},
                        )
                        if file_record.hash:
                            await asyncio.to_thread(
                                client.delete,
                                collection_name=kb.id,
                                filter={"hash": file_record.hash},
                            )
                    except Exception as e:
                        log.debug(f"KB embedding cleanup for {kb.id}: {e}")
            except Exception as e:
                log.debug(f"Error getting knowledges for file {file_id}: {e}")

            # Delete the row FIRST, then reclaim bytes/vectors only if it stuck
            # (Files.delete_file_by_id swallows errors and returns False); the
            # reverse order could strand a live row over missing content. Matches
            # Open WebUI's own delete_file_by_id endpoint.
            row_deleted = await Files.delete_file_by_id(file_id, db=session)
            if not row_deleted:
                log.warning(f"File row {file_id} not deleted; keeping its bytes and vectors")
                return False

            await asyncio.to_thread(vector_cleaner.delete_collection, f"file-{file_id}")
            if file_record.path:
                try:
                    await asyncio.to_thread(Storage.delete_file, file_record.path)
                except Exception as e:
                    log.debug(f"Error deleting physical file {file_record.path}: {e}")

            return True

    except Exception as e:
        log.error(f"Error deleting file {file_id}: {e}")
        return False


async def cleanup_orphaned_uploads(active_file_ids: Set[str]) -> int:
    """
    Delete orphaned objects from the configured storage backend
    (local/S3/GCS/Azure). An object is orphaned when its storage ref does
    not match any active File.path in the database.

    Returns the number of objects deleted.
    """
    active_paths = await _get_active_file_paths(active_file_ids)
    deleted_count = 0

    provider = (STORAGE_PROVIDER or "local").lower()

    def _list_orphans():
        return [
            (ref, name)
            for ref, name, _size in iter_storage_objects()
            if ref not in active_paths
            and name not in active_paths
            # GCS/Azure delete_file extracts the key naively (first segment /
            # basename) and would delete a DIFFERENT, possibly live blob for
            # nested names; never touch those.
            and not (provider in ("gcs", "azure") and "/" in name)
        ]

    try:
        orphans = await asyncio.to_thread(_list_orphans)
        _prog_tick(0, len(orphans))
        for ref, name in orphans:
            _prog_tick()
            try:
                await asyncio.to_thread(Storage.delete_file, ref)
                deleted_count += 1
            except Exception as e:
                log.error(f"Failed to delete storage object {name}: {e}")
            await _pace()
    except Exception as e:
        log.error(f"Error scanning storage for orphans: {e}")

    if deleted_count > 0:
        log.info(f"Deleted {deleted_count} orphaned storage objects")

    return deleted_count


async def delete_inactive_users(
    inactive_days: int,
    vector_cleaner=None,
    exempt_admin: bool = True,
    exempt_pending: bool = True,
) -> int:
    """
    Delete users who have been inactive for the specified number of days.

    The user's files are deliberately NOT deleted here: files follow the
    unreferenced-only rule in the orphan sweep, so anything the user uploaded
    into another user's live KB, chat or channel survives, while their own
    now-unreferenced files fall in the orphan pass of the same run.

    Args:
        inactive_days: Number of days of inactivity before deletion
        vector_cleaner: Unused; kept for call-site compatibility
        exempt_admin: Whether to exempt admin users from deletion
        exempt_pending: Whether to exempt pending users from deletion

    Returns the number of users deleted.
    """
    if inactive_days is None:
        return 0

    cutoff_time = int(time.time()) - (inactive_days * 86400)
    deleted_count = 0

    try:
        users_to_delete = []

        # Get all users and check activity
        all_users = (await Users.get_users())["users"]

        for user in all_users:
            # Skip if user is exempt
            if exempt_admin and user.role == "admin":
                continue
            if exempt_pending and user.role == "pending":
                continue

            # Check if user is inactive based on last_active_at
            if user.last_active_at < cutoff_time:
                users_to_delete.append(user)

        # No savepoint: the OWUI managers commit their own sessions in the
        # default (non-session-sharing) configuration, so a savepoint here
        # would contain no work and only feign atomicity.
        _prog_tick(0, len(users_to_delete))
        async with get_async_db() as db:
            for user in users_to_delete:
                _prog_tick()
                try:
                    # Delete user's automations and their runs
                    await delete_user_automations(user.id, db=db)

                    # Auths.delete_auth_by_id wraps Users.delete_user_by_id AND
                    # removes the auth credential row, matching Open WebUI's
                    # own admin delete route; plain Users.delete_user_by_id
                    # would leave email + password hash behind forever.
                    if await Auths.delete_auth_by_id(user.id, db=db):
                        deleted_count += 1
                        await _pace()
                        log.info(
                            f"Deleted inactive user: {user.email} (last active: {user.last_active_at})"
                        )
                    else:
                        log.error(f"Failed to delete user {user.id}")
                except Exception as e:
                    log.error(f"Failed to delete user {user.id}: {e}")

    except Exception as e:
        log.error(f"Error during inactive user deletion: {e}")

    return deleted_count


async def delete_user_automations(
    user_id: str, db: Optional[AsyncSession] = None
) -> int:
    """
    Delete all automations and their runs for a given user.

    Called during user deletion to ensure automation data is cleaned up
    before the user row is removed.

    Args:
        user_id: The user ID whose automations should be deleted
        db: Optional database session to reuse

    Returns:
        Number of automations deleted
    """
    if Automation is None:
        return 0

    owns_session = db is None
    deleted_count = 0
    try:
        async with get_async_db_context(db) as session:
            result = await session.execute(
                select(Automation.id).where(Automation.user_id == user_id)
            )
            automation_ids = [row[0] for row in result.fetchall()]

            if not automation_ids:
                return 0

            # Delete runs for these automations first (batched for SQLite)
            batch_size = 500
            if AutomationRun is not None:
                runs_deleted = 0
                for i in range(0, len(automation_ids), batch_size):
                    batch = automation_ids[i : i + batch_size]
                    result = await session.execute(
                        delete(AutomationRun).where(
                            AutomationRun.automation_id.in_(batch)
                        )
                    )
                    runs_deleted += result.rowcount
            else:
                log.warning("AutomationRun model not available, skipping run cleanup")
                runs_deleted = 0

            # Delete the automations themselves
            result = await session.execute(
                delete(Automation).where(Automation.user_id == user_id)
            )
            deleted_count = result.rowcount

            # Commit unconditionally: get_async_db_context only reuses a passed
            # session when DATABASE_ENABLE_SESSION_SHARING is on (off by
            # default), so with a borrowed session this block may hold its OWN
            # session and skipping the commit silently rolls back the deletes
            # while the success log still prints. Committing a caller's session
            # is safe; OWUI managers commit borrowed sessions too.
            await session.commit()

            if deleted_count > 0:
                log.info(
                    f"Deleted {deleted_count} automations and "
                    f"{runs_deleted} automation runs for user {user_id}"
                )

    except _TABLE_MISSING_ERRORS as e:
        if _is_table_missing_error(e):
            log.debug(f"Automation tables do not exist: {e}")
        elif not owns_session:
            raise  # Let caller handle transaction policy
        else:
            log.warning(f"Error deleting automations for user {user_id}: {e}")
    except Exception as e:
        if not owns_session:
            raise  # Let caller handle transaction policy
        log.warning(f"Error deleting automations for user {user_id}: {e}")

    return deleted_count


async def delete_orphaned_automations(active_user_ids: Set[str]) -> int:
    """
    Delete automation rows whose owner user no longer exists.

    Also deletes associated automation_run rows (best-effort) to avoid
    leaving doubly-orphaned records.  If the automation_run table is
    missing or inaccessible, automation deletion still proceeds.

    Uses stream-and-batch-delete to avoid materializing all orphaned IDs
    in memory at once, preserving scalability on large instances.

    Args:
        active_user_ids: Set of user IDs that still exist

    Returns:
        Number of automations deleted

    Raises:
        Exception on operational errors (non-table-missing)
    """
    if Automation is None:
        return 0

    batch_size = 500

    async def _delete_runs_for_batch(db, batch: list) -> int:
        """Best-effort deletion of automation runs for a batch of automation IDs.

        Returns the number of runs deleted.  If the automation_run table
        does not exist, logs a debug message and returns 0 so automation
        deletion can proceed.
        """
        if AutomationRun is None:
            return 0
        try:
            result = await db.execute(
                delete(AutomationRun).where(AutomationRun.automation_id.in_(batch))
            )
            return result.rowcount
        except _TABLE_MISSING_ERRORS as e:
            if _is_table_missing_error(e):
                log.debug(
                    f"automation_run table not available, skipping run cleanup: {e}"
                )
                return 0
            raise

    try:
        async with get_async_db_context() as db:
            # Stream-and-batch: accumulate IDs up to batch_size, then flush
            # a DELETE before accumulating the next batch.
            total_autos_deleted = 0
            total_runs_deleted = 0
            batch = []

            async for auto_id, auto_uid in stream_rows(
                db, Automation.id, Automation.user_id
            ):
                _prog_tick()
                if str(auto_uid) not in active_user_ids:
                    batch.append(str(auto_id))

                if len(batch) >= batch_size:
                    # Flush: delete runs first (best-effort), then automations
                    total_runs_deleted += await _delete_runs_for_batch(db, batch)
                    result = await db.execute(
                        delete(Automation).where(Automation.id.in_(batch))
                    )
                    total_autos_deleted += result.rowcount
                    await db.commit()
                    await _pace(len(batch))
                    batch.clear()

            # Flush remaining batch
            if batch:
                total_runs_deleted += await _delete_runs_for_batch(db, batch)
                result = await db.execute(
                    delete(Automation).where(Automation.id.in_(batch))
                )
                total_autos_deleted += result.rowcount

            await db.commit()
            await _pace(len(batch))

            if total_autos_deleted > 0:
                log.info(
                    f"Deleted {total_autos_deleted} orphaned automations and "
                    f"{total_runs_deleted} associated automation runs"
                )
            return total_autos_deleted

    except _TABLE_MISSING_ERRORS as e:
        if _is_table_missing_error(e):
            log.debug(f"Automation table does not exist: {e}")
            return 0
        raise


async def delete_orphaned_automation_runs() -> int:
    """
    Delete automation_run rows whose parent automation no longer exists.

    These can be left behind if an automation was deleted without cleaning
    up its runs, or on SQLite where FK CASCADE is not enforced.

    Uses stream-and-batch-delete to avoid materializing all orphaned IDs
    in memory at once.

    Returns:
        Number of automation_run rows deleted

    Raises:
        Exception on operational errors (non-table-missing)
    """
    if AutomationRun is None or Automation is None:
        return 0

    batch_size = 500

    try:
        async with get_async_db_context() as db:
            # Build the set of valid automation IDs for fast lookup.
            # Automation IDs are few relative to runs, so this is safe.
            valid_auto_ids = set()
            async for (aid,) in stream_rows(db, Automation.id):
                valid_auto_ids.add(aid)

            # Stream runs and batch-delete orphans on-the-fly
            deleted = 0
            batch = []

            async for run_id, parent_id in stream_rows(
                db, AutomationRun.id, AutomationRun.automation_id
            ):
                _prog_tick()
                if parent_id is None or parent_id not in valid_auto_ids:
                    batch.append(str(run_id))

                if len(batch) >= batch_size:
                    result = await db.execute(
                        delete(AutomationRun).where(AutomationRun.id.in_(batch))
                    )
                    deleted += result.rowcount
                    await db.commit()
                    await _pace(len(batch))
                    batch.clear()

            # Flush remaining batch
            if batch:
                result = await db.execute(
                    delete(AutomationRun).where(AutomationRun.id.in_(batch))
                )
                deleted += result.rowcount

            await db.commit()
            await _pace(len(batch))

            if deleted > 0:
                log.info(f"Deleted {deleted} orphaned automation_run rows")
            return deleted

    except _TABLE_MISSING_ERRORS as e:
        if _is_table_missing_error(e):
            log.debug(f"Automation tables do not exist: {e}")
            return 0
        raise


async def count_orphaned_memory_rows(active_user_ids) -> int:
    """Count memory rows whose owner no longer exists."""
    try:
        async with get_async_db_context() as db:
            n = 0
            async for _mid, mem_uid in stream_rows(db, Memory.id, Memory.user_id):
                if str(mem_uid) not in active_user_ids:
                    n += 1
            return n
    except Exception as e:
        log.debug(f"Error counting orphaned memory rows: {e}")
        return 0


async def delete_orphaned_memory_rows(active_user_ids) -> int:
    """Delete memory rows whose owner no longer exists.

    Open WebUI's user deletion does not cascade into the memory table, so a
    deleted user's memories linger as rows forever (their vector collection is
    reaped by the general sweep, the rows were not).
    """
    deleted = 0
    try:
        async with get_async_db_context() as db:
            batch = []
            async for mem_id, mem_uid in stream_rows(db, Memory.id, Memory.user_id):
                if str(mem_uid) not in active_user_ids:
                    batch.append(mem_id)
                if len(batch) >= 500:
                    result = await db.execute(delete(Memory).where(Memory.id.in_(batch)))
                    deleted += result.rowcount or 0
                    await db.commit()
                    await _pace(len(batch))
                    batch.clear()
            if batch:
                result = await db.execute(delete(Memory).where(Memory.id.in_(batch)))
                deleted += result.rowcount or 0
                await db.commit()
                await _pace(len(batch))
        if deleted:
            log.info(f"Deleted {deleted} orphaned memory rows")
    except Exception as e:
        log.error(f"Error deleting orphaned memory rows: {e}")
    return deleted


def cleanup_audio_cache(max_age_days: Optional[int] = 30) -> int:
    """
    Clean up audio cache files older than specified days.

    Returns:
        Number of files deleted
    """
    if max_age_days is None:
        log.info("Skipping audio cache cleanup (max_age_days is None)")
        return 0

    cutoff_time = time.time() - (max_age_days * 86400)
    deleted_count = 0
    total_size_deleted = 0

    audio_dirs = [
        Path(CACHE_DIR) / "audio" / "speech",
        Path(CACHE_DIR) / "audio" / "transcriptions",
    ]

    for audio_dir in audio_dirs:
        if not audio_dir.exists():
            continue

        try:
            for file_path in audio_dir.iterdir():
                if not file_path.is_file():
                    continue

                stat_info = file_path.stat()
                file_mtime = stat_info.st_mtime
                if file_mtime < cutoff_time:
                    try:
                        file_size = stat_info.st_size
                        file_path.unlink()
                        deleted_count += 1
                        total_size_deleted += file_size
                        log.debug(
                            f"Deleted audio cache file: {file_path} ({file_size} bytes)"
                        )
                    except Exception as e:
                        log.error(f"Failed to delete audio file {file_path}: {e}")

        except Exception as e:
            log.error(f"Error cleaning audio directory {audio_dir}: {e}")

    log.info(
        f"Audio cache cleanup: deleted {deleted_count} files, freed {total_size_deleted} bytes"
    )
    return deleted_count


# ============================================================================
# Orchestration (from standalone_prune.py run_prune, throttled)
# ============================================================================

async def run_prune(form_data: PruneDataForm) -> dict:
    """Run a prune preview (dry_run) or actual deletion; returns a result dict."""
    # Acquire lock to prevent concurrent operations
    if not PruneLock.acquire():
        return {
            "ok": False,
            "error": "A prune operation is already in progress. Please wait for it to complete.",
        }

    try:
        _prog_begin("preview" if form_data.dry_run else "execute")
        # Get vector database cleaner based on configuration
        vector_cleaner = get_vector_database_cleaner(
            VECTOR_DB,
            VECTOR_DB_CLIENT,
            Path(CACHE_DIR),
            enable_milvus_multitenancy=ENABLE_MILVUS_MULTITENANCY_MODE,
            enable_qdrant_multitenancy=ENABLE_QDRANT_MULTITENANCY_MODE,
        )

        if form_data.dry_run:
            log.info("Starting data pruning preview (dry run)")

            # Get counts for all enabled operations
            _prog_stage("Loading users")
            all_users = (await Users.get_users())["users"]
            active_user_ids = {str(user.id) for user in all_users}
            # Single preservation decision: off-flag and shared exemption
            # protect KB contents (files, vectors, metadata), not just rows
            _prog_stage("Deciding which knowledge bases to keep")
            active_kb_ids = await get_preserved_kb_ids(form_data, active_user_ids)
            active_file_ids = await get_active_file_ids(
                active_user_ids=active_user_ids, preserved_kb_ids=active_kb_ids
            )
            # Vector collections follow file ROWS (like storage bytes), so
            # grace-protected and sweep-deferred rows keep their embeddings
            all_file_row_ids = await get_all_file_row_ids()

            orphaned_counts = await count_orphaned_records(
                form_data, active_file_ids, active_user_ids
            )

            _prog_stage("Counting inactive users")
            inactive_users = await count_inactive_users(
                form_data.delete_inactive_users_days,
                form_data.exempt_admin_users,
                form_data.exempt_pending_users,
                all_users,
            )
            _prog_stage("Counting old chats")
            old_chats = await count_old_chats(
                form_data.days,
                form_data.exempt_archived_chats,
                form_data.exempt_chats_in_folders,
                form_data.exempt_pinned_chats,
            )
            old_knowledge_bases = await count_old_knowledge_bases(
                form_data.delete_knowledge_bases_older_than_days,
                form_data.knowledge_bases_age_field,
            )
            _prog_stage("Scanning storage for orphaned uploads")
            orphaned_uploads = await count_orphaned_uploads(active_file_ids)
            _prog_stage("Scanning vector collections")
            orphaned_vector_collections = await asyncio.to_thread(
                vector_cleaner.count_orphaned_collections,
                all_file_row_ids,
                active_kb_ids,
                active_user_ids,
            )
            _prog_stage("Checking the knowledge-base search index")
            orphaned_kb_metadata = (
                await asyncio.to_thread(
                    vector_cleaner.count_orphaned_kb_metadata, active_kb_ids
                )
                if form_data.delete_orphaned_kb_metadata
                else 0
            )
            orphaned_memories = 0
            if form_data.delete_orphaned_memories:
                memory_ids_by_user = await get_memory_ids_by_user(active_user_ids)
                _prog_stage(
                    "Reconciling memory embeddings", len(memory_ids_by_user)
                )
                orphaned_memories = await asyncio.to_thread(
                    vector_cleaner.count_orphaned_memories, memory_ids_by_user
                ) + await count_orphaned_memory_rows(active_user_ids)
            _prog_stage("Counting audio cache files")
            audio_cache_files = await asyncio.to_thread(
                count_audio_cache_files, form_data.audio_cache_max_age_days
            )
            _prog_stage("Counting old channel messages")
            old_channel_messages = await count_old_channel_messages(
                form_data.channel_message_max_age_days,
                form_data.exempt_pinned_channel_messages,
            )

            result = PrunePreviewResult(
                inactive_users=inactive_users,
                old_chats=old_chats,
                old_knowledge_bases=old_knowledge_bases,
                orphaned_chats=orphaned_counts["chats"],
                orphaned_files=orphaned_counts["files"],
                orphaned_tools=orphaned_counts["tools"],
                orphaned_functions=orphaned_counts["functions"],
                orphaned_prompts=orphaned_counts["prompts"],
                orphaned_knowledge_bases=orphaned_counts["knowledge_bases"],
                orphaned_models=orphaned_counts["models"],
                orphaned_notes=orphaned_counts["notes"],
                orphaned_skills=orphaned_counts["skills"],
                orphaned_folders=orphaned_counts["folders"],
                orphaned_uploads=orphaned_uploads,
                orphaned_vector_collections=orphaned_vector_collections,
                orphaned_kb_metadata=orphaned_kb_metadata,
                orphaned_memories=orphaned_memories,
                audio_cache_files=audio_cache_files,
                orphaned_chat_messages=orphaned_counts["chat_messages"],
                orphaned_automations=orphaned_counts["automations"],
                orphaned_automation_runs=orphaned_counts["automation_runs"],
                old_channel_messages=old_channel_messages,
                orphaned_channels=orphaned_counts["channels"],
                orphaned_channel_messages=orphaned_counts["channel_messages"],
            )

            log.info("Data pruning preview completed")
            return {"ok": True, "dry_run": True, "preview": result}

        # Actual deletion logic (dry_run=False)
        log.info("Starting data pruning process (ACTUAL DELETION)")

        # Stage 0: Delete inactive users (if enabled)
        deleted_users = 0
        if form_data.delete_inactive_users_days is not None:
            _prog_stage("Deleting inactive users")
            log.info(
                f"Deleting users inactive for more than {form_data.delete_inactive_users_days} days"
            )
            deleted_users = await delete_inactive_users(
                form_data.delete_inactive_users_days,
                vector_cleaner,
                form_data.exempt_admin_users,
                form_data.exempt_pending_users,
            )
            if deleted_users > 0:
                log.info(f"Deleted {deleted_users} inactive users")
            else:
                log.info("No inactive users found to delete")
        else:
            log.info("Skipping inactive user deletion (disabled)")

        # Stage 1: Delete old chats — stream IDs only to avoid loading full chat JSON
        if form_data.days is not None:
            cutoff_time = int(time.time()) - (form_data.days * 86400)

            async with get_async_db() as db:
                conditions = Chat.updated_at < cutoff_time
                if form_data.exempt_archived_chats:
                    conditions &= or_(Chat.archived == False, Chat.archived == None)
                if form_data.exempt_pinned_chats and hasattr(Chat, "pinned"):
                    conditions &= or_(Chat.pinned == False, Chat.pinned == None)
                if form_data.exempt_chats_in_folders:
                    if hasattr(Chat, "folder_id"):
                        conditions &= Chat.folder_id == None

                _prog_stage(
                    "Deleting old chats", await _count_rows(db, Chat, conditions)
                )
                deleted = 0
                async for (chat_id,) in stream_rows(
                    db, Chat.id, filter_clause=conditions
                ):
                    # delete_chat_by_id swallows exceptions and returns False
                    if await Chats.delete_chat_by_id(chat_id, db=db):
                        deleted += 1
                    _prog_tick()
                    await db.commit()
                    await _pace()
                if deleted > 0:
                    log.info(
                        f"Deleting {deleted} old chats (older than {form_data.days} days)"
                    )
                else:
                    log.info(f"No chats found older than {form_data.days} days")
        else:
            log.info("Skipping chat deletion (days parameter is None)")

        # Stage 1b: Delete old knowledge bases (age-based retention policy).
        # Runs before the preservation set is built so the KB's now-unreferenced
        # files, uploads and per-file vector collections are reclaimed by the
        # normal orphan sweep in Stages 3-4.
        if form_data.delete_knowledge_bases_older_than_days is not None:
            _prog_stage("Deleting old knowledge bases")
            deleted_old_kbs = await delete_old_knowledge_bases(
                form_data.delete_knowledge_bases_older_than_days,
                vector_cleaner,
                form_data.knowledge_bases_age_field,
            )
            if deleted_old_kbs > 0:
                log.info(
                    f"Deleted {deleted_old_kbs} knowledge bases older than "
                    f"{form_data.delete_knowledge_bases_older_than_days} days "
                    f"(by {form_data.knowledge_bases_age_field})"
                )
            else:
                log.info(
                    f"No knowledge bases found older than "
                    f"{form_data.delete_knowledge_bases_older_than_days} days"
                )
        else:
            log.info("Skipping age-based knowledge base deletion (disabled)")

        # Stage 1c: junction hygiene. SQLite never enforces the declared
        # cascades, so deleted chats/KBs/channels strand junction rows; stale
        # chat_file rows would pin deleted chats' attachments as active forever.
        # Must run BEFORE the preservation set is built.
        _prog_stage("Cleaning junction tables")
        await cleanup_dangling_junction_rows()

        # Stage 2: Build preservation set
        log.info("Building preservation set")

        _prog_stage("Building preservation set")
        active_user_ids = {str(user.id) for user in (await Users.get_users())["users"]}
        log.info(f"Found {len(active_user_ids)} active users")

        active_kb_ids = await get_preserved_kb_ids(form_data, active_user_ids)
        log.info(f"Found {len(active_kb_ids)} preserved knowledge bases")

        active_file_ids = await get_active_file_ids(
            active_user_ids=active_user_ids, preserved_kb_ids=active_kb_ids
        )

        # Shared exemptions for the orphan loops below: resources a living
        # principal can still reach are kept
        shared_models = (
            await get_shared_resource_ids("model", active_user_ids)
            if form_data.delete_orphaned_models
            and form_data.exempt_shared_orphaned_models
            else set()
        )
        shared_prompts = (
            await get_shared_resource_ids("prompt", active_user_ids)
            if form_data.delete_orphaned_prompts
            and form_data.exempt_shared_orphaned_prompts
            else set()
        )
        shared_tools = (
            await get_shared_resource_ids("tool", active_user_ids)
            if form_data.delete_orphaned_tools
            and form_data.exempt_shared_orphaned_tools
            else set()
        )
        shared_notes = (
            await get_shared_resource_ids("note", active_user_ids)
            if form_data.delete_orphaned_notes
            and getattr(form_data, "exempt_shared_orphaned_notes", True)
            else set()
        )
        shared_skills = (
            await get_shared_resource_ids("skill", active_user_ids)
            if form_data.delete_orphaned_skills
            and getattr(form_data, "exempt_shared_orphaned_skills", True)
            else set()
        )

        # Stage 3: Delete orphaned database records
        log.info("Deleting orphaned database records")

        deleted_files = 0
        # A file is orphaned only when unreferenced: a deleted uploader's files
        # can still back another user's live KB or chat. Fresh uploads get a
        # grace window (upload and first reference are separate requests).
        grace_cutoff = int(time.time()) - max(
            0, int(getattr(form_data, "orphan_file_grace_hours", 0) or 0)
        ) * 3600
        async with get_async_db() as db:
            _prog_stage("Sweeping orphaned files", await _count_rows(db, File))
            async for fid, _uid, created_at in stream_rows(
                db, File.id, File.user_id, File.created_at
            ):
                _prog_tick()
                if created_at is not None and created_at > grace_cutoff:
                    continue
                if str(fid) not in active_file_ids:
                    if await safe_delete_file_by_id(fid, vector_cleaner, db=db):
                        deleted_files += 1
                    await db.commit()
                    await _pace()

        if deleted_files > 0:
            log.info(f"Deleted {deleted_files} orphaned files")

        deleted_kbs = 0
        if form_data.delete_orphaned_knowledge_bases:
            _prog_stage("Deleting orphaned knowledge bases")
            deleted_kb_ids = []
            async with get_async_db() as db:
                # Stream ids — get_knowledge_bases() paginates (limit=30) and
                # eager-loads file payloads, silently masking orphans past page 1
                orphan_kb_ids = []
                async for kb_id, owner_id in stream_rows(
                    db, Knowledge.id, Knowledge.user_id
                ):
                    # active_kb_ids folds in live owners, the off-flag and the
                    # shared exemption. The owner_id re-check mirrors the sibling
                    # loops and the count path and closes a TOCTOU window: the
                    # snapshot predates the (long, throttled) file sweep, so a KB
                    # a live user creates mid-pass would otherwise be deleted.
                    if (
                        str(kb_id) not in active_kb_ids
                        and str(owner_id) not in active_user_ids
                    ):
                        orphan_kb_ids.append(str(kb_id))
                _prog_tick(0, len(orphan_kb_ids))
                for kb_id in orphan_kb_ids:
                    _prog_tick()
                    if await asyncio.to_thread(
                        vector_cleaner.delete_collection, kb_id
                    ):
                        await Knowledges.delete_knowledge_by_id(kb_id, db=db)
                        deleted_kb_ids.append(kb_id)
                        deleted_kbs += 1
                        await db.commit()
                        await _pace()

            # Remove each deleted KB's search-metadata embedding too
            if deleted_kb_ids:
                await asyncio.to_thread(
                    vector_cleaner.delete_kb_metadata, deleted_kb_ids
                )
                # Strip the deleted KBs from every model's meta.knowledge, as
                # the age-based KB path already does — ghost-owned KBs can be
                # attached to active users' models.
                await _dereference_knowledge_from_models(set(deleted_kb_ids))

            if deleted_kbs > 0:
                log.info(f"Deleted {deleted_kbs} orphaned knowledge bases")
        else:
            log.info("Skipping knowledge base deletion (disabled)")

        deleted_others = 0

        # Chats — stream IDs + user_ids, filter via Python set membership
        # to avoid SQLite's ~999 parameter limit with NOT IN clauses
        if form_data.delete_orphaned_chats:
            chats_deleted = 0
            async with get_async_db() as db:
                _prog_stage(
                    "Deleting chats of deleted users", await _count_rows(db, Chat)
                )
                async for chat_id, chat_uid in stream_rows(db, Chat.id, Chat.user_id):
                    _prog_tick()
                    if str(chat_uid) not in active_user_ids:
                        if await Chats.delete_chat_by_id(chat_id, db=db):
                            chats_deleted += 1
                            deleted_others += 1
                        await db.commit()
                        await _pace()
            if chats_deleted > 0:
                log.info(f"Deleted {chats_deleted} orphaned chats")
        else:
            log.info("Skipping orphaned chat deletion (disabled)")

        if form_data.delete_orphaned_tools:
            tools_deleted = 0
            _prog_stage("Deleting orphaned tools")
            async with get_async_db() as db:
                for tool in await Tools.get_tools(db=db):
                    _prog_tick()
                    if str(tool.user_id) not in active_user_ids:
                        if str(tool.id) in shared_tools:
                            continue
                        await Tools.delete_tool_by_id(tool.id, db=db)
                        tools_deleted += 1
                        deleted_others += 1
                        await db.commit()
                        await _pace()
            if tools_deleted > 0:
                log.info(f"Deleted {tools_deleted} orphaned tools")
        else:
            log.info("Skipping tool deletion (disabled)")

        if form_data.delete_orphaned_functions:
            functions_deleted = 0
            _prog_stage("Deleting orphaned functions")
            async with get_async_db() as db:
                for function in await Functions.get_functions(db=db):
                    _prog_tick()
                    if str(function.user_id) not in active_user_ids:
                        await Functions.delete_function_by_id(function.id, db=db)
                        functions_deleted += 1
                        deleted_others += 1
                        await db.commit()
                        await _pace()
            if functions_deleted > 0:
                log.info(f"Deleted {functions_deleted} orphaned functions")
        else:
            log.info("Skipping function deletion (disabled)")

        if form_data.delete_orphaned_notes:
            notes_deleted = 0
            _prog_stage("Deleting orphaned notes")
            async with get_async_db() as db:
                # Stream raw columns — Notes.get_notes() paginates (limit=50)
                async for note_id, note_uid in stream_rows(db, Note.id, Note.user_id):
                    _prog_tick()
                    if str(note_uid) not in active_user_ids:
                        if str(note_id) in shared_notes:
                            continue
                        await Notes.delete_note_by_id(note_id, db=db)
                        notes_deleted += 1
                        deleted_others += 1
                        await db.commit()
                        await _pace()
            if notes_deleted > 0:
                log.info(f"Deleted {notes_deleted} orphaned notes")
        else:
            log.info("Skipping note deletion (disabled)")

        if form_data.delete_orphaned_skills:
            skills_deleted = 0
            _prog_stage("Deleting orphaned skills")
            async with get_async_db() as db:
                for skill in await Skills.get_skills(db=db):
                    _prog_tick()
                    if str(skill.user_id) not in active_user_ids:
                        if str(skill.id) in shared_skills:
                            continue
                        await Skills.delete_skill_by_id(skill.id, db=db)
                        skills_deleted += 1
                        deleted_others += 1
                        await db.commit()
                        await _pace()
            if skills_deleted > 0:
                log.info(f"Deleted {skills_deleted} orphaned skills")
        else:
            log.info("Skipping skill deletion (disabled)")

        if form_data.delete_orphaned_prompts:
            prompts_deleted = 0
            _prog_stage("Deleting orphaned prompts")
            async with get_async_db() as db:
                # Stream raw columns — Prompts.get_prompts() validates every row
                # into PromptModel and aborts the run on legacy rows (NULL tags)
                async for _pid, command, prompt_uid in stream_rows(
                    db, Prompt.id, Prompt.command, Prompt.user_id
                ):
                    _prog_tick()
                    if str(prompt_uid) not in active_user_ids:
                        if str(_pid) in shared_prompts:
                            continue
                        await Prompts.delete_prompt_by_command(command, db=db)
                        prompts_deleted += 1
                        deleted_others += 1
                        await db.commit()
                        await _pace()
            if prompts_deleted > 0:
                log.info(f"Deleted {prompts_deleted} orphaned prompts")
        else:
            log.info("Skipping prompt deletion (disabled)")

        if form_data.delete_orphaned_models:
            models_deleted = 0
            _prog_stage("Deleting orphaned models")
            async with get_async_db() as db:
                for model in await Models.get_all_models(db=db):
                    _prog_tick()
                    if str(model.user_id) not in active_user_ids:
                        if str(model.id) in shared_models:
                            continue
                        await Models.delete_model_by_id(model.id, db=db)
                        models_deleted += 1
                        deleted_others += 1
                        await db.commit()
                        await _pace()
            if models_deleted > 0:
                log.info(f"Deleted {models_deleted} orphaned models")
        else:
            log.info("Skipping model deletion (disabled)")

        if form_data.delete_orphaned_folders:
            folders_deleted = 0
            _prog_stage("Deleting orphaned folders")
            async with get_async_db() as db:
                for folder in await get_all_folders(db=db):
                    _prog_tick()
                    if str(folder.user_id) not in active_user_ids:
                        await Folders.delete_folder_by_id_and_user_id(
                            folder.id, folder.user_id, db=db
                        )
                        folders_deleted += 1
                        deleted_others += 1
                        await db.commit()
                        await _pace()
            if folders_deleted > 0:
                log.info(f"Deleted {folders_deleted} orphaned folders")
        else:
            log.info("Skipping folder deletion (disabled)")

        if deleted_others > 0:
            log.info(f"Total other orphaned records deleted: {deleted_others}")

        # Stage 3b: Delete orphaned chat messages
        if form_data.delete_orphaned_chat_messages:
            _prog_stage("Deleting orphaned chat messages")
            deleted_chat_messages = await delete_orphaned_chat_messages()
            if deleted_chat_messages > 0:
                log.info(f"Deleted {deleted_chat_messages} orphaned chat messages")
        else:
            log.info("Skipping orphaned chat_message deletion (disabled)")

        # Stage 3c: Delete orphaned automations and automation runs
        if form_data.delete_orphaned_automations:
            _prog_stage("Deleting orphaned automations")
            deleted_automations = await delete_orphaned_automations(active_user_ids)
            if deleted_automations > 0:
                log.info(f"Deleted {deleted_automations} orphaned automations")

            deleted_automation_runs = await delete_orphaned_automation_runs()
            if deleted_automation_runs > 0:
                log.info(f"Deleted {deleted_automation_runs} orphaned automation runs")
        else:
            log.info("Skipping orphaned automation deletion (disabled)")

        # Stage 3d: Channel pruning. Runs before Stage 4 so that files attached to
        # pruned channel content become unreferenced and get cleaned below.
        if form_data.delete_orphaned_channels:
            _prog_stage("Deleting orphaned channels")
            deleted_channels = await delete_orphaned_channels(active_user_ids)
            if deleted_channels > 0:
                log.info(f"Deleted {deleted_channels} orphaned channels")
        else:
            log.info("Skipping orphaned channel deletion (disabled)")

        if form_data.delete_orphaned_channel_messages:
            _prog_stage("Deleting orphaned channel messages")
            deleted_ch_msgs = await delete_orphaned_channel_messages()
            if deleted_ch_msgs > 0:
                log.info(f"Deleted {deleted_ch_msgs} orphaned channel messages")
        else:
            log.info("Skipping orphaned channel message deletion (disabled)")

        if form_data.channel_message_max_age_days is not None:
            _prog_stage("Deleting old channel messages")
            deleted_old_ch_msgs = await delete_old_channel_messages(
                form_data.channel_message_max_age_days,
                form_data.exempt_pinned_channel_messages,
            )
            if deleted_old_ch_msgs > 0:
                log.info(
                    f"Deleted {deleted_old_ch_msgs} channel messages older than "
                    f"{form_data.channel_message_max_age_days} days"
                )
        else:
            log.info("Skipping age-based channel message deletion (disabled)")

        # Stage 4: Clean up orphaned physical files and vector collections.
        # Recompute preservation sets after Stage 3 deletions — files that
        # were only referenced by now-deleted chats/KBs should no longer
        # be considered active.  This is safe with the streaming-based
        # get_active_file_ids() that replaced the OOM-prone ORM version.
        log.info("Recomputing preservation sets after deletions")
        _prog_stage("Recomputing preservation set")
        active_user_ids = {str(user.id) for user in (await Users.get_users())["users"]}
        active_kb_ids = await get_preserved_kb_ids(form_data, active_user_ids)
        active_file_ids = await get_active_file_ids(
            active_user_ids=active_user_ids, preserved_kb_ids=active_kb_ids
        )
        # Vector collections follow file ROWS (like storage bytes): any row
        # that survived stage 3 (referenced, grace-protected, or deferred to
        # the next run) keeps its embeddings.
        all_file_row_ids = await get_all_file_row_ids()

        log.info("Cleaning up orphaned physical files")

        _prog_stage("Deleting orphaned uploads from storage")
        deleted_uploads = await cleanup_orphaned_uploads(active_file_ids)
        if deleted_uploads > 0:
            log.info(f"Deleted {deleted_uploads} orphaned upload files")

        # Audio cache cleanup
        if form_data.audio_cache_max_age_days is not None:
            _prog_stage("Cleaning audio cache")
            log.info(
                f"Cleaning audio cache files older than {form_data.audio_cache_max_age_days} days"
            )
            await asyncio.to_thread(
                cleanup_audio_cache, form_data.audio_cache_max_age_days
            )

        # Use modular vector database cleanup
        _prog_stage("Cleaning vector collections")
        warnings = []
        deleted_vector_count, vector_error = await asyncio.to_thread(
            vector_cleaner.cleanup_orphaned_collections,
            all_file_row_ids,
            active_kb_ids,
            active_user_ids,
        )
        if vector_error:
            warnings.append(f"Vector cleanup warning: {vector_error}")
            log.warning(f"Vector cleanup completed with errors: {vector_error}")

        # Clean orphaned KB metadata embeddings (KBs deleted outside the tool,
        # or by older versions that did not remove the metadata entry).
        if form_data.delete_orphaned_kb_metadata:
            _prog_stage("Cleaning the knowledge-base search index")
            deleted_kb_meta = await asyncio.to_thread(
                vector_cleaner.cleanup_orphaned_kb_metadata, active_kb_ids
            )
            if deleted_kb_meta > 0:
                log.info(f"Deleted {deleted_kb_meta} orphaned KB metadata embeddings")
        else:
            log.info("Skipping orphaned KB metadata cleanup (disabled)")

        # Clean orphaned memories (memories deleted by active users that
        # left their vector point behind).
        if form_data.delete_orphaned_memories:
            await delete_orphaned_memory_rows(active_user_ids)
            memory_ids_by_user = await get_memory_ids_by_user(active_user_ids)
            _prog_stage("Reconciling memory embeddings", len(memory_ids_by_user))
            deleted_mem = await asyncio.to_thread(
                vector_cleaner.cleanup_orphaned_memories, memory_ids_by_user
            )
            if deleted_mem > 0:
                log.info(f"Deleted {deleted_mem} orphaned memories")
        else:
            log.info("Skipping orphaned memory cleanup (disabled)")

        # Stage 5: Database optimization (optional)
        #
        # VACUUM is a DDL/maintenance command that CANNOT run inside a
        # transaction.  The async engine always opens a transaction, so we
        # use the sync engine directly with a raw DBAPI connection in
        # autocommit mode.  The sync engine is retained by Open WebUI
        # specifically for startup and maintenance tasks.
        if form_data.run_vacuum:
            _prog_stage("Running VACUUM")
            await asyncio.to_thread(_run_vacuum_sync, vector_cleaner)
        else:
            log.info("Skipping VACUUM optimization (not enabled)")

        # Log any warnings collected during pruning
        if warnings:
            log.warning(f"Data pruning completed with warnings: {'; '.join(warnings)}")

        log.info("Data pruning completed successfully")
        return {"ok": True, "dry_run": False, "warnings": warnings}

    except Exception as e:
        log.exception(f"Error during data pruning: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        # Always release lock, even if operation fails
        _prog_end()
        PruneLock.release()


# ============================================================================
# Event plugin layer: valves, single-worker election, event routing,
# manual admin UI + API (same deletion engine as the automatic passes)
# ============================================================================

PLUGIN_VERSION = "0.10.6"
MAX_RUN_LOG_LINES = 4000
MAX_RUNS_KEPT = 20

_STATE = {
    "started": False,
    "lock": None,          # in-process: never run two passes concurrently
    "claims": {},          # local claim fallback when Redis is unavailable
    "tasks": set(),        # keep task refs so passes are not garbage-collected
    "runs": [],            # manual run history for the UI
    "redis": None,
    "redis_prefix": "open-webui",
    "redis_tried": False,
}


def _redis():
    if _STATE["redis_tried"]:
        return _STATE["redis"]
    _STATE["redis_tried"] = True
    try:
        from open_webui.env import REDIS_URL, REDIS_KEY_PREFIX

        try:
            from open_webui.env import (
                REDIS_CLUSTER,
                REDIS_SENTINEL_HOSTS,
                REDIS_SENTINEL_PORT,
            )
        except ImportError:
            REDIS_CLUSTER, REDIS_SENTINEL_HOSTS, REDIS_SENTINEL_PORT = False, "", ""
        from open_webui.utils.redis import get_redis_connection

        sentinels = []
        try:
            from open_webui.utils.redis import get_sentinels_from_env

            sentinels = get_sentinels_from_env(REDIS_SENTINEL_HOSTS, REDIS_SENTINEL_PORT)
        except Exception:
            pass

        if REDIS_URL or sentinels:
            _STATE["redis"] = get_redis_connection(
                REDIS_URL,
                redis_sentinels=sentinels,
                redis_cluster=bool(REDIS_CLUSTER),
                decode_responses=True,
            )
            _STATE["redis_prefix"] = REDIS_KEY_PREFIX or "open-webui"
            log.info("prune: using Redis for cross-worker coordination")
    except Exception as e:
        log.warning(f"prune: Redis unavailable, falling back to per-worker claims: {e}")
    return _STATE["redis"]


def _claim(key: str, ttl_seconds: int) -> bool:
    """Atomically claim a prune pass for this worker (Redis SET NX EX).

    Exactly one worker across all replicas gets True within the ttl window; the
    ttl doubles as the cooldown between event-triggered rechecks. Falls back to
    an in-process expiry map when Redis is not configured (single-worker setups).
    """
    ttl = max(1, int(ttl_seconds))
    r = _redis()
    if r is not None:
        try:
            return bool(
                r.set(f"{_STATE['redis_prefix']}:prune:{key}", "1", nx=True, ex=ttl)
            )
        except Exception as e:
            log.warning(f"prune: Redis claim failed, using local fallback: {e}")
    now = time.time()
    if _STATE["claims"].get(key, 0) > now:
        return False
    _STATE["claims"][key] = now + ttl
    return True


# ---- global run lock ----
# The file-based PruneLock only serializes within one node (each replica has
# its own CACHE_DIR, even on S3-storage deployments). When Redis is available,
# layer a cross-replica lock on top and rebind PruneLock so every call site
# (run_prune, targeted passes, manual runs) gets global exclusion for free.

RUN_LOCK_TTL = int(PruneLock.LOCK_TIMEOUT.total_seconds())
_RUN_LOCK_TOKEN = {"value": None}


def _redis_run_lock_acquire() -> bool:
    r = _redis()
    if r is None:
        return True  # no Redis: the per-node file lock is all we can do
    token = uuid.uuid4().hex
    key = f"{_STATE['redis_prefix']}:prune:running"
    try:
        if r.set(key, token, nx=True, ex=RUN_LOCK_TTL):
            _RUN_LOCK_TOKEN["value"] = token
            return True
        log.info("prune: another replica holds the global prune lock")
        return False
    except Exception as e:
        log.warning(f"prune: Redis run lock failed, relying on file lock only: {e}")
        return True


def _redis_run_lock_release() -> None:
    r = _redis()
    token = _RUN_LOCK_TOKEN["value"]
    _RUN_LOCK_TOKEN["value"] = None
    if r is None or not token:
        return
    key = f"{_STATE['redis_prefix']}:prune:running"
    try:
        if r.get(key) == token:  # never delete a lock another replica owns
            r.delete(key)
    except Exception as e:
        log.warning(f"prune: Redis run lock release failed (expires in {RUN_LOCK_TTL}s): {e}")


async def _lock_heartbeat():
    """Refresh both locks every 10 min so a slow throttled pass never outlives
    the 2h TTL/staleness cutoff and loses exclusivity mid-run."""
    key = f"{_STATE['redis_prefix']}:prune:running"
    while True:
        await asyncio.sleep(600)
        token = _RUN_LOCK_TOKEN["value"]
        r = _redis()
        if r is not None and token:
            try:
                if r.get(key) == token:
                    r.expire(key, RUN_LOCK_TTL)
            except Exception as e:
                log.debug(f"prune: redis lock heartbeat failed: {e}")
        try:
            if PruneLock.LOCK_FILE is not None and PruneLock.LOCK_FILE.exists():
                data = json.loads(PruneLock.LOCK_FILE.read_text())
                data["timestamp"] = datetime.utcnow().isoformat()
                PruneLock.LOCK_FILE.write_text(json.dumps(data))
        except Exception as e:
            log.debug(f"prune: file lock heartbeat failed: {e}")


_file_lock_acquire = PruneLock.acquire
_file_lock_release = PruneLock.release


def _combined_lock_acquire() -> bool:
    token_before = _RUN_LOCK_TOKEN["value"]
    if not _redis_run_lock_acquire():
        return False
    if not _file_lock_acquire():
        # Release only what THIS call acquired: on a Redis-exception fallback
        # the token slot still belongs to the active holder, and releasing it
        # here would delete the live global lock out from under a running pass.
        if _RUN_LOCK_TOKEN["value"] != token_before:
            _redis_run_lock_release()
        return False
    try:
        _RUN_LOCK_TOKEN["hb"] = asyncio.get_running_loop().create_task(_lock_heartbeat())
    except RuntimeError:
        _RUN_LOCK_TOKEN["hb"] = None
    return True


def _combined_lock_release() -> None:
    hb = _RUN_LOCK_TOKEN.pop("hb", None)
    if hb:
        hb.cancel()
    _file_lock_release()
    _redis_run_lock_release()


PruneLock.acquire = _combined_lock_acquire
PruneLock.release = _combined_lock_release


def _unclaim(key: str) -> None:
    """Undo a claim whose pass never ran, so the cooldown isn't burned."""
    r = _redis()
    if r is not None:
        try:
            r.delete(f"{_STATE['redis_prefix']}:prune:{key}")
            return
        except Exception as e:
            log.debug(f"prune: unclaim of '{key}' failed: {e}")
    _STATE["claims"].pop(key, None)


def _spawn(name: str, factory, on_skip=None):
    """Run a prune pass as a background task, one at a time per worker."""

    async def runner():
        lock = _STATE["lock"]
        if lock.locked():
            log.info(f"prune: skipping '{name}' pass, another pass is running")
            if on_skip:
                on_skip()
            return
        async with lock:
            try:
                await factory()
            except Exception:
                log.exception(f"prune: '{name}' pass failed")

    task = asyncio.create_task(runner())
    _STATE["tasks"].add(task)
    task.add_done_callback(_STATE["tasks"].discard)


def _days(value) -> Optional[int]:
    """Valve convention: 0 or empty means disabled."""
    try:
        value = int(value or 0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _make_cleaner():
    return get_vector_database_cleaner(
        VECTOR_DB,
        VECTOR_DB_CLIENT,
        Path(CACHE_DIR),
        enable_milvus_multitenancy=ENABLE_MILVUS_MULTITENANCY_MODE,
        enable_qdrant_multitenancy=ENABLE_QDRANT_MULTITENANCY_MODE,
    )


def _form_from_valves(v: dict) -> PruneDataForm:
    return PruneDataForm(
        days=_days(v["chat_max_age_days"]),
        exempt_archived_chats=v["exempt_archived_chats"],
        exempt_pinned_chats=v["exempt_pinned_chats"],
        exempt_chats_in_folders=v["exempt_chats_in_folders"],
        delete_knowledge_bases_older_than_days=_days(
            v.get("knowledge_base_max_age_days", v.get("kb_max_age_days", 0))
        ),
        knowledge_bases_age_field=(
            "updated_at"
            if v.get("knowledge_base_age_basis", v.get("kb_age_field")) == "updated_at"
            else "created_at"
        ),
        delete_orphaned_chats=v["delete_orphaned_chats"],
        delete_orphaned_tools=v["delete_orphaned_tools"],
        delete_orphaned_functions=v.get("delete_orphaned_functions", False),
        delete_orphaned_prompts=v["delete_orphaned_prompts"],
        delete_orphaned_knowledge_bases=v["delete_orphaned_knowledge_bases"],
        exempt_shared_orphaned_knowledge_bases=v.get("exempt_shared_orphaned_knowledge_bases", True),
        exempt_shared_orphaned_models=v.get("exempt_shared_orphaned_models", True),
        exempt_shared_orphaned_prompts=v.get("exempt_shared_orphaned_prompts", True),
        exempt_shared_orphaned_tools=v.get("exempt_shared_orphaned_tools", True),
        delete_orphaned_kb_metadata=v.get(
            "delete_orphaned_knowledge_base_metadata",
            v.get("delete_orphaned_kb_metadata", True),
        ),
        delete_orphaned_memories=v["delete_orphaned_memories"],
        delete_orphaned_models=v["delete_orphaned_models"],
        delete_orphaned_notes=v["delete_orphaned_notes"],
        exempt_shared_orphaned_notes=v.get("exempt_shared_orphaned_notes", True),
        exempt_shared_orphaned_skills=v.get("exempt_shared_orphaned_skills", True),
        delete_orphaned_skills=v["delete_orphaned_skills"],
        delete_orphaned_folders=v["delete_orphaned_folders"],
        delete_orphaned_chat_messages=v["delete_orphaned_chat_messages"],
        delete_orphaned_automations=v["delete_orphaned_automations"],
        channel_message_max_age_days=_days(v["channel_message_max_age_days"]),
        exempt_pinned_channel_messages=v["exempt_pinned_channel_messages"],
        delete_orphaned_channels=v["delete_orphaned_channels"],
        delete_orphaned_channel_messages=v["delete_orphaned_channel_messages"],
        audio_cache_max_age_days=_days(v["audio_cache_max_age_days"]),
        orphan_file_grace_hours=max(0, int(v.get("orphan_file_grace_hours", 24) or 0)),
        delete_inactive_users_days=_days(v["inactive_user_days"]),
        exempt_admin_users=v["exempt_admin_users"],
        exempt_pending_users=v["exempt_pending_users"],
        run_vacuum=False,  # vacuum only ever runs via the one-shot valve
        # Automatic passes DELETE FOR REAL; the manual preview endpoint sets
        # dry_run explicitly. The master switch is the safety gate.
        dry_run=False,
    )


# ---- targeted passes (cheap, event-triggered; no whole-database scans) ----


async def _delete_old_chats_paced(
    days: int, exempt_archived: bool, exempt_pinned: bool, exempt_in_folders: bool
) -> int:
    cutoff_time = int(time.time()) - (days * 86400)
    async with get_async_db() as db:
        conditions = Chat.updated_at < cutoff_time
        if exempt_archived:
            conditions &= or_(Chat.archived == False, Chat.archived == None)
        if exempt_pinned and hasattr(Chat, "pinned"):
            conditions &= or_(Chat.pinned == False, Chat.pinned == None)
        if exempt_in_folders and hasattr(Chat, "folder_id"):
            conditions &= Chat.folder_id == None

        deleted = 0
        async for (chat_id,) in stream_rows(db, Chat.id, filter_clause=conditions):
            # delete_chat_by_id swallows exceptions and returns False
            if await Chats.delete_chat_by_id(chat_id, db=db):
                deleted += 1
            await db.commit()  # release the write lock before sleeping
            await _pace()
    if deleted:
        log.info(f"Deleted {deleted} chats older than {days} days")
    return deleted


async def _pass_chats(v: dict):
    chat_days = _days(v["chat_max_age_days"])
    ch_msg_days = _days(v["channel_message_max_age_days"])
    if chat_days is None and ch_msg_days is None:
        return

    if not PruneLock.acquire():
        log.info("prune: chats pass skipped, prune lock held")
        return
    try:
        if chat_days is not None:
            await _delete_old_chats_paced(
                chat_days,
                v["exempt_archived_chats"],
                v["exempt_pinned_chats"],
                v["exempt_chats_in_folders"],
            )
        if ch_msg_days is not None:
            await delete_old_channel_messages(
                ch_msg_days, v["exempt_pinned_channel_messages"]
            )
    finally:
        PruneLock.release()


async def _pass_users(v: dict):
    inactive_days = _days(v["inactive_user_days"])
    if inactive_days is None:
        return

    if not PruneLock.acquire():
        log.info("prune: users pass skipped, prune lock held")
        return
    try:
        await delete_inactive_users(
            inactive_days,
            _make_cleaner(),
            v["exempt_admin_users"],
            v["exempt_pending_users"],
        )
    finally:
        PruneLock.release()


async def _pass_full(v: dict):
    """Full sweep: everything configured, incl. orphan + vector + storage cleanup."""
    form_data = _form_from_valves(v)
    outcome = await run_prune(form_data)
    if not outcome.get("ok"):
        log.error(f"prune: full pass failed: {outcome.get('error')}")


# ---- one-shot VACUUM (sync body from standalone Stage 5, run in a thread) ----


def _run_vacuum_sync(vector_cleaner):
    log.info(
        "Optimizing database with VACUUM (this may take a while and lock the database)"
    )
    try:
        engine = get_sync_engine()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            if "postgresql" in str(engine.url):
                conn.execute(text("VACUUM ANALYZE"))
                log.info("Vacuumed PostgreSQL main database")
            else:
                conn.execute(text("VACUUM"))
                log.info("Vacuumed SQLite main database")
    except Exception as e:
        log.error(f"Failed to vacuum main database: {e}")

    if isinstance(vector_cleaner, ChromaDatabaseCleaner):
        try:
            with sqlite3.connect(str(vector_cleaner.chroma_db_path)) as conn:
                conn.execute("VACUUM")
                log.info("Vacuumed ChromaDB database")
        except Exception as e:
            log.error(f"Failed to vacuum ChromaDB database: {e}")
    elif isinstance(vector_cleaner, PGVectorDatabaseCleaner) and vector_cleaner.session:
        try:
            pg_engine = vector_cleaner.session.get_bind()
            with pg_engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as pg_conn:
                pg_conn.execute(text("VACUUM ANALYZE"))
                log.info("Executed VACUUM ANALYZE on PostgreSQL vector database")
        except Exception as e:
            log.error(f"Failed to vacuum PostgreSQL vector database: {e}")


def _full_sweep_ttl(v: dict) -> int:
    hours = int(v["full_sweep_interval_hours"] or 0)
    return hours * 3600 if hours > 0 else 600


# ---- manual runs (UI/API); same engine, with per-run log capture ----


class _RunLogHandler(logging.Handler):
    """Captures this module's log lines into a run record for the UI."""

    def __init__(self, sink: list):
        super().__init__(logging.INFO)
        self.sink = sink

    def emit(self, record):
        try:
            ts = datetime.utcnow().strftime("%H:%M:%S")
            self.sink.append(f"{ts} {record.levelname} {record.getMessage()}")
            if len(self.sink) > MAX_RUN_LOG_LINES:
                del self.sink[: len(self.sink) - MAX_RUN_LOG_LINES]
                self.sink[0] = "... (older log lines truncated)"
        except Exception:
            pass


def _run_summary(run: dict, log_tail: int = 0) -> dict:
    out = {k: v for k, v in run.items() if k != "log"}
    out["log_lines"] = len(run["log"])
    out["log"] = run["log"][-log_tail:] if log_tail else run["log"]
    if run["status"] == "running" and _PROGRESS.get("active"):
        out["progress"] = dict(_PROGRESS)
    return out


def _rate_override(body: dict, key: str):
    """Optional per-run speed override; non-negative int or None."""
    try:
        value = int(body.get(key))
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


async def _manual_execute(form_data: "PruneDataForm", run: dict, rates: dict = None):
    handler = _RunLogHandler(run["log"])
    log.addHandler(handler)
    rates = rates or {}
    _PACE["run_rows_per_second"] = rates.get("deletion_rows_per_second")
    _PACE["run_scan_rows_per_second"] = rates.get("scan_rows_per_second")
    try:
        outcome = await run_prune(form_data)
        if outcome.get("ok") and outcome.get("dry_run"):
            # Store the UI-ready payload; PrunePreviewResult itself is not JSON
            preview = outcome["preview"]
            run["result"] = {
                "ok": True,
                "dry_run": True,
                "total": preview.total_items(),
                "summary": preview.get_summary_dict(),
                "detail": preview.model_dump(),
            }
        else:
            run["result"] = outcome
        run["status"] = "done" if outcome.get("ok") else "failed"
    except Exception as e:
        log.exception(f"Prune run failed: {e}")
        run["result"] = {"ok": False, "error": str(e)}
        run["status"] = "failed"
    finally:
        _PACE["run_rows_per_second"] = None
        _PACE["run_scan_rows_per_second"] = None
        log.removeHandler(handler)
        run["finished_at"] = int(time.time())


async def _verify_session_or_none(request, response, background_tasks, auth_token):
    """Full check incl. token revocation. Returns UserModel or None."""
    from open_webui.utils.auth import get_current_user

    try:
        return await get_current_user(request, response, background_tasks, auth_token)
    except Exception as e:
        log.debug(f"prune page auth failed (redirecting): {e}")
        return None


def _sanitize_manual_form(body: dict) -> dict:
    """Age fields: anything not a positive int means disabled. Prevents a typed
    0 or negative from arming a rule with cutoff=now (which deletes everything)."""
    out = dict(body or {})
    for key in (
        "days",
        "delete_knowledge_bases_older_than_days",
        "channel_message_max_age_days",
        "audio_cache_max_age_days",
        "delete_inactive_users_days",
    ):
        if key in out:
            try:
                value = int(out[key]) if out[key] is not None else None
            except (TypeError, ValueError):
                value = None
            out[key] = value if value is not None and value > 0 else None
    # Grace hours is a PROTECTION, so it fails CLOSED: garbage or negative
    # values fall back to the default instead of silently disabling the window
    # (explicit 0 remains a deliberate opt-out).
    if "orphan_file_grace_hours" in out:
        try:
            grace = int(out["orphan_file_grace_hours"])
        except (TypeError, ValueError):
            grace = -1
        out["orphan_file_grace_hours"] = grace if grace >= 0 else 24
    return out


def mount_routes(app, settings: dict):
    from open_webui.utils.auth import get_admin_user, bearer_security

    prefix = "/" + settings["route_prefix"].strip("/ ")
    if prefix == "/":
        prefix = "/prune"  # an empty valve would shadow the SPA at '/'
    stale = [
        r
        for r in app.router.routes
        if getattr(r, "path", None) == prefix
        or str(getattr(r, "path", "")).startswith(prefix + "/")
    ]
    if stale:
        # Module was re-executed (in-place code update). Starlette can't swap a
        # route's handler in place, so the previous version's page and API keep
        # serving until a full server restart -- which is why a freshly updated
        # plugin still shows the old UI (e.g. a preview with no progress bar).
        # Drop our stale routes here so the fresh handlers mounted below take
        # effect on update, no restart required.
        stale_ids = {id(r) for r in stale}
        app.router.routes[:] = [
            r for r in app.router.routes if id(r) not in stale_ids
        ]
        log.info("prune: refreshed %d route(s) after code update", len(stale))
    router = APIRouter()

    # ---- page: session-gated BEFORE any HTML is served; admins only ----
    @router.get(prefix, include_in_schema=False)
    async def page(
        request: Request,
        response: Response,
        background_tasks: BackgroundTasks,
        auth_token=Depends(bearer_security),
    ):
        user = await _verify_session_or_none(
            request, response, background_tasks, auth_token
        )
        if user is None or getattr(user, "role", None) != "admin":
            redirect = RedirectResponse(url="/", status_code=302)
            # get_current_user cleared invalid token cookies on the injected
            # response; carry those Set-Cookie headers onto the redirect so a
            # dead cookie is dropped like on core routes.
            for header_key, header_value in response.headers.raw:
                if header_key == b"set-cookie":
                    redirect.raw_headers.append((header_key, header_value))
            return redirect
        return HTMLResponse(
            _PAGE_HTML.replace("__PREFIX__", prefix),
            headers={"Cache-Control": "no-store"},
        )

    @router.get(f"{prefix}/api/status", include_in_schema=False)
    async def status(user=Depends(get_admin_user)):
        running = _STATE["lock"] is not None and _STATE["lock"].locked()
        current = next((r for r in _STATE["runs"] if r["status"] == "running"), None)
        return {
            "version": PLUGIN_VERSION,
            "vector_db": str(VECTOR_DB) if VECTOR_DB else None,
            "storage_provider": str(STORAGE_PROVIDER or "local"),
            "running": running,
            "current": _run_summary(current, log_tail=20) if current else None,
            # Automatic passes have no run record but still report progress
            "progress": dict(_PROGRESS) if _PROGRESS.get("active") else None,
        }

    def _start_manual_run(body: dict, user, dry_run: bool):
        """Create a run record and launch preview/execute in the background."""
        if _STATE["lock"] is not None and _STATE["lock"].locked():
            return JSONResponse(
                status_code=409,
                content={"ok": False, "error": "A prune pass is already in progress"},
            )
        sanitized = _sanitize_manual_form(body)
        rates = {
            k: _rate_override(sanitized, k)
            for k in ("deletion_rows_per_second", "scan_rows_per_second")
        }
        sanitized.pop("deletion_rows_per_second", None)
        sanitized.pop("scan_rows_per_second", None)
        form_data = PruneDataForm(**{**sanitized, "dry_run": dry_run})
        run = {
            "id": str(uuid.uuid4())[:8],
            "mode": "preview" if dry_run else "manual",
            "started_at": int(time.time()),
            "finished_at": None,
            "status": "running",
            "by": user.email,
            "form": form_data.model_dump(),
            "log": [],
            "result": None,
        }
        _STATE["runs"].insert(0, run)
        del _STATE["runs"][MAX_RUNS_KEPT:]

        def on_skip():
            run["status"] = "failed"
            run["finished_at"] = int(time.time())
            run["result"] = {"ok": False, "error": "another pass won the start race"}

        _spawn(
            f"{run['mode']}-{run['id']}",
            lambda: _manual_execute(form_data, run, rates),
            on_skip,
        )
        return {"ok": True, "run_id": run["id"]}

    @router.post(f"{prefix}/api/preview", include_in_schema=False)
    async def preview(request: Request, body: dict, user=Depends(get_admin_user)):
        # Same bearer requirement as execute: preview is not destructive but
        # it takes the global run lock and scans the whole database. Runs in
        # the background like execute; poll the run for progress and result.
        if not request.headers.get("authorization", "").lower().startswith("bearer "):
            return JSONResponse(
                status_code=403,
                content={"ok": False, "error": "Bearer token required"},
            )
        return _start_manual_run(body, user, dry_run=True)

    @router.post(f"{prefix}/api/execute", include_in_schema=False)
    async def execute(request: Request, body: dict, user=Depends(get_admin_user)):
        # CSRF hardening: the UI always sends a Bearer header; never accept
        # cookie-only auth for the destructive endpoint.
        if not request.headers.get("authorization", "").lower().startswith("bearer "):
            return JSONResponse(
                status_code=403,
                content={"ok": False, "error": "Bearer token required"},
            )
        return _start_manual_run(body, user, dry_run=False)

    @router.get(f"{prefix}/api/runs", include_in_schema=False)
    async def runs(user=Depends(get_admin_user)):
        return {"runs": [_run_summary(r, log_tail=5) for r in _STATE["runs"]]}

    @router.get(f"{prefix}/api/runs/{{run_id}}", include_in_schema=False)
    async def run_detail(run_id: str, user=Depends(get_admin_user)):
        for r in _STATE["runs"]:
            if r["id"] == run_id:
                return _run_summary(r, log_tail=1000)
        return JSONResponse(status_code=404, content={"ok": False, "error": "not found"})

    before = len(app.router.routes)
    app.include_router(router)
    # OWUI mounts its SPA catch-all at '/' at import time; routes appended during
    # the startup event land after it and get shadowed. Move ours ahead of it.
    routes = app.router.routes
    added = routes[before:]
    spa_i = next(
        (i for i, r in enumerate(routes) if getattr(r, "name", None) == "spa-static-files"),
        None,
    )
    if spa_i is not None and added:
        del routes[before:]
        routes[spa_i:spa_i] = added


class Event:
    class Valves(BaseModel):
        enable_automatic_deletion: bool = Field(
            default=False,
            description="\U0001f9f9 \u27a1\ufe0f **[Open the Prune UI](/prune)** to preview and run cleanups by hand (link follows the route_prefix valve). This toggle is the **MASTER SWITCH for automatic pruning**: when on, the rules below run on their own in reaction to server events and **DELETE FOR REAL**. Rehearse with the Preview button in the Prune UI first.",
        )
        route_prefix: str = Field(
            default="/prune",
            description="URL path of the manual Prune page. Changing it requires a server restart.",
        )
        deletion_rows_per_second: int = Field(
            default=50,
            description="Speed limit for all pruning, in database rows per second, so large cleanups never slow down a live instance. Applies immediately, even to a pass that is already running. 0 = no limit.",
        )
        scan_rows_per_second: int = Field(
            default=10000,
            description="Speed limit for the read-side scans (preview counts and orphan detection), in rows per second, so a preview or run never saturates a live database. Defaults to a bounded 10000/s; raise it for faster previews on a quiet instance, or set 0 for no limit.",
        )
        event_recheck_minutes: int = Field(
            default=60,
            description="At most one automatic recheck of old chats and inactive users per this many minutes, triggered by normal activity such as logins and chat updates. 0 = never recheck on events. Full sweeps are controlled by Full Sweep Interval Hours instead.",
        )
        full_sweep_interval_hours: int = Field(
            default=24,
            description="At most one full cleanup sweep (orphaned records, storage, vector collections) per this many hours, triggered at startup or by user and knowledge base deletions. 0 = sweep only at server startup, on every startup.",
        )
        orphan_file_grace_hours: int = Field(
            default=24,
            description="Never treat files younger than this many hours as orphaned. Protects uploads the user has not yet attached to a chat or knowledge base (0 = no protection).\n\n---\n\n#### 🕒 Age Rules",
        )
        chat_max_age_days: int = Field(
            default=0,
            description="Delete chats older than this many days (0 = keep forever).",
        )
        exempt_archived_chats: bool = Field(
            default=True,
            description="\u21b3 Never auto-delete archived chats, even past the age limit.",
        )
        exempt_pinned_chats: bool = Field(
            default=True,
            description="\u21b3 Never auto-delete pinned chats, even past the age limit.",
        )
        exempt_chats_in_folders: bool = Field(
            default=False,
            description="\u21b3 Never auto-delete chats that are organized into folders.",
        )
        audio_cache_max_age_days: int = Field(
            default=0,
            description="Delete cached text-to-speech and transcription audio older than this many days (0 = keep forever).\n\n---\n\n#### 👤 Inactive Users",
        )
        inactive_user_days: int = Field(
            default=0,
            description="\u26a0\ufe0f Delete user accounts inactive for this many days, INCLUDING all their private data (0 = never). Files they uploaded that other users still rely on are kept.",
        )
        exempt_admin_users: bool = Field(
            default=True,
            description="\u21b3 Never delete admin accounts (strongly recommended).",
        )
        exempt_pending_users: bool = Field(
            default=True,
            description="\u21b3 Never delete accounts still pending approval.\n\n---\n\n#### 🧹 Orphaned: Chats & Messages",
        )
        delete_orphaned_chats: bool = Field(
            default=True, description="Delete chats that belonged to deleted users."
        )
        delete_orphaned_chat_messages: bool = Field(
            default=True,
            description="Delete leftover message rows whose chat no longer exists.\n\n---\n\n#### 📚 Orphaned: Knowledge Bases & Memories",
        )
        delete_orphaned_knowledge_bases: bool = Field(
            default=True,
            description="Delete knowledge bases that belonged to deleted users.",
        )
        exempt_shared_orphaned_knowledge_bases: bool = Field(
            default=True,
            description="\u21b3 Keep them, files included, when a living user, an existing group or a public grant can still access them.",
        )
        delete_orphaned_knowledge_base_metadata: bool = Field(
            default=True,
            description="Delete leftover search-index entries of knowledge bases that no longer exist (every knowledge base has one hidden embedding used for searching across knowledge bases).",
        )
        delete_orphaned_memories: bool = Field(
            default=True,
            description="Delete orphaned memories: leftover embeddings whose memory entry no longer exists, and the stored memories of deleted users.\n\n---\n\n#### 🧰 Orphaned: Workspace",
        )
        delete_orphaned_prompts: bool = Field(
            default=True, description="Delete prompts that belonged to deleted users."
        )
        exempt_shared_orphaned_prompts: bool = Field(
            default=True,
            description="\u21b3 Keep them when a living user, an existing group or a public grant can still access them.",
        )
        delete_orphaned_models: bool = Field(
            default=True,
            description="Delete workspace models that belonged to deleted users.",
        )
        exempt_shared_orphaned_models: bool = Field(
            default=True,
            description="\u21b3 Keep them when a living user, an existing group or a public grant can still access them.",
        )
        delete_orphaned_tools: bool = Field(
            default=False, description="Delete tools that belonged to deleted users."
        )
        exempt_shared_orphaned_tools: bool = Field(
            default=True,
            description="\u21b3 Keep them when a living user, an existing group or a public grant can still access them.",
        )
        delete_orphaned_functions: bool = Field(
            default=False,
            description="Delete functions that belonged to deleted users. Functions are server-side code, so this is off by default; review before enabling.",
        )
        delete_orphaned_skills: bool = Field(
            default=False, description="Delete skills that belonged to deleted users."
        )
        exempt_shared_orphaned_skills: bool = Field(
            default=True,
            description="\u21b3 Keep them when a living user, an existing group or a public grant can still access them.\n\n---\n\n#### 🗂 Orphaned: Notes, Folders & Automations",
        )
        delete_orphaned_notes: bool = Field(
            default=True, description="Delete notes that belonged to deleted users."
        )
        exempt_shared_orphaned_notes: bool = Field(
            default=True,
            description="\u21b3 Keep them when a living user, an existing group or a public grant can still access them.",
        )
        delete_orphaned_folders: bool = Field(
            default=True, description="Delete folders that belonged to deleted users."
        )
        delete_orphaned_automations: bool = Field(
            default=True,
            description="Delete automations, including their run history, that belonged to deleted users.\n\n---\n\n#### 💬 Channels",
        )
        channel_message_max_age_days: int = Field(
            default=0,
            description="Delete channel messages older than this many days (0 = keep forever).",
        )
        exempt_pinned_channel_messages: bool = Field(
            default=True,
            description="\u21b3 Never auto-delete pinned channel messages.",
        )
        delete_orphaned_channel_messages: bool = Field(
            default=True,
            description="Delete channel messages whose channel no longer exists.",
        )
        delete_orphaned_channels: bool = Field(
            default=False,
            description="Delete channels that belonged to deleted users. Channels are shared infrastructure, so this is off by default.\n\n---\n\n#### 📚 Knowledge Base Retention",
        )
        knowledge_base_max_age_days: int = Field(
            default=0,
            description="\u26a0\ufe0f **Retention policy, not orphan cleanup:** permanently delete knowledge bases older than this many days, **even when they are shared and actively in use** (0 = never).",
        )
        knowledge_base_age_basis: str = Field(
            default="created_at",
            description="\u21b3 How a knowledge base's age is measured: `created_at` (time since it was created) or `updated_at` (time since it was last changed).",
        )
    def __init__(self):
        self.valves = self.Valves()

    def _init(self, app, v: dict):
        """Idempotent per-worker init; also runs lazily after an in-place code
        update, when the fresh module never sees system.startup.completed."""
        if _STATE["started"]:
            return
        if _STATE["lock"] is None:
            _STATE["lock"] = asyncio.Lock()
        log.setLevel(logging.INFO)
        PruneLock.init(Path(CACHE_DIR))
        if app is not None:
            mount_routes(app, v)
        _STATE["started"] = True
        log.info(
            f"prune plugin v{PLUGIN_VERSION} ready at {v['route_prefix']} "
            f"(automatic={v['enable_automatic_deletion']}, "
            f"rate={_PACE['rows_per_second']}/s)"
        )

    async def event(
        self,
        event: dict,
        __event_name__: str = None,
        __app__=None,
        __id__: str = None,
        **kwargs,
    ):
        # Snapshot valves; the module is a shared singleton reassigned per dispatch.
        v = self.valves.model_dump()
        _PACE["rows_per_second"] = max(0, int(v["deletion_rows_per_second"] or 0))
        _PACE["scan_rows_per_second"] = max(0, int(v.get("scan_rows_per_second") or 0))
        name = __event_name__ or ""

        if name == "system.startup.completed":
            self._init(__app__, v)
            # Boot-time full sweep. The boot claim dedupes simultaneous replica
            # boots; with an interval configured the sweep ALSO requires the
            # interval claim, so rolling deploys and crash-looping workers
            # cannot re-sweep the whole database every restart. Interval 0 =
            # startup-only mode: sweep on every boot.
            if v["enable_automatic_deletion"] and _claim("full-sweep-boot", 600):
                interval_hours = int(v["full_sweep_interval_hours"] or 0)
                if interval_hours == 0 or _claim("full-sweep", _full_sweep_ttl(v)):
                    _spawn(
                        "startup-full",
                        lambda: _pass_full(v),
                        on_skip=lambda: (
                            _unclaim("full-sweep-boot"),
                            _unclaim("full-sweep"),
                        ),
                    )
            return

        if not _STATE["started"]:
            if __app__ is None:
                return
            log.info("prune: late init after code update (no restart seen)")
            self._init(__app__, v)


        if not v["enable_automatic_deletion"]:
            return

        if _STATE["lock"] is not None and _STATE["lock"].locked():
            return  # a pass is running; don't burn cross-replica claims

        cooldown_minutes = int(v["event_recheck_minutes"] or 0)
        cooldown = max(60, cooldown_minutes * 60)

        if name in ("chat.created", "chat.deleted", "chat.deleted_all", "message.created"):
            if (
                cooldown_minutes > 0
                and (
                    _days(v["chat_max_age_days"]) is not None
                    or _days(v["channel_message_max_age_days"]) is not None
                )
                and _claim("chats", cooldown)
            ):
                _spawn("chats", lambda: _pass_chats(v), on_skip=lambda: _unclaim("chats"))

        elif name in ("auth.login", "user.created"):
            if (
                cooldown_minutes > 0
                and _days(v["inactive_user_days"]) is not None
                and _claim("users", cooldown)
            ):
                _spawn("users", lambda: _pass_users(v), on_skip=lambda: _unclaim("users"))

        elif name in ("user.deleted", "knowledge.deleted", "file.deleted_all"):
            if int(v["full_sweep_interval_hours"] or 0) > 0 and _claim(
                "full-sweep", _full_sweep_ttl(v)
            ):
                _spawn(
                    "full",
                    lambda: _pass_full(v),
                    on_skip=lambda: _unclaim("full-sweep"),
                )


_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Prune - Open WebUI</title>
<style>
:root{color-scheme:light dark;--bg:#f3f4f6;--surface:#fff;--text:#14171c;--muted:#666d78;
--border:rgba(18,22,28,.12);--accent:#1f242c;--fg-on-accent:#fff;
--danger:#c5413f;--danger-bg:rgba(197,65,63,.1);--ok:#15935f;--r:12px}
@media(prefers-color-scheme:dark){:root{--bg:#0c0e12;--surface:#15181e;--text:#e8eaef;
--muted:#a0a7b2;--border:rgba(255,255,255,.1);--accent:#e8eaef;--fg-on-accent:#14171c;
--danger:#f0726f;--danger-bg:rgba(240,114,111,.12);--ok:#46cf94}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:880px;margin:0 auto;padding:24px 16px 80px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:13px;text-transform:uppercase;
letter-spacing:.05em;color:var(--muted);margin:24px 0 8px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);
padding:14px 16px;margin-bottom:12px}
.sub{color:var(--muted);font-size:13px;margin:0 0 16px}
label.row{display:flex;align-items:center;gap:8px;padding:4px 0;cursor:pointer}
label.row.sub{margin-left:22px}
.numrow{display:flex;align-items:center;gap:8px;padding:4px 0;flex-wrap:wrap}
input[type=number]{width:90px;padding:4px 8px;border:1px solid var(--border);
border-radius:8px;background:var(--bg);color:var(--text)}
select{padding:4px 8px;border:1px solid var(--border);border-radius:8px;
background:var(--bg);color:var(--text)}
button{border:1px solid var(--border);border-radius:10px;padding:8px 16px;cursor:pointer;
font-weight:600;background:var(--surface);color:var(--text)}
button.primary{background:var(--accent);color:var(--fg-on-accent);border-color:transparent}
button.danger{background:var(--danger);color:#fff;border-color:transparent}
button:disabled{opacity:.5;cursor:default}
.actions{display:flex;gap:10px;margin-top:16px;align-items:center}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:5px 8px;border-bottom:1px solid var(--border);text-align:left}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.total{font-weight:700}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;
font-weight:600;background:var(--danger-bg);color:var(--danger)}
.badge.ok{background:rgba(21,147,95,.12);color:var(--ok)}
pre.log{background:var(--bg);border:1px solid var(--border);border-radius:8px;
padding:10px;max-height:320px;overflow:auto;font-size:12px;white-space:pre-wrap;margin:8px 0 0}
.prog{margin:14px 0 4px;display:none}
.prog .bar{height:8px;border-radius:999px;background:var(--border);overflow:hidden}
.prog .fill{height:100%;width:0%;background:var(--accent);border-radius:999px;
transition:width .4s ease}
.prog.indet .fill{width:30%;animation:pslide 1.2s linear infinite;transition:none}
@keyframes pslide{from{margin-left:-30%}to{margin-left:100%}}
.prog .lbl{font-size:12px;color:var(--muted);margin-top:5px;display:flex;
justify-content:space-between;gap:12px;flex-wrap:wrap}
.msg{margin:10px 0;font-size:13px}
.hint{color:var(--muted);font-size:12px}
.tipi{cursor:help;border:1px solid var(--border);border-radius:50%;width:15px;height:15px;
display:inline-flex;align-items:center;justify-content:center;font-size:10px;
color:var(--muted);flex:none;user-select:none}
.unit{color:var(--muted);font-size:12px}
</style>
</head>
<body data-prefix="__PREFIX__">
<div class="wrap">
<h1>Prune</h1>
<p class="sub">Manual cleanup of old and orphaned Open WebUI data. Preview is always safe; Execute permanently deletes. Automatic pruning is configured separately in this function's Valves.</p>

<div id="form"></div>

<div class="actions">
  <button class="primary" id="btnPreview">Preview</button>
  <button class="danger" id="btnExecute">Execute…</button>
  <span id="status"></span>
</div>
<div class="prog" id="prog">
  <div class="bar"><div class="fill" id="progFill"></div></div>
  <div class="lbl"><span id="progStage"></span><span id="progCount"></span></div>
</div>
<div class="msg" id="msg"></div>

<div class="card" id="previewCard" style="display:none">
  <h2 style="margin-top:0">Preview result</h2>
  <div id="previewBody"></div>
</div>

<div class="card" id="runCard" style="display:none">
  <h2 style="margin-top:0">Run <span id="runId"></span> <span class="badge" id="runStatus"></span></h2>
  <pre class="log" id="runLog"></pre>
</div>
</div>

<script>
const PREFIX = document.body.dataset.prefix;
const token = localStorage.getItem('token');

const SECTIONS = [
 {title:'🛡️ Safety', fields:[
  {k:'orphan_file_grace_hours',t:'num',label:'Protect uploads younger than',unit:'hours',val:24,
   tip:'Files younger than this are never treated as orphaned. Uploading and attaching are separate steps in Open WebUI, so this protects uploads not yet attached to a chat or knowledge base. 0 disables the protection.'},
 ]},
 {title:'🚦 Speed (this run only)', fields:[
  {k:'scan_rows_per_second',t:'num',label:'Scan speed',unit:'rows/s',val:50000,ph:'valve',
   tip:'Read speed for THIS run only, overriding the valve. Applies to preview counts and orphan detection. Higher = faster preview/scan; lower = gentler on a live database. Seeded here at 50000/s for snappy on-demand runs — clear the field to fall back to the valve default (10000/s); 0 = no limit.'},
  {k:'deletion_rows_per_second',t:'num',label:'Deletion speed',unit:'rows/s',val:500,ph:'valve',
   tip:'Delete speed for THIS run only, overriding the valve (Execute only). Higher = faster cleanup; lower = gentler on a live instance. Seeded here at 500/s for hand-run cleanups — clear the field to fall back to the valve default (50/s); 0 = no limit.'},
 ]},
 {title:'🕒 Age Rules', fields:[
  {k:'days',t:'num',label:'Delete chats older than',unit:'days',
   tip:'Chats whose last update is older than this are deleted. Empty = off.'},
  {k:'exempt_archived_chats',t:'chk',def:true,label:'Keep archived chats',
   tip:'Archived chats survive the age rule above.'},
  {k:'exempt_pinned_chats',t:'chk',def:true,label:'Keep pinned chats',
   tip:'Pinned chats survive the age rule above.'},
  {k:'exempt_chats_in_folders',t:'chk',def:false,label:'Keep chats in folders',
   tip:'Chats organized into folders survive the age rule above.'},
  {k:'audio_cache_max_age_days',t:'num',label:'Delete audio cache older than',unit:'days',
   tip:'Cached text-to-speech and transcription audio files. Empty = keep forever.'},
 ]},
 {title:'👤 Inactive Users', fields:[
  {k:'delete_inactive_users_days',t:'num',label:'Delete users inactive for',unit:'days',
   tip:'DESTRUCTIVE: deletes the account, its login credentials and all its private data. Files they uploaded that other users still rely on are kept. Empty = off.'},
  {k:'exempt_admin_users',t:'chk',def:true,label:'Never delete admins',
   tip:'Strongly recommended. Admin accounts are never deleted by the rule above.'},
  {k:'exempt_pending_users',t:'chk',def:true,label:'Never delete pending users',
   tip:'Accounts still awaiting approval are never deleted by the rule above.'},
 ]},
 {title:'🧹 Orphaned: Chats & Messages', fields:[
  {k:'delete_orphaned_chats',t:'chk',def:true,label:'Chats of deleted users',
   tip:'Chats whose owner account no longer exists.'},
  {k:'delete_orphaned_chat_messages',t:'chk',def:true,label:'Leftover chat message rows',
   tip:'Message rows whose parent chat no longer exists (left behind because SQLite does not enforce cascades).'},
 ]},
 {title:'📚 Orphaned: Knowledge Bases & Memories', fields:[
  {k:'delete_orphaned_knowledge_bases',t:'chk',def:true,label:'Knowledge bases of deleted users',
   tip:'Knowledge bases whose owner account no longer exists. Unchecking preserves their files and vectors too.'},
  {k:'exempt_shared_orphaned_knowledge_bases',t:'chk',def:true,parent:'delete_orphaned_knowledge_bases',label:'↳ Keep shared ones, files included',
   tip:'A knowledge base still reachable by a living user, an existing group or a public grant is kept, with all its files and vectors.'},
  {k:'delete_orphaned_kb_metadata',t:'chk',def:true,label:'Leftover search-index entries',
   tip:'Every knowledge base has one hidden embedding used for searching across knowledge bases; this removes entries whose knowledge base is gone.'},
  {k:'delete_orphaned_memories',t:'chk',def:true,label:'Orphaned memories',
   tip:'Leftover memory embeddings whose entry was deleted, and the stored memories of deleted users.'},
 ]},
 {title:'🧰 Orphaned: Workspace', fields:[
  {k:'delete_orphaned_prompts',t:'chk',def:true,label:'Prompts of deleted users',tip:'Prompts whose owner account no longer exists.'},
  {k:'exempt_shared_orphaned_prompts',t:'chk',def:true,parent:'delete_orphaned_prompts',label:'↳ Keep shared ones',
   tip:'Kept when a living user, an existing group or a public grant can still access them.'},
  {k:'delete_orphaned_models',t:'chk',def:true,label:'Models of deleted users',tip:'Workspace model presets whose owner account no longer exists.'},
  {k:'exempt_shared_orphaned_models',t:'chk',def:true,parent:'delete_orphaned_models',label:'↳ Keep shared ones',
   tip:'Kept when a living user, an existing group or a public grant can still access them.'},
  {k:'delete_orphaned_tools',t:'chk',def:false,label:'Tools of deleted users',tip:'Off by default: tools are server-side code.'},
  {k:'exempt_shared_orphaned_tools',t:'chk',def:true,parent:'delete_orphaned_tools',label:'↳ Keep shared ones',
   tip:'Kept when a living user, an existing group or a public grant can still access them.'},
  {k:'delete_orphaned_functions',t:'chk',def:false,label:'Functions of deleted users',tip:'Off by default: functions are server-side code.'},
  {k:'delete_orphaned_skills',t:'chk',def:false,label:'Skills of deleted users',tip:'Off by default.'},
  {k:'exempt_shared_orphaned_skills',t:'chk',def:true,parent:'delete_orphaned_skills',label:'↳ Keep shared ones',
   tip:'Kept when a living user, an existing group or a public grant can still access them.'},
 ]},
 {title:'🗂️ Orphaned: Notes, Folders & Automations', fields:[
  {k:'delete_orphaned_notes',t:'chk',def:true,label:'Notes of deleted users',tip:'Notes whose owner account no longer exists.'},
  {k:'exempt_shared_orphaned_notes',t:'chk',def:true,parent:'delete_orphaned_notes',label:'↳ Keep shared ones',
   tip:'Kept when a living user, an existing group or a public grant can still access them.'},
  {k:'delete_orphaned_folders',t:'chk',def:true,label:'Folders of deleted users',tip:'Chat folders whose owner account no longer exists.'},
  {k:'delete_orphaned_automations',t:'chk',def:true,label:'Automations of deleted users',tip:'Automations and their run history.'},
 ]},
 {title:'💬 Channels', fields:[
  {k:'channel_message_max_age_days',t:'num',label:'Delete channel messages older than',unit:'days',
   tip:'Age-based cleanup of channel messages; the channels themselves are kept. Empty = off.'},
  {k:'exempt_pinned_channel_messages',t:'chk',def:true,label:'↳ Keep pinned channel messages',
   tip:'Pinned messages survive the age rule above.'},
  {k:'delete_orphaned_channel_messages',t:'chk',def:true,label:'Messages of deleted channels',
   tip:'Channel messages whose channel no longer exists.'},
  {k:'delete_orphaned_channels',t:'chk',def:false,label:'Channels of deleted users',
   tip:'Off by default: channels are shared infrastructure, other members may still use them.'},
 ]},
 {title:'⚠️ Knowledge Base Retention', fields:[
  {k:'delete_knowledge_bases_older_than_days',t:'num',label:'Delete knowledge bases older than',unit:'days',
   tip:'RETENTION POLICY, NOT CLEANUP: permanently deletes knowledge bases past this age even when they are shared and actively in use. Empty = off.'},
  {k:'knowledge_bases_age_field',t:'sel',label:'Age measured by',options:['created_at','updated_at'],
   tip:'created_at = time since the knowledge base was created; updated_at = time since it was last changed.'},
 ]},
 {title:'🛠️ Maintenance', fields:[
  {k:'run_vacuum',t:'chk',def:false,label:'Run VACUUM afterwards',
   tip:'Reclaims disk space from the main and vector databases after this run. LOCKS THE DATABASE while running; use during a maintenance window.'},
 ]},
];

function tipIcon(tip){return `<span class="tipi" title="${tip.replace(/"/g,'&quot;')}">i</span>`;}

function build(){
  const root=document.getElementById('form');
  for(const sec of SECTIONS){
    const h=document.createElement('h2');h.textContent=sec.title;root.appendChild(h);
    const card=document.createElement('div');card.className='card';root.appendChild(card);
    for(const f of sec.fields){
      if(f.t==='num'){
        const d=document.createElement('div');d.className='numrow';
        d.innerHTML=`<span>${f.label}</span><input type="number" min="0" id="f_${f.k}" `+
          `${f.val!==undefined?`value="${f.val}"`:''} placeholder="${f.ph||'off'}"><span class="unit">${f.unit}</span> ${tipIcon(f.tip)}`;
        card.appendChild(d);
      }else if(f.t==='sel'){
        const d=document.createElement('div');d.className='numrow';
        d.innerHTML=`<span>${f.label}</span><select id="f_${f.k}">`+
          f.options.map(o=>`<option value="${o}">${o}</option>`).join('')+`</select> ${tipIcon(f.tip)}`;
        card.appendChild(d);
      }else{
        const l=document.createElement('label');l.className='row'+(f.parent?' sub':'');
        l.innerHTML=`<input type="checkbox" id="f_${f.k}" ${f.def?'checked':''}><span>${f.label}</span> ${tipIcon(f.tip)}`;
        card.appendChild(l);
        if(f.parent){
          const pEl=document.getElementById('f_'+f.parent),c=l.querySelector('input');
          const sync=()=>{c.disabled=!pEl.checked;l.style.opacity=pEl.checked?'':'0.45';};
          pEl.addEventListener('change',sync);sync();
        }
      }
    }
  }
}

const ZERO_OK=new Set(['orphan_file_grace_hours','scan_rows_per_second','deletion_rows_per_second']);
function form(){
  const f={};
  for(const sec of SECTIONS)for(const fl of sec.fields){
    const el=document.getElementById('f_'+fl.k);
    if(fl.t==='num'){const n=parseInt(el.value,10);f[fl.k]=el.value&&Number.isFinite(n)&&n>0?n:(ZERO_OK.has(fl.k)&&el.value==='0'?0:null);}
    else if(fl.t==='sel'){f[fl.k]=el.value;}
    else{f[fl.k]=el.checked;}
  }
  if(f.orphan_file_grace_hours===null)f.orphan_file_grace_hours=0;
  return f;
}

async function api(path,opts={}){
  const r=await fetch(PREFIX+path,{...opts,headers:{
    'Content-Type':'application/json','Authorization':'Bearer '+token,...(opts.headers||{})}});
  if(r.status===401||r.status===403) throw new Error('Not authorized: admin session required.');
  const data=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(data.error||data.detail||('HTTP '+r.status));
  return data;
}

const msg=t=>{document.getElementById('msg').textContent=t||'';};
const fmt=n=>(n||0).toLocaleString();

function setBusy(b){
  document.getElementById('btnPreview').disabled=b;
  document.getElementById('btnExecute').disabled=b;
}

// A preview is an unthrottled scan that often finishes inside a single
// animation frame (small DB / localhost): the whole POST -> scan -> first
// poll round-trip completes before the browser paints, so it coalesces the
// show and the subsequent hide and the bar never actually appears. Hold the
// bar for a minimum visible duration so it is always perceptible.
const PROG_MIN_MS=650;
let progShownAt=0,progHideTimer=null;
function showProgress(p,mode){
  const box=document.getElementById('prog');
  if(!p){
    // Defer hiding until the bar has been on screen long enough to paint.
    if(box.style.display==='block'){
      const remaining=PROG_MIN_MS-(Date.now()-progShownAt);
      clearTimeout(progHideTimer);
      if(remaining>0){progHideTimer=setTimeout(()=>{box.style.display='none';},remaining);return;}
    }
    box.style.display='none';return;
  }
  clearTimeout(progHideTimer);
  if(box.style.display!=='block'){progShownAt=Date.now();}
  box.style.display='block';
  const kind=mode==='preview'?'Preview':'Run';
  document.getElementById('progStage').textContent=
    kind+' · step '+(p.stages_done||1)+' · '+(p.stage||'working');
  const fill=document.getElementById('progFill');
  const count=document.getElementById('progCount');
  if(p.total){
    box.classList.remove('indet');
    const pct=Math.min(100,Math.round(100*(p.done||0)/p.total));
    fill.style.width=pct+'%';
    count.textContent=fmt(p.done)+' / '+fmt(p.total)+' ('+pct+'%)';
  }else{
    box.classList.add('indet');
    count.textContent=p.done?fmt(p.done)+' processed':'';
  }
}

function renderPreview(result){
  document.getElementById('previewCard').style.display='';
  let html='';
  for(const [group,items] of Object.entries(result.summary||{})){
    const rows=Object.entries(items).filter(([,v])=>v>0);
    if(!rows.length)continue;
    html+=`<table><tr><th colspan="2">${group}</th></tr>`+
      rows.map(([k,v])=>`<tr><td>${k}</td><td class="n">${fmt(v)}</td></tr>`).join('')+'</table>';
  }
  html+=`<p class="total">Total items: ${fmt(result.total)}</p>`;
  if(!result.total)html='<p>Nothing to delete — database is clean for the selected options.</p>';
  document.getElementById('previewBody').innerHTML=html;
}

let pollTimer=null;
async function pollRun(id){
  try{
    const r=await api('/api/runs/'+id);
    const isPreview=r.mode==='preview';
    showProgress(r.status==='running'?(r.progress||{}):null,r.mode);
    if(!isPreview){
      document.getElementById('runCard').style.display='';
      document.getElementById('runId').textContent=id;
      const b=document.getElementById('runStatus');
      b.textContent=r.status;b.className='badge'+(r.status==='done'?' ok':'');
      const pre=document.getElementById('runLog');
      pre.textContent=r.log.join('\\n');pre.scrollTop=pre.scrollHeight;
    }
    if(r.status==='running'){pollTimer=setTimeout(()=>pollRun(id),1000);return;}
    setBusy(false);
    if(isPreview){
      if(r.status==='done'&&r.result){msg('');renderPreview(r.result);}
      else msg('Preview failed: '+((r.result&&r.result.error)||'see server log.'));
    }else{
      msg(r.status==='done'?'Run finished.':'Run failed — see log.');
    }
  }catch(e){msg('Poll failed: '+e.message);showProgress(null);setBusy(false);}
}

async function startRun(path,startMsg){
  setBusy(true);msg(startMsg);
  // Show an indeterminate bar immediately. A preview is an unthrottled scan and
  // often finishes within the round-trip before the first poll can observe the
  // 'running' state, so relying on pollRun to reveal the bar means it never
  // appears at all. pollRun still takes over once the first poll returns.
  showProgress({},path.indexOf('preview')>=0?'preview':'manual');
  try{
    const data=await api(path,{method:'POST',body:JSON.stringify(form())});
    msg('');pollRun(data.run_id);
  }catch(e){msg(e.message);showProgress(null);setBusy(false);}
}

function doPreview(){
  document.getElementById('previewCard').style.display='none';
  startRun('/api/preview','Starting preview…');
}

function doExecute(){
  const answer=prompt('This will PERMANENTLY DELETE the selected data.\\nType DELETE to confirm.');
  if(answer!=='DELETE')return;
  startRun('/api/execute','Starting run…');
}

async function initStatus(){
  try{
    const s=await api('/api/status');
    if(s.running&&s.current){msg('A prune run is already in progress.');setBusy(true);pollRun(s.current.id);}
    else if(s.running){
      document.getElementById('status').textContent='An automatic prune pass is currently running.';
      showProgress(s.progress||{},s.progress&&s.progress.mode);
      setTimeout(initStatus,2000);
    }else{
      document.getElementById('status').textContent='';
      showProgress(null);
    }
  }catch(e){}
}

build();
document.getElementById('btnPreview').onclick=doPreview;
document.getElementById('btnExecute').onclick=doExecute;
if(!token)msg('No session token found — log in to Open WebUI in this browser first.');
else initStatus();
</script>
</body>
</html>"""
