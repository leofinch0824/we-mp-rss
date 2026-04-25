import unittest


class DictCache:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ttl=None):
        self.data[key] = value
        return True

    def delete(self, key):
        self.data.pop(key, None)
        return True


class TestRefreshTaskStore(unittest.TestCase):
    def test_store_tracks_task_and_active_article_mapping(self):
        from core.refresh_task_store import RefreshTaskStore

        store = RefreshTaskStore(cache=DictCache(), ttl=60)
        task_id = "task-1"

        store.set_task(
            task_id,
            {
                "task_id": task_id,
                "article_id": "article-1",
                "status": "pending",
                "message": "created",
            },
        )

        task = store.get_task(task_id)
        active = store.get_active_task("article-1")

        self.assertIsNotNone(task)
        self.assertEqual(task["status"], "pending")
        self.assertIsNotNone(active)
        self.assertEqual(active["task_id"], task_id)

    def test_terminal_status_clears_active_mapping(self):
        from core.refresh_task_store import RefreshTaskStore

        store = RefreshTaskStore(cache=DictCache(), ttl=60)
        task_id = "task-2"

        store.set_task(
            task_id,
            {
                "task_id": task_id,
                "article_id": "article-2",
                "status": "running",
                "message": "running",
            },
        )
        store.set_task(
            task_id,
            {
                "task_id": task_id,
                "article_id": "article-2",
                "status": "failed",
                "message": "failed",
            },
        )

        active = store.get_active_task("article-2")
        task = store.get_task(task_id)

        self.assertIsNone(active)
        self.assertEqual(task["status"], "failed")


if __name__ == "__main__":
    unittest.main()
