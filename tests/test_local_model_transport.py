"""Bounded local Ollama transport tests."""
from __future__ import annotations

import json
from unittest import TestCase
from unittest.mock import patch

from cognition_agent_os import local_model


class FakeResponse:
    status = 200

    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit: int) -> bytes:
        return self.payload[:limit]


class FakeOpener:
    def __init__(self, payload: bytes):
        self.response = FakeResponse(payload)

    def open(self, request, timeout: int):
        return self.response


class LocalModelTransportTests(TestCase):
    def test_bounded_context_array_response_fits_native_prompt_envelope(self):
        # Ollama includes token IDs in the /api/generate context array. A
        # realistic long context must not be rejected by a 16 KiB transport cap.
        payload = json.dumps({
            "done": True,
            "response": '{"ok":true}',
            "context": list(range(12000)),
        }).encode("utf-8")
        self.assertLessEqual(len(payload), local_model._MAX_RESPONSE)
        with patch.object(
            local_model, "build_opener", return_value=FakeOpener(payload)
        ):
            result = local_model._request("GET", "/api/tags", None, 5)
        self.assertTrue(result["done"])
        self.assertEqual(result["response"], '{"ok":true}')
        self.assertEqual(len(result["context"]), 12000)

    def test_response_above_hard_ceiling_still_fails_closed(self):
        payload = b"x" * (local_model._MAX_RESPONSE + 1)
        with patch.object(
            local_model, "build_opener", return_value=FakeOpener(payload)
        ):
            with self.assertRaisesRegex(
                    local_model.LocalModelUnavailable, "size limit"):
                local_model._request("GET", "/api/tags", None, 5)


if __name__ == "__main__":
    import unittest
    unittest.main()
