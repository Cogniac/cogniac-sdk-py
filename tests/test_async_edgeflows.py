"""
Async integration tests for AsyncCogniacEdgeFlow.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestAsyncEdgeFlowRead:

    @pytest.mark.asyncio
    async def test_get_all_edgeflows(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            edgeflows = await cogniac.AsyncCogniacEdgeFlow.get_all(cc)
            assert isinstance(edgeflows, list)
            if len(edgeflows) > 0:
                ef = edgeflows[0]
                assert ef.gateway_id is not None

    @pytest.mark.asyncio
    async def test_get_edgeflow(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            edgeflows = await cogniac.AsyncCogniacEdgeFlow.get_all(cc)
            if len(edgeflows) == 0:
                pytest.skip("No edgeflows on test tenant")
            ef = edgeflows[0]
            fetched = await cogniac.AsyncCogniacEdgeFlow.get(cc, ef.gateway_id)
            assert fetched.gateway_id == ef.gateway_id

    @pytest.mark.asyncio
    async def test_status_generator(self):
        """Test the async status generator on the first available edgeflow."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            edgeflows = await cogniac.AsyncCogniacEdgeFlow.get_all(cc)
            if len(edgeflows) == 0:
                pytest.skip("No edgeflows on test tenant")
            ef = edgeflows[0]
            events = []
            async for event in ef.status(limit=3):
                events.append(event)
            # may be empty if edgeflow has no recent status, but shouldn't error
            assert isinstance(events, list)

    @pytest.mark.asyncio
    async def test_edgeflow_setattr_guard_raises(self):
        """Assigning to a server-managed key should raise, directing user to set()."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            edgeflows = await cogniac.AsyncCogniacEdgeFlow.get_all(cc)
            if len(edgeflows) == 0:
                pytest.skip("No edgeflows on test tenant")
            ef = edgeflows[0]
            with pytest.raises(AttributeError, match="set"):
                ef.name = "should-not-work"


# ---------------------------------------------------------------------------
# get_aggregated_stats: async parity for the per-model `model_detections_<id>`
# subsystem aggregation fix (no creds). Mirrors the sync regression in
# tests/test_edgeflows.py. Model-instance ids are placeholders.
# ---------------------------------------------------------------------------


def _async_edgeflow_with_status(events):
    # bypass __init__ / __setattr__ guard
    ef = object.__new__(cogniac.AsyncCogniacEdgeFlow)
    object.__setattr__(ef, '_edgeflow_keys', [])
    object.__setattr__(ef, 'gateway_id', 'gw-placeholder')

    async def fake_status(*args, **kwargs):
        msg = 'get_aggregated_stats must not use an exact-match subsystem filter'
        assert not kwargs.get('subsystem_name'), msg
        for ev in events:
            yield ev

    object.__setattr__(ef, 'status', fake_status)
    return ef


def _model_event(model_id, detections, media_pixels, gpu_pixels):
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


@pytest.mark.asyncio
async def test_async_aggregated_stats_sums_per_model_subsystems():
    events = [
        _model_event('m0001', detections=5, media_pixels=1000, gpu_pixels=2000),
        _model_event('m0002', detections=3, media_pixels=500, gpu_pixels=1500),
        _model_event('m0001', detections=2, media_pixels=100, gpu_pixels=400),
        {'subsystem': 'ifconfig', 'status': {'wan0': {'ip': '10.0.0.1'}}},
    ]
    ef = _async_edgeflow_with_status(events)
    stats = await ef.get_aggregated_stats(start=1000.0, end=1300.0)

    assert stats['total']['model_detections'] == 10
    assert stats['total']['aggregated_media_pixels'] == 1600
    assert stats['total']['aggregated_gpu_pixels'] == 3900
    assert set(stats['app']) == {'m0001', 'm0002'}
    assert stats['app']['m0001']['model_detections'] == 7


# ---------------------------------------------------------------------------
# status() must guarantee a top-level 'timestamp' on every yielded record.
# Async parity for the sync regression in tests/test_edgeflows.py: the backend
# omits 'timestamp' on a minority of records (they carry only
# gw_timestamp/cc_timestamp); status() aliases timestamp <- gw_timestamp so
# callers can sort/diff on record['timestamp'] uniformly, never clobbering an
# existing timestamp.  (no creds; mocked connection)
# ---------------------------------------------------------------------------


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _FakeAsyncConn:
    """A connection whose async _get returns a single-page status envelope."""

    def __init__(self, records):
        self._records = records

    async def _get(self, url, *args, **kwargs):
        return _FakeResp({'data': self._records, 'paging': {'next': None}})


def _async_edgeflow_with_conn(records):
    ef = object.__new__(cogniac.AsyncCogniacEdgeFlow)
    object.__setattr__(ef, '_edgeflow_keys', [])
    object.__setattr__(ef, 'gateway_id', 'gw-placeholder')
    object.__setattr__(ef, '_cc', _FakeAsyncConn(records))
    return ef


def _mixed_status_records():
    return [
        {'subsystem': 'http-input-a0001', 'status': {'n': 1},
         'cc_timestamp': 100.5, 'gw_timestamp': 100.0, 'timestamp': 100.0},
        {'subsystem': 'http-input-a0001', 'status': {'n': 2},
         'cc_timestamp': 101.5, 'gw_timestamp': 101.0},  # no 'timestamp'
        {'subsystem': 'http-input-a0001', 'status': {'n': 3},
         'cc_timestamp': 102.5, 'gw_timestamp': 102.0, 'timestamp': 102.0},
    ]


@pytest.mark.asyncio
async def test_async_status_guarantees_timestamp_on_every_record():
    ef = _async_edgeflow_with_conn(_mixed_status_records())
    records = [r async for r in ef.status()]
    assert len(records) == 3
    assert all('timestamp' in r for r in records)
    records.sort(key=lambda r: r['timestamp'])  # must not raise KeyError


@pytest.mark.asyncio
async def test_async_status_does_not_clobber_existing_timestamp():
    rec = {'subsystem': 's', 'status': {}, 'cc_timestamp': 9.0,
           'gw_timestamp': 7.0, 'timestamp': 5.0}
    ef = _async_edgeflow_with_conn([rec])
    out = [r async for r in ef.status()]
    assert out[0]['timestamp'] == 5.0  # original preserved, not 7.0


@pytest.mark.asyncio
async def test_async_status_aliases_missing_timestamp_to_gw_timestamp():
    rec = {'subsystem': 's', 'status': {}, 'cc_timestamp': 9.0,
           'gw_timestamp': 7.0}  # no 'timestamp'
    ef = _async_edgeflow_with_conn([rec])
    out = [r async for r in ef.status()]
    assert out[0]['timestamp'] == 7.0  # aliased to gw_timestamp
    assert out[0]['gw_timestamp'] == 7.0
    assert out[0]['cc_timestamp'] == 9.0
