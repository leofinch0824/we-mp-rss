import unittest
import importlib
import os
import sys
from unittest.mock import patch


class DummyArticle:
    def __init__(self, article_id: str):
        self.id = article_id
        self.title = "demo title"
        self.url = "https://example.com/article"


class DummyQuery:
    def __init__(self, article):
        self.article = article

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.article


class DummySession:
    def __init__(self, article):
        self.article = article
        self.closed = False
        self.rolled_back = False

    def query(self, *args, **kwargs):
        return DummyQuery(self.article)

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class DummyStore:
    def __init__(self):
        self.tasks = {}

    def set_task(self, task_id, data):
        self.tasks[task_id] = dict(data)

    def get_task(self, task_id):
        return self.tasks.get(task_id)


class TestArticleRefreshTasks(unittest.IsolatedAsyncioTestCase):
    def _load_article_api(self):
        os.environ["DB"] = "sqlite:///./test_refresh_tasks.db"
        sys.argv = ["test", "-config", "config.example.yaml"]
        for module_name in ["apis.article", "core.db", "core.auth", "core.config"]:
            sys.modules.pop(module_name, None)
        return importlib.import_module("apis.article")

    async def test_refresh_task_uses_sync_article_content_with_force(self):
        article_api = self._load_article_api()

        session = DummySession(DummyArticle("article-1"))
        store = DummyStore()

        def fake_sync_article_content(*, session, article, preferred_mode, force):
            self.assertEqual(article.id, "article-1")
            self.assertTrue(force)
            return True, "api"

        with patch.object(article_api.DB, "get_session", return_value=session), \
             patch.object(article_api, "refresh_task_store", store), \
             patch.object(article_api, "sync_article_content", side_effect=fake_sync_article_content), \
             patch.object(article_api, "clear_cache_pattern"):
            await article_api._run_refresh_article_task("task-1", "article-1")

        task = store.get_task("task-1")
        self.assertEqual(task["status"], "success")
        self.assertEqual(task["fetch_mode"], "api")
        self.assertTrue(session.closed)


if __name__ == "__main__":
    unittest.main()
