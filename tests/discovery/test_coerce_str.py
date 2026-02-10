"""Unit tests for coerce_str() utility (Issue #255).

Validates that LLM response values are correctly coerced to strings
for Pydantic str fields.
"""

import json

import pytest

from src.discovery.agents.base import coerce_str


@pytest.mark.fast
class TestCoerceStr:
    """Tests for the shared coerce_str() utility."""

    def test_string_passthrough(self):
        assert coerce_str("hello") == "hello"

    def test_dict_input(self):
        val = {"key": "val"}
        assert coerce_str(val) == json.dumps(val, indent=2)

    def test_list_input(self):
        val = [1, 2, 3]
        assert coerce_str(val) == json.dumps(val, indent=2)

    def test_nested_dict(self):
        val = {"outer": {"inner": [1, 2]}}
        assert coerce_str(val) == json.dumps(val, indent=2)

    def test_empty_string_no_fallback(self):
        assert coerce_str("") == ""

    def test_empty_string_with_fallback(self):
        assert coerce_str("", fallback="default") == "default"

    def test_none_no_fallback(self):
        assert coerce_str(None) == ""

    def test_none_with_fallback(self):
        assert coerce_str(None, fallback="default") == "default"

    def test_int_passthrough(self):
        assert coerce_str(42) == "42"

    def test_zero_not_fallback(self):
        assert coerce_str(0) == "0"

    def test_true_not_fallback(self):
        assert coerce_str(True) == "True"

    def test_false_not_fallback(self):
        assert coerce_str(False) == "False"

    def test_empty_dict_serialized(self):
        assert coerce_str({}) == "{}"

    def test_empty_list_serialized(self):
        assert coerce_str([]) == "[]"
