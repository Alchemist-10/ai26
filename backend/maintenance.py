"""Retention runs even when inference is disabled or a source/model fails."""
import logging
import threading
import time
from artifacts import cleanup_artifacts
from retention_policy import settings as retention_settings

log = logging.getLogger(__name__)


class Maintenance:
    def __init__(self, repository, retention_days=None):
        self.repository = repository
        configured = retention_settings()
        if retention_days is not None:
            if type(retention_days) is not int or not 7 <= retention_days <= 365:
                raise ValueError('AI26_OBSERVATION_RETENTION_DAYS must be an integer from 7 to 365')
            configured['observation_days'] = retention_days
        self.retention_days = configured['observation_days']
        self.traffic_retention_days = configured['traffic_days']
        self.stop_event = threading.Event()
        self.thread = None

    def run_once(self, now=None):
        now = time.time() if now is None else now
        cutoff = now - self.retention_days*86400
        # Report insertion and lease checks share this lock with cleanup.
        with self.repository.lock:
            self.repository.cleanup(cutoff, now, self.traffic_retention_days)
            cleanup_artifacts(cutoff, self.repository.protected_artifacts(now))

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, name='ai26-retention', daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop_event.is_set():
            try: self.run_once()
            except Exception: log.exception('Retention cleanup failed; retrying next minute')
            self.stop_event.wait(60)

    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join(timeout=30)
