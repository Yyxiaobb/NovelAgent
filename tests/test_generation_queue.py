import unittest
from unittest.mock import AsyncMock, patch

from config import queue_conf


class GenerationQueueTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_enqueue_uses_database_job_id_for_deduplication(self):
        pool = AsyncMock()
        pool.enqueue_job.return_value = object()

        with patch.object(queue_conf, "create_pool", new=AsyncMock(return_value=pool)):
            queued = await queue_conf.enqueue_content_job("job-123")

        self.assertTrue(queued)
        pool.enqueue_job.assert_awaited_once_with(
            "generate_chapter_content", "job-123", _job_id="job-123",
        )
        pool.aclose.assert_awaited_once()

    async def test_abort_targets_the_durable_job_id(self):
        pool = AsyncMock()
        with (
            patch.object(queue_conf, "create_pool", new=AsyncMock(return_value=pool)),
            patch.object(queue_conf.Job, "abort", new=AsyncMock(return_value=True)) as abort,
        ):
            aborted = await queue_conf.abort_content_job("job-456")

        self.assertTrue(aborted)
        abort.assert_awaited_once()
        pool.aclose.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
