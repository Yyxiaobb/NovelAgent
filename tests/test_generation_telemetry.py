import io
import json
import logging
import os
import tempfile
import unittest
from unittest.mock import AsyncMock
from unittest.mock import patch

from utils.generation_telemetry import _logger, log_generation_metric


class GenerationTelemetryTests(unittest.TestCase):
    def test_metric_logs_safe_scalars_and_replaces_unknown_objects(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        previous_handlers = _logger.handlers[:]
        previous_propagate = _logger.propagate
        _logger.handlers[:] = [handler]
        _logger.propagate = False
        try:
            log_generation_metric(
                "model_complete",
                "project_field:project_type",
                12.345,
                output_chars=2,
                model=AsyncMock(),
                private_object=type("PrivateValue", (), {"__str__": lambda self: "must not leak"})(),
            )
        finally:
            _logger.handlers[:] = previous_handlers
            _logger.propagate = previous_propagate

        line = stream.getvalue()
        self.assertIn("generation_telemetry", line)
        payload = json.loads(line.split("generation_telemetry ", 1)[1])
        self.assertEqual(payload["duration_ms"], 12.35)
        self.assertEqual(payload["output_chars"], 2)
        self.assertEqual(payload["model"], "AsyncMock")
        self.assertEqual(payload["private_object"], "PrivateValue")
        self.assertNotIn("must not leak", line)

    def test_metric_writes_structured_jsonl_to_configured_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "generation.jsonl")
            with patch.dict(os.environ, {"GENERATION_TELEMETRY_FILE": target}):
                log_generation_metric("context_built", "chapter_content", 42.5, prompt_chars=120)

            with open(target, encoding="utf-8") as stream:
                payload = json.loads(stream.readline())
            self.assertEqual(payload["event"], "context_built")
            self.assertEqual(payload["task"], "chapter_content")
            self.assertEqual(payload["duration_ms"], 42.5)
            self.assertEqual(payload["prompt_chars"], 120)
            self.assertTrue(payload["recorded_at"].endswith("+00:00"))


if __name__ == "__main__":
    unittest.main()
