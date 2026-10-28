"""
Annotation Storage Subsystem for GeoVerse Model 1.

Supports dual-backend architecture:
1. JsonAnnotationStore: Local-first atomic JSON persistence with timestamped backups.
2. SupabaseAnnotationStore: PostgreSQL/Supabase database storage with transactions,
   relational integrity, audit history logging, and role-based access.

Strict Safety Rules:
- Never silently fall back to JSON on database write failures (prevents divergent split-brain state).
- Keep JSON storage as an independent, recoverable source of truth.
- Prevent browser exposure of database service keys.
"""

import os
import json
import shutil
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List


# -----------------------------------------------------------------------------
# Storage Exceptions
# -----------------------------------------------------------------------------

class StorageError(Exception):
    """Base exception for all annotation storage errors."""
    pass


class StorageConnectionError(StorageError):
    """Raised when connection to the storage backend fails."""
    pass


class StorageWriteError(StorageError):
    """Raised when an annotation write or update transaction fails."""
    pass


class StorageValidationError(StorageError):
    """Raised when data fails schema or relational constraints before persistence."""
    pass


class StorageConfigurationError(StorageError):
    """Raised when required backend configuration/credentials are missing."""
    pass


# -----------------------------------------------------------------------------
# Abstract Base Annotation Store
# -----------------------------------------------------------------------------

class BaseAnnotationStore(ABC):
    """
    Abstract interface for annotation storage backends.
    """

    @abstractmethod
    def load_annotations(self, dataset: str) -> Dict[str, Any]:
        """
        Loads all saved annotations for a dataset.
        Returns a dictionary mapping:
            anon_id -> {
                "updated_at": <iso_str>,
                "epochs": {
                    <epoch_str>: {
                        "status": <str>,
                        "dominant_class": <str>,
                        ...
                    }
                }
            }
        """
        pass

    @abstractmethod
    def save_sample_annotation(
        self,
        dataset: str,
        anon_id: str,
        data: Dict[str, Any],
        annotator_id: Optional[str] = None
    ) -> bool:
        """
        Saves or updates multi-epoch annotations for a single sample.
        Merges submitted epochs with existing epochs.
        """
        pass

    @abstractmethod
    def get_sample_annotation(self, dataset: str, anon_id: str) -> Dict[str, Any]:
        """
        Retrieves annotations for a single sample.
        Returns {"updated_at": ..., "epochs": {...}} or {"epochs": {}}.
        """
        pass

    @abstractmethod
    def ping(self) -> bool:
        """
        Checks health and connectivity to the storage backend.
        """
        pass

    @abstractmethod
    def get_backend_name(self) -> str:
        """
        Returns backend identifier ('json' or 'supabase').
        """
        pass


# -----------------------------------------------------------------------------
# Master AnnotationStore Factory / Base Class
# -----------------------------------------------------------------------------

class AnnotationStore(BaseAnnotationStore):
    """
    Annotation storage entry point and polymorphic factory.
    Instantiating AnnotationStore(storage_dir) maintains 100% backward compatibility
    with existing JSON callers while enabling dynamic backend switching via
    environment variables or explicit arguments.
    """

    def __new__(cls, storage_dir: Optional[str] = None, backend: Optional[str] = None, **kwargs):
        if cls is not AnnotationStore:
            return super().__new__(cls)

        if backend is None:
            backend = os.getenv("GEOVERSE_STORAGE_BACKEND", "json").strip().lower()

        if backend == "supabase":
            return object.__new__(SupabaseAnnotationStore)
        return object.__new__(JsonAnnotationStore)

    def load_annotations(self, dataset: str) -> Dict[str, Any]:
        raise NotImplementedError

    def save_sample_annotation(
        self,
        dataset: str,
        anon_id: str,
        data: Dict[str, Any],
        annotator_id: Optional[str] = None
    ) -> bool:
        raise NotImplementedError

    def get_sample_annotation(self, dataset: str, anon_id: str) -> Dict[str, Any]:
        raise NotImplementedError

    def ping(self) -> bool:
        raise NotImplementedError

    def get_backend_name(self) -> str:
        raise NotImplementedError


# -----------------------------------------------------------------------------
# JSON File-Backed Annotation Store
# -----------------------------------------------------------------------------

class JsonAnnotationStore(AnnotationStore):
    """
    Local file-backed annotation storage with atomic file writes and timestamped backups.
    """

    def __init__(self, storage_dir: Optional[str] = None, **kwargs):
        if storage_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            storage_dir = os.path.join(base_dir, "storage")
        self.storage_dir = str(storage_dir)
        self.backup_dir = os.path.join(self.storage_dir, "backups")
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

    def _get_filepath(self, dataset: str) -> str:
        safe_name = "gold" if dataset == "gold" else "t1"
        return os.path.join(self.storage_dir, f"{safe_name}_annotations.json")

    def load_annotations(self, dataset: str) -> Dict[str, Any]:
        filepath = self._get_filepath(dataset)
        if not os.path.exists(filepath):
            return {}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return {}

    def get_sample_annotation(self, dataset: str, anon_id: str) -> Dict[str, Any]:
        annotations = self.load_annotations(dataset)
        return annotations.get(anon_id, {"epochs": {}})

    def save_sample_annotation(
        self,
        dataset: str,
        anon_id: str,
        data: Dict[str, Any],
        annotator_id: Optional[str] = None
    ) -> bool:
        """
        Saves annotations for a single sample atomically and maintains timestamped backups.
        """
        filepath = self._get_filepath(dataset)
        current = self.load_annotations(dataset)

        # Merge or update epochs
        existing_sample = current.get(anon_id, {})
        existing_epochs = existing_sample.get("epochs", {})
        merged_epochs = dict(existing_epochs)
        submitted_epochs = data.get("epochs", {})
        merged_epochs.update(submitted_epochs)

        current[anon_id] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "epochs": merged_epochs
        }

        # Backup existing file before write
        if os.path.exists(filepath):
            ts = time.time_ns()
            backup_file = os.path.join(self.backup_dir, f"{dataset}_annotations_{ts}.json")
            try:
                shutil.copy2(filepath, backup_file)
            except Exception as e:
                print(f"Backup warning: {e}")

        # Atomic write via temp file
        temp_file = filepath + ".tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(current, f, indent=2)
            os.replace(temp_file, filepath)
        except Exception as e:
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass
            raise StorageWriteError(f"Atomic JSON write failed for {filepath}: {e}") from e
        return True

    def ping(self) -> bool:
        """Verifies storage directory is accessible and writable."""
        try:
            test_file = os.path.join(self.storage_dir, f".write_test_{time.time_ns()}")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            return True
        except Exception:
            return False

    def get_backend_name(self) -> str:
        return "json"


# -----------------------------------------------------------------------------
# Supabase / PostgreSQL Database Annotation Store
# -----------------------------------------------------------------------------

class SupabaseAnnotationStore(AnnotationStore):
    """
    PostgreSQL-backed annotation store using official Supabase client.
    Guarantees:
    - Atomicity and referential integrity via PostgreSQL constraints.
    - Preserves exact nested JSON data structure for application compatibility.
    - Server-side validation matching scientific protocol rules.
    - Strict fail-closed error handling (NO silent fallback to JSON).
    """

    def __init__(
        self,
        storage_dir: Optional[str] = None,
        url: Optional[str] = None,
        key: Optional[str] = None,
        client: Optional[Any] = None,
        manifest_dir: Optional[str] = None,
        **kwargs
    ):
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = (
            key
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            or os.getenv("SUPABASE_KEY")
            or os.getenv("SUPABASE_ANON_KEY")
        )

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.manifest_dir = manifest_dir or os.path.join(base_dir, "data")
        self.storage_dir = str(storage_dir or os.path.join(base_dir, "storage"))

        if client is not None:
            self.client = client
        else:
            if not self.url or not self.key:
                raise StorageConfigurationError(
                    "Supabase backend requires SUPABASE_URL and SUPABASE_KEY "
                    "(or SUPABASE_SERVICE_ROLE_KEY) environment variables."
                )
            try:
                from supabase import create_client
                self.client = create_client(self.url, self.key)
            except Exception as e:
                raise StorageConnectionError(f"Failed to initialize Supabase client: {e}") from e

    def ping(self) -> bool:
        """Checks database connectivity by reading datasets table."""
        try:
            resp = self.client.table("datasets").select("dataset_id").limit(1).execute()
            return hasattr(resp, "data") and resp.data is not None
        except Exception as e:
            return False

    def load_annotations(self, dataset: str) -> Dict[str, Any]:
        """
        Loads all annotations for dataset from Supabase annotations table.
        Reconstructs the hierarchical sample dictionary expected by app and tests.
        """
        safe_ds = "gold" if dataset == "gold" else "t1"
        try:
            resp = self.client.table("annotations").select("*").eq("dataset_id", safe_ds).execute()
        except Exception as e:
            raise StorageConnectionError(f"Failed to query Supabase annotations for {safe_ds}: {e}") from e

        rows = resp.data or []
        result: Dict[str, Any] = {}

        for row in rows:
            aid = row["anon_id"]
            epoch_str = str(row["epoch"])

            if aid not in result:
                result[aid] = {
                    "updated_at": row.get("updated_at") or row.get("created_at") or datetime.now(timezone.utc).isoformat(),
                    "epochs": {}
                }

            row_updated = row.get("updated_at") or row.get("created_at")
            if row_updated and row_updated > result[aid]["updated_at"]:
                result[aid]["updated_at"] = row_updated

            result[aid]["epochs"][epoch_str] = {
                "status": row.get("status") or "",
                "dominant_class": row.get("dominant_class") or "",
                "dominant_share_3bins": row.get("dominant_share_3bins") or "",
                "second_class": row.get("second_class") or "none",
                "confidence_1to3": row.get("confidence_1to3"),
                "imagery_source": row.get("imagery_source") or "",
                "imagery_date": row.get("imagery_date") or "",
                "notes": row.get("notes") or ""
            }

        return result

    def get_sample_annotation(self, dataset: str, anon_id: str) -> Dict[str, Any]:
        safe_ds = "gold" if dataset == "gold" else "t1"
        try:
            resp = (
                self.client.table("annotations")
                .select("*")
                .eq("dataset_id", safe_ds)
                .eq("anon_id", anon_id)
                .execute()
            )
        except Exception as e:
            raise StorageConnectionError(f"Failed to fetch sample {anon_id} from Supabase: {e}") from e

        rows = resp.data or []
        if not rows:
            return {"epochs": {}}

        latest_updated = rows[0].get("updated_at") or rows[0].get("created_at")
        epochs_data = {}
        for row in rows:
            row_updated = row.get("updated_at") or row.get("created_at")
            if row_updated and (latest_updated is None or row_updated > latest_updated):
                latest_updated = row_updated

            epochs_data[str(row["epoch"])] = {
                "status": row.get("status") or "",
                "dominant_class": row.get("dominant_class") or "",
                "dominant_share_3bins": row.get("dominant_share_3bins") or "",
                "second_class": row.get("second_class") or "none",
                "confidence_1to3": row.get("confidence_1to3"),
                "imagery_source": row.get("imagery_source") or "",
                "imagery_date": row.get("imagery_date") or "",
                "notes": row.get("notes") or ""
            }

        return {
            "updated_at": latest_updated or datetime.now(timezone.utc).isoformat(),
            "epochs": epochs_data
        }

    def _resolve_or_create_sample(self, dataset: str, anon_id: str) -> int:
        """
        Resolves the integer primary key of a sample in the database.
        If the sample row does not yet exist, attempts to resolve it from the local manifest.
        """
        resp = (
            self.client.table("samples")
            .select("id")
            .eq("dataset_id", dataset)
            .eq("anon_id", anon_id)
            .execute()
        )
        if resp.data and len(resp.data) > 0:
            return resp.data[0]["id"]

        # Sample not present in DB; attempt auto-registration from authoritative manifest
        manifest_file = os.path.join(self.manifest_dir, f"{dataset}_manifest.json")
        if os.path.exists(manifest_file):
            try:
                with open(manifest_file, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                matched = next((s for s in manifest if s["anon_id"] == anon_id), None)
                if matched:
                    ins_resp = self.client.table("samples").insert({
                        "dataset_id": dataset,
                        "anon_id": anon_id,
                        "lat": float(matched["lat"]),
                        "lon": float(matched["lon"]),
                        "polygon": matched.get("polygon", []),
                        "inside_primary_landsat": True,
                        "is_double_interpretation": False
                    }).execute()
                    if ins_resp.data and len(ins_resp.data) > 0:
                        return ins_resp.data[0]["id"]
            except Exception as e:
                raise StorageWriteError(f"Auto-registration for sample {anon_id} failed: {e}") from e

        raise StorageWriteError(f"Sample '{anon_id}' is not registered in dataset '{dataset}'.")

    def save_sample_annotation(
        self,
        dataset: str,
        anon_id: str,
        data: Dict[str, Any],
        annotator_id: Optional[str] = None
    ) -> bool:
        """
        Persists sample epoch annotations into Supabase.
        Uses idempotent UPSERT on (dataset_id, anon_id, epoch).
        Does NOT silently fall back to JSON on error.
        """
        safe_ds = "gold" if dataset == "gold" else "t1"
        sample_id = self._resolve_or_create_sample(safe_ds, anon_id)

        epochs_payload = data.get("epochs", {})
        if not epochs_payload:
            raise StorageValidationError("Cannot save annotation without epoch payload.")

        rows_to_upsert: List[Dict[str, Any]] = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for ep_str, ep_data in epochs_payload.items():
            try:
                ep_int = int(ep_str)
            except ValueError:
                raise StorageValidationError(f"Invalid epoch key '{ep_str}'. Must be integer.")

            conf_val = ep_data.get("confidence_1to3")
            conf_int = None
            if conf_val is not None and conf_val != "":
                try:
                    conf_int = int(conf_val)
                except (ValueError, TypeError):
                    raise StorageValidationError(f"Invalid confidence '{conf_val}' for epoch {ep_str}.")

            row = {
                "sample_id": sample_id,
                "dataset_id": safe_ds,
                "anon_id": anon_id,
                "epoch": ep_int,
                "status": ep_data.get("status", ""),
                "dominant_class": ep_data.get("dominant_class") or None,
                "dominant_share_3bins": ep_data.get("dominant_share_3bins") or None,
                "second_class": ep_data.get("second_class") or "none",
                "confidence_1to3": conf_int,
                "imagery_source": ep_data.get("imagery_source") or None,
                "imagery_date": ep_data.get("imagery_date") or None,
                "notes": ep_data.get("notes") or "",
                "annotator_id": annotator_id or ep_data.get("annotator_id"),
                "schema_version": "1.0",
                "updated_at": now_iso
            }
            rows_to_upsert.append(row)

        try:
            # Atomic upsert on composite unique key (dataset_id, anon_id, epoch)
            res = (
                self.client.table("annotations")
                .upsert(rows_to_upsert, on_conflict="dataset_id,anon_id,epoch")
                .execute()
            )
            if not hasattr(res, "data"):
                raise StorageWriteError("Supabase upsert did not return a valid response.")
            return True
        except Exception as e:
            # Strictly do not fall back to JSON; re-raise as StorageWriteError
            raise StorageWriteError(
                f"Failed to write annotations to Supabase for sample {anon_id}: {e}"
            ) from e

    def get_backend_name(self) -> str:
        return "supabase"


# -----------------------------------------------------------------------------
# Convenience Accessor
# -----------------------------------------------------------------------------

def get_storage_backend(
    storage_dir: Optional[str] = None,
    backend: Optional[str] = None,
    **kwargs
) -> BaseAnnotationStore:
    """
    Factory helper that instantiates the active storage backend based on
    environment variables or explicit options.
    """
    return AnnotationStore(storage_dir=storage_dir, backend=backend, **kwargs)
