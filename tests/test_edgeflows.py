"""
Baseline tests for CogniacEdgeFlow.
"""

import json

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestEdgeFlowRead:

    def test_get_all_edgeflows(self, cc):
        edgeflows = cc.get_all_edgeflows()
        assert isinstance(edgeflows, list)
        # tenant may or may not have edgeflows
        if len(edgeflows) > 0:
            ef = edgeflows[0]
            assert ef.gateway_id is not None

    def test_get_edgeflow(self, cc):
        edgeflows = cc.get_all_edgeflows()
        if len(edgeflows) == 0:
            pytest.skip("No edgeflows on test tenant")
        ef = edgeflows[0]
        fetched = cogniac.CogniacEdgeFlow.get(cc, ef.gateway_id)
        assert fetched.gateway_id == ef.gateway_id


# ---------------------------------------------------------------------------
# `edgeflows status --list-subsystems` discovery mode (no creds; mocked status)
# ---------------------------------------------------------------------------

class _FakeEdgeFlow:
    """Stand-in whose status() replays synthetic events. Mirrors the real
    high-frequency-crowds-low-frequency situation: many model_detections_*
    samples plus a few rarer subsystems."""

    def __init__(self, events):
        self._events = events
        self.last_status_kwargs = None

    def status(self, subsystem_name=None, limit=None, **kwargs):
        self.last_status_kwargs = dict(subsystem_name=subsystem_name, limit=limit, **kwargs)
        out = []
        for e in self._events:
            out.append(e)
            if limit and len(out) == limit:
                break
        return iter(out)


def _run_status(monkeypatch, argv, edgeflow):
    """Parse argv through the real CLI parser and run the bound handler with a
    mocked connection that returns `edgeflow`."""
    from cogniac.cli import build_parser
    import cogniac.cli as cli

    class _FakeConn:
        def get_edgeflow(self, edgeflow_id):
            return edgeflow

    monkeypatch.setattr(cli, "get_connection", lambda args=None: _FakeConn())
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


# Placeholder ids only — no customer identifiers.
_SYNTHETIC_EVENTS = [
    {"subsystem": "model_detections_aaaa", "edgeflow_timestamp": 100.0},
    {"subsystem": "model_detections_aaaa", "edgeflow_timestamp": 130.0},
    {"subsystem": "model_detections_bbbb", "edgeflow_timestamp": 131.0},
    {"subsystem": "http-input-cccc", "edgeflow_timestamp": 90.0},
    {"subsystem": "gpus", "edgeflow_timestamp": 50.0},
    {"subsystem": "cpu", "edgeflow_timestamp": 51.0},
    {"subsystem": "memory", "edgeflow_timestamp": 52.0},
    {"subsystem": "model_detections_aaaa", "edgeflow_timestamp": 160.0},
]


def test_list_subsystems_returns_distinct_with_count_and_last_seen(monkeypatch, capsys):
    ef = _FakeEdgeFlow(_SYNTHETIC_EVENTS)
    _run_status(monkeypatch, ["edgeflow", "status", "--edgeflow-id", "g1", "--list-subsystems"], ef)

    out = json.loads(capsys.readouterr().out)
    by_name = {row["subsystem"]: row for row in out}

    # distinct set, independent of per-subsystem frequency
    assert set(by_name) == {
        "model_detections_aaaa", "model_detections_bbbb",
        "http-input-cccc", "gpus", "cpu", "memory",
    }
    # sorted by subsystem name
    assert [r["subsystem"] for r in out] == sorted(by_name)
    # counts and last-seen aggregate across the scan
    assert by_name["model_detections_aaaa"]["count"] == 3
    assert by_name["model_detections_aaaa"]["last_seen"] == 160.0
    assert by_name["gpus"]["count"] == 1
    assert by_name["gpus"]["last_seen"] == 50.0


def test_list_subsystems_scan_cap_notice_to_stderr(monkeypatch, capsys):
    ef = _FakeEdgeFlow(_SYNTHETIC_EVENTS)
    _run_status(
        monkeypatch,
        ["edgeflow", "status", "--edgeflow-id", "g1", "--list-subsystems", "--scan-limit", "3"],
        ef,
    )
    captured = capsys.readouterr()
    # stdout stays clean JSON
    json.loads(captured.out)
    # the scan-cap diagnostic goes to stderr, not stdout
    notice = json.loads(captured.err)
    assert notice["scan_capped"] is True
    assert notice["scanned"] == 3
    # the scan honored --scan-limit, not the default --limit
    assert ef.last_status_kwargs["limit"] == 3


def test_status_without_flag_lists_events(monkeypatch, capsys):
    ef = _FakeEdgeFlow(_SYNTHETIC_EVENTS)
    _run_status(monkeypatch, ["edgeflow", "status", "--edgeflow-id", "g1", "--limit", "2"], ef)
    out = json.loads(capsys.readouterr().out)
    # normal listing path is unchanged: raw events, capped by --limit
    assert isinstance(out, list)
    assert len(out) == 2
    assert out[0]["subsystem"] == "model_detections_aaaa"
