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
# Real status events key the timestamp as cc_timestamp (cloud-receipt), never
# edgeflow_timestamp; the fixtures mirror that so last_seen is exercised.
_SYNTHETIC_EVENTS = [
    {"subsystem": "model_detections_aaaa", "cc_timestamp": 100.0},
    {"subsystem": "model_detections_aaaa", "cc_timestamp": 130.0},
    {"subsystem": "model_detections_bbbb", "cc_timestamp": 131.0},
    {"subsystem": "http-input-cccc", "cc_timestamp": 90.0},
    {"subsystem": "gpus", "cc_timestamp": 50.0},
    {"subsystem": "cpu", "cc_timestamp": 51.0},
    {"subsystem": "memory", "cc_timestamp": 52.0},
    {"subsystem": "model_detections_aaaa", "cc_timestamp": 160.0},
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


def test_list_subsystems_last_seen_falls_back_to_gw_timestamp(monkeypatch, capsys):
    # An event without cc_timestamp/timestamp must still populate last_seen
    # from gw_timestamp, rather than reporting null.
    events = [{"subsystem": "gpus", "gw_timestamp": 77.0}]
    ef = _FakeEdgeFlow(events)
    _run_status(monkeypatch, ["edgeflow", "status", "--edgeflow-id", "g1", "--list-subsystems"], ef)
    out = json.loads(capsys.readouterr().out)
    assert out == [{"subsystem": "gpus", "last_seen": 77.0, "count": 1}]


# ---------------------------------------------------------------------------
# get_aggregated_stats: per-model `model_detections_<id>` subsystem aggregation
# (no creds). Regression for the bug where the code passed the literal
# subsystem filter 'model_detections*' to status() -- an exact-match filter
# that matches nothing, so every device reporting per-model subsystems
# (all CloudFlows) aggregated to zero. The fix pulls all subsystems for the
# window and sums every event whose subsystem name starts with
# 'model_detections_'. Model-instance ids are placeholders.
# ---------------------------------------------------------------------------


def _edgeflow_with_status(events):
    """A CogniacEdgeFlow whose status() yields the given synthetic events.

    Bypasses __init__ (which would try to set a url_prefix / open a session).
    """
    # bypass CogniacEdgeFlow.__init__ / __setattr__ (which auto-POSTs)
    ef = object.__new__(cogniac.CogniacEdgeFlow)
    object.__setattr__(ef, '_edgeflow_keys', [])
    object.__setattr__(ef, 'gateway_id', 'gw-placeholder')

    def fake_status(*args, **kwargs):
        # The fix must not pass an exact-match subsystem filter (that is the
        # bug); it should pull all subsystems and filter client-side.
        msg = 'get_aggregated_stats must not use an exact-match subsystem filter'
        assert not kwargs.get('subsystem_name'), msg
        for ev in events:
            yield ev

    object.__setattr__(ef, 'status', fake_status)
    return ef


def _model_event(model_id, detections, media_pixels, gpu_pixels):
    """A status event as reported per deployed model.

    The subsystem is 'model_detections_<model_id>' and the status dict is
    keyed by the same <model_id>.
    """
    return {
        'subsystem': 'model_detections_%s' % model_id,
        'status': {
            model_id: {
                'model_detections': detections,
                'aggregated_media_pixels': media_pixels,
                'aggregated_gpu_pixels': gpu_pixels,
            }
        },
    }


def test_aggregated_stats_sums_per_model_subsystems():
    events = [
        _model_event('m0001', detections=5, media_pixels=1000, gpu_pixels=2000),
        _model_event('m0002', detections=3, media_pixels=500, gpu_pixels=1500),
        # second window for the first model -> accumulates into the same app
        _model_event('m0001', detections=2, media_pixels=100, gpu_pixels=400),
    ]
    ef = _edgeflow_with_status(events)
    stats = ef.get_aggregated_stats(start=1000.0, end=1300.0)

    assert stats['total']['model_detections'] == 10
    assert stats['total']['aggregated_media_pixels'] == 1600
    assert stats['total']['aggregated_gpu_pixels'] == 3900

    # per-model rollup, keyed by model-instance id
    assert set(stats['app']) == {'m0001', 'm0002'}
    assert stats['app']['m0001'] == {
        'model_detections': 7,
        'aggregated_media_pixels': 1100,
        'aggregated_gpu_pixels': 2400,
    }
    assert stats['app']['m0002'] == {
        'model_detections': 3,
        'aggregated_media_pixels': 500,
        'aggregated_gpu_pixels': 1500,
    }


def test_aggregated_stats_ignores_unrelated_subsystems():
    # Pulling all subsystems means unrelated ones must be skipped, not summed.
    events = [
        {'subsystem': 'ifconfig', 'status': {'wan0': {'ip': '10.0.0.1'}}},
        _model_event('m0001', detections=4, media_pixels=800, gpu_pixels=1600),
        {'subsystem': 'ping', 'status': {'ping_id': 'x'}},
    ]
    ef = _edgeflow_with_status(events)
    stats = ef.get_aggregated_stats(start=1000.0, end=1300.0)

    assert stats['total']['model_detections'] == 4
    assert stats['total']['aggregated_media_pixels'] == 800
    assert stats['total']['aggregated_gpu_pixels'] == 1600
    assert set(stats['app']) == {'m0001'}


def test_aggregated_stats_handles_model_id_with_underscores():
    # Stripping the 'model_detections_' prefix (rather than split('_')[2])
    # keeps a model id that itself contains underscores intact.
    mid = 'tenant_abc_42'
    events = [_model_event(mid, detections=1, media_pixels=10, gpu_pixels=20)]
    ef = _edgeflow_with_status(events)
    stats = ef.get_aggregated_stats(start=1000.0, end=1300.0)

    assert stats['total']['model_detections'] == 1
    assert set(stats['app']) == {mid}
    assert stats['app'][mid]['aggregated_gpu_pixels'] == 20


# ---------------------------------------------------------------------------
# status() must guarantee a top-level 'timestamp' on every yielded record.
# The backend omits 'timestamp' on a minority of records (they carry only
# gw_timestamp/cc_timestamp); status() aliases timestamp <- gw_timestamp so
# callers can sort/diff on record['timestamp'] uniformly, never clobbering an
# existing timestamp.  (no creds; mocked connection)
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeConn:
    """A connection whose _get returns a single-page status envelope."""

    def __init__(self, records):
        self._records = records

    def _get(self, url, *args, **kwargs):
        return _FakeResp({'data': self._records, 'paging': {'next': None}})


def _edgeflow_with_conn(records):
    ef = object.__new__(cogniac.CogniacEdgeFlow)
    object.__setattr__(ef, '_edgeflow_keys', [])
    object.__setattr__(ef, 'gateway_id', 'gw-placeholder')
    object.__setattr__(ef, '_cc', _FakeConn(records))
    return ef


def _mixed_status_records():
    # Mirror the real non-uniformity: some records carry a top-level
    # 'timestamp', some carry only gw_timestamp/cc_timestamp.
    return [
        {'subsystem': 'http-input-a0001', 'status': {'n': 1},
         'cc_timestamp': 100.5, 'gw_timestamp': 100.0, 'timestamp': 100.0},
        {'subsystem': 'http-input-a0001', 'status': {'n': 2},
         'cc_timestamp': 101.5, 'gw_timestamp': 101.0},  # no 'timestamp'
        {'subsystem': 'http-input-a0001', 'status': {'n': 3},
         'cc_timestamp': 102.5, 'gw_timestamp': 102.0, 'timestamp': 102.0},
    ]


def test_status_guarantees_timestamp_on_every_record():
    ef = _edgeflow_with_conn(_mixed_status_records())
    records = list(ef.status())
    assert len(records) == 3
    # every yielded record now has a top-level timestamp -> safe to sort
    assert all('timestamp' in r for r in records)
    records.sort(key=lambda r: r['timestamp'])  # must not raise KeyError


def test_status_does_not_clobber_existing_timestamp():
    # A record that already has a distinct 'timestamp' keeps its own value and
    # is NOT overwritten by gw_timestamp.
    rec = {'subsystem': 's', 'status': {}, 'cc_timestamp': 9.0,
           'gw_timestamp': 7.0, 'timestamp': 5.0}
    ef = _edgeflow_with_conn([rec])
    out = list(ef.status())
    assert out[0]['timestamp'] == 5.0  # original preserved, not 7.0


def test_status_aliases_missing_timestamp_to_gw_timestamp():
    rec = {'subsystem': 's', 'status': {}, 'cc_timestamp': 9.0,
           'gw_timestamp': 7.0}  # no 'timestamp'
    ef = _edgeflow_with_conn([rec])
    out = list(ef.status())
    assert out[0]['timestamp'] == 7.0  # aliased to gw_timestamp
    # the source clocks are left intact
    assert out[0]['gw_timestamp'] == 7.0
    assert out[0]['cc_timestamp'] == 9.0
