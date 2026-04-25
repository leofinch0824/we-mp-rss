import threading
import time
from typing import Any, Optional

from core.redis_client import RedisCache


ACTIVE_STATUSES = {"pending", "running"}
TERMINAL_STATUSES = {"success", "failed"}


class RefreshTaskStore:
    def __init__(self, cache: Optional[Any] = None, ttl: int = 24 * 60 * 60):
        self.cache = cache or RedisCache(key_prefix="werss:refresh_task")
        self.ttl = ttl
        self._lock = threading.RLock()
        self._local_tasks: dict[str, dict[str, Any]] = {}
        self._local_active_by_article: dict[str, str] = {}

    def _task_key(self, task_id: str) -> str:
        return f"task:{task_id}"

    def _active_key(self, article_id: str) -> str:
        return f"article:{article_id}:active"

    def _cache_set(self, key: str, value: Any) -> bool:
        if not self.cache:
            return False
        try:
            return bool(self.cache.set(key, value, ttl=self.ttl))
        except Exception:
            return False

    def _cache_get(self, key: str) -> Any:
        if not self.cache:
            return None
        try:
            return self.cache.get(key)
        except Exception:
            return None

    def _cache_delete(self, key: str) -> bool:
        if not self.cache:
            return False
        try:
            return bool(self.cache.delete(key))
        except Exception:
            return False

    def set_task(self, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            existing = self.get_task(task_id) or {}
            payload = dict(existing)
            payload.update(data)
            payload["task_id"] = task_id
            payload["updated_at_millis"] = int(time.time() * 1000)

            article_id = payload.get("article_id")
            self._local_tasks[task_id] = dict(payload)

            self._cache_set(self._task_key(task_id), payload)

            if article_id:
                if payload.get("status") in ACTIVE_STATUSES:
                    self._local_active_by_article[article_id] = task_id
                    self._cache_set(self._active_key(article_id), task_id)
                elif payload.get("status") in TERMINAL_STATUSES:
                    if self._local_active_by_article.get(article_id) == task_id:
                        self._local_active_by_article.pop(article_id, None)
                    active_task_id = self._cache_get(self._active_key(article_id))
                    if active_task_id == task_id:
                        self._cache_delete(self._active_key(article_id))

            return dict(payload)

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            task = self._cache_get(self._task_key(task_id))
            if isinstance(task, dict):
                self._local_tasks[task_id] = dict(task)
                return dict(task)

            task = self._local_tasks.get(task_id)
            return dict(task) if task else None

    def get_active_task(self, article_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            task_id = self._cache_get(self._active_key(article_id))
            if not task_id:
                task_id = self._local_active_by_article.get(article_id)

            if not task_id:
                return None

            task = self.get_task(task_id)
            if not task:
                self._local_active_by_article.pop(article_id, None)
                self._cache_delete(self._active_key(article_id))
                return None

            if task.get("status") not in ACTIVE_STATUSES:
                self._local_active_by_article.pop(article_id, None)
                self._cache_delete(self._active_key(article_id))
                return None

            return dict(task)


refresh_task_store = RefreshTaskStore()
