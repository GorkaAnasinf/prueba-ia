import threading
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .config import settings

logger = logging.getLogger(__name__)

DEBOUNCE_SECONDS = 10


class VaultHandler(FileSystemEventHandler):
    def __init__(self):
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    def _schedule_ingest(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._run_ingest)
            self._timer.daemon = True
            self._timer.start()

    def _run_ingest(self):
        from .routers.rag import do_ingest
        try:
            result = do_ingest()
            logger.info(f"Auto-ingest: {result.files_processed} files, {result.chunks_indexed} chunks")
        except Exception as e:
            logger.error(f"Auto-ingest failed: {e}")

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            logger.debug(f"Vault change detected: {event.src_path}")
            self._schedule_ingest()

    def on_modified(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            logger.debug(f"Vault change detected: {event.src_path}")
            self._schedule_ingest()

    def on_deleted(self, event):
        if not event.is_directory and event.src_path.endswith(".md"):
            logger.debug(f"Vault change detected: {event.src_path}")
            self._schedule_ingest()


def start_watcher() -> Observer | None:
    vault_path = settings.obsidian_vault_path
    if not Path(vault_path).exists():
        logger.warning(f"Vault path not found, watcher disabled: {vault_path}")
        return None

    observer = Observer()
    observer.schedule(VaultHandler(), vault_path, recursive=True)
    observer.start()
    logger.info(f"Vault watcher started: {vault_path}")
    return observer
