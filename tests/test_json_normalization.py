"""
Unit tests for app_data / custom_data JSON-string normalization (issue #157).

These tests do NOT require live credentials — they mock the HTTP layer.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from cogniac.common import parse_json_str
from cogniac.subject import CogniacSubject


# ---------------------------------------------------------------------------
# parse_json_str unit tests
# ---------------------------------------------------------------------------

class TestParseJsonStr:

    def test_dict_passthrough(self):
        val = {"key": "value", "num": 42}
        assert parse_json_str(val) is val

    def test_list_passthrough(self):
        val = [1, 2, 3]
        assert parse_json_str(val) is val

    def test_none_passthrough(self):
        assert parse_json_str(None) is None

    def test_int_passthrough(self):
        assert parse_json_str(42) == 42

    def test_string_dict_parsed(self):
        s = '{"score": 0.95, "class": "defect"}'
        result = parse_json_str(s)
        assert result == {"score": 0.95, "class": "defect"}

    def test_string_list_parsed(self):
        s = '[1, 2, 3]'
        assert parse_json_str(s) == [1, 2, 3]

    def test_invalid_json_string_returned_as_is(self):
        s = "not valid json"
        assert parse_json_str(s) == s

    def test_empty_string_returned_as_is(self):
        assert parse_json_str("") == ""


# ---------------------------------------------------------------------------
# media_associations normalization integration test
# ---------------------------------------------------------------------------

def _make_subject(cc):
    """Build a CogniacSubject without a live API call."""
    data = {
        "subject_uid": "test-uid-001",
        "name": "test-subject",
        "tenant_id": "test-tenant",
    }
    return CogniacSubject(cc, data)


def _mock_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


class TestMediaAssociationsNormalization:

    def _make_page(self, app_data, custom_data=None):
        return {
            "data": [{
                "subject": {
                    "media_id": "m001",
                    "subject_uid": "test-uid-001",
                    "probability": 0.9,
                    "app_data_type": "box",
                    "app_data": app_data,
                },
                "media": {
                    "media_id": "m001",
                    "custom_data": custom_data,
                },
                "focus": None,
            }],
            "paging": {},
        }

    def test_app_data_string_is_parsed(self):
        cc = MagicMock()
        subject = _make_subject(cc)

        app_data_dict = {"score": 0.95, "boxes": [{"x0": 10, "y0": 20, "x1": 100, "y1": 200}]}
        page = self._make_page(app_data=json.dumps(app_data_dict))
        cc._get.return_value = _mock_response(page)

        assocs = list(subject.media_associations(limit=1))
        assert len(assocs) == 1
        result = assocs[0]["subject"]["app_data"]
        assert isinstance(result, dict), f"Expected dict, got {type(result)}: {result!r}"
        assert result == app_data_dict

    def test_app_data_dict_is_unchanged(self):
        cc = MagicMock()
        subject = _make_subject(cc)

        app_data_dict = {"score": 0.9}
        page = self._make_page(app_data=app_data_dict)
        cc._get.return_value = _mock_response(page)

        assocs = list(subject.media_associations(limit=1))
        assert assocs[0]["subject"]["app_data"] == app_data_dict

    def test_app_data_none_is_unchanged(self):
        cc = MagicMock()
        subject = _make_subject(cc)

        page = self._make_page(app_data=None)
        cc._get.return_value = _mock_response(page)

        assocs = list(subject.media_associations(limit=1))
        assert assocs[0]["subject"]["app_data"] is None

    def test_custom_data_string_is_parsed(self):
        cc = MagicMock()
        subject = _make_subject(cc)

        custom = {"tag": "batch-A", "run": 7}
        page = self._make_page(app_data=None, custom_data=json.dumps(custom))
        cc._get.return_value = _mock_response(page)

        assocs = list(subject.media_associations(limit=1))
        result = assocs[0]["media"]["custom_data"]
        assert isinstance(result, dict)
        assert result == custom
