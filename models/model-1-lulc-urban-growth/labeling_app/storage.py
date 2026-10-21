import os
import json
import shutil
import time
from datetime import datetime, timezone

class AnnotationStore:
    def __init__(self, storage_dir):
        self.storage_dir = storage_dir
        self.backup_dir = os.path.join(storage_dir, "backups")
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

    def _get_filepath(self, dataset):
        safe_name = "gold" if dataset == "gold" else "t1"
        return os.path.join(self.storage_dir, f"{safe_name}_annotations.json")

    def load_annotations(self, dataset):
        filepath = self._get_filepath(dataset)
        if not os.path.exists(filepath):
            return {}
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
            return {}

    def save_sample_annotation(self, dataset, anon_id, data):
        """
        Saves annotations for a single sample atomically and maintains timestamped backups.
        """
        filepath = self._get_filepath(dataset)
        current = self.load_annotations(dataset)
        
        # Merge or update
        current[anon_id] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "epochs": data.get("epochs", {})
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
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        os.replace(temp_file, filepath)
        return True
