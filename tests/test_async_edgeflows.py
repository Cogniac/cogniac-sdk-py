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


# ---------------------------------------------------------------------------
# metrics / all_metrics: async parity for the #171 param-forwarding fix.
# Mirrors the sync assertions in tests/test_edgeflows.py — async metrics()
# must send ef_id (NOT gateway_id) + tenant_id; all_metrics() must inject
# tenant_id. No creds; placeholder ids only.
# ---------------------------------------------------------------------------


class _AsyncCaptureResp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _AsyncCaptureConn:
    """Records the (url, params) of the last _get; awaitable _get returning a
    Grafana-shaped payload. Stands in for an AsyncCogniacConnection."""

    def __init__(self, tenant_id='tenant-placeholder'):
        self.tenant_id = tenant_id
        self.last_get = None

    async def _get(self, url, params=None, **kwargs):
        self.last_get = (url, params)
        return _AsyncCaptureResp({'status': 200, 'data': []})


def _async_ef_for_metrics(conn, gateway_id='gw-placeholder'):
    """An AsyncCogniacEdgeFlow bound to a capture connection, bypassing __init__."""
    ef = object.__new__(cogniac.AsyncCogniacEdgeFlow)
    object.__setattr__(ef, '_edgeflow_keys', [])
    object.__setattr__(ef, 'gateway_id', gateway_id)
    object.__setattr__(ef, '_cc', conn)
    return ef


@pytest.mark.asyncio
async def test_async_metrics_sends_ef_id_and_tenant_id_not_gateway_id():
    conn = _AsyncCaptureConn(tenant_id='tenant-placeholder')
    ef = _async_ef_for_metrics(conn, gateway_id='gw-placeholder')

    await ef.metrics(metric_name='cpu')

    url, params = conn.last_get
    assert url == '/1/metrics/ef'
    # the bug was sending gateway_id; the contract requires ef_id
    assert 'gateway_id' not in params
    assert params['ef_id'] == 'gw-placeholder'
    assert params['tenant_id'] == 'tenant-placeholder'
    assert params['metric_name'] == 'cpu'


@pytest.mark.asyncio
async def test_async_all_metrics_injects_tenant_id():
    conn = _AsyncCaptureConn(tenant_id='tenant-placeholder')

    await cogniac.AsyncCogniacEdgeFlow.all_metrics(conn, metric_name='cpu')

    url, params = conn.last_get
    assert url == '/1/metrics'
    assert params['tenant_id'] == 'tenant-placeholder'
    assert params['metric_name'] == 'cpu'
    # tenant-wide query must not be scoped to an ef
    assert 'ef_id' not in params


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


# ---------------------------------------------------------------------------
# health / get_all_health — async parity for the client-derived fleet health
# summary (#184). Mirrors the sync tests in tests/test_edgeflows.py.
# (no creds; mocked connection). Placeholder ids only.
# ---------------------------------------------------------------------------

import re
from time import time


class _AsyncHealthConn:
    """Fake async connection serving the tenant gateway list and one status
    envelope per gateway (latest record only). A per-gateway value that is an
    Exception is raised from that device's status GET.

    Exposes tenant_id directly: AsyncCogniacConnection has no `tenant`
    property, and the async get_all/get_all_health use connection.tenant_id."""

    def __init__(self, gateways, status_by_gateway):
        self.tenant_id = 'tenant-placeholder'
        self._gateways = gateways
        self._status = status_by_gateway
        self.status_urls = []

    async def _get(self, url, *args, **kwargs):
        if url == '/1/tenants/tenant-placeholder/gateways':
            return _FakeResp({'data': self._gateways})
        m = re.match(r'^/1/gateways/([^/?]+)/status\?(.*)$', url)
        assert m, "unexpected url %s" % url
        self.status_urls.append(url)
        records = self._status.get(m.group(1), [])
        if isinstance(records, Exception):
            raise records
        return _FakeResp({'data': records[:1], 'paging': {'next': None}})


def _gw(gateway_id, **extra):
    d = {'gateway_id': gateway_id, 'name': 'ef-%s' % gateway_id}
    d.update(extra)
    return d


@pytest.mark.asyncio
async def test_async_get_all_health_online_stale_and_no_records():
    now = time()
    gateways = [
        _gw('gw-online', deployment_group_id='dg-0001', current_workflow_id='wf-0001'),
        _gw('gw-stale'),
        _gw('gw-silent'),
    ]
    status = {
        'gw-online': [{'subsystem': 'cpu', 'cc_timestamp': now - 60.0,
                       'gw_timestamp': now - 65.0}],
        'gw-stale': [{'subsystem': 'cpu', 'cc_timestamp': now - 7200.0}],
        'gw-silent': [],
    }
    conn = _AsyncHealthConn(gateways, status)
    out = await cogniac.AsyncCogniacEdgeFlow.get_all_health(conn, stale_seconds=900)

    assert [r['gateway_id'] for r in out] == ['gw-online', 'gw-stale', 'gw-silent']
    by_id = {r['gateway_id']: r for r in out}
    assert by_id['gw-online']['online'] is True
    # last_seen is the cloud-receipt clock (cc_timestamp), not gw_timestamp
    assert by_id['gw-online']['last_seen'] == pytest.approx(now - 60.0)
    assert by_id['gw-online']['deployment_group_id'] == 'dg-0001'
    assert by_id['gw-online']['current_workflow_id'] == 'wf-0001'
    assert by_id['gw-stale']['online'] is False
    assert by_id['gw-stale']['deployment_group_id'] is None
    assert by_id['gw-silent']['last_seen'] is None
    assert by_id['gw-silent']['online'] is False
    # one bounded status GET per device
    assert len(conn.status_urls) == 3
    assert all('limit=1' in u and 'reverse=True' in u for u in conn.status_urls)


@pytest.mark.asyncio
async def test_async_get_all_health_empty_tenant():
    conn = _AsyncHealthConn([], {})
    assert await cogniac.AsyncCogniacEdgeFlow.get_all_health(conn) == []


@pytest.mark.asyncio
async def test_async_get_all_health_one_bad_device_degrades_not_aborts():
    # Mirrors the sync regression: a 404 ClientError from one device's status
    # GET (e.g. gateway deleted mid-sweep) degrades only that record — online
    # None (tri-state "could not determine") with the failure in `error` —
    # while every other device still reports normally.
    from cogniac.common import ClientError

    now = time()
    gateways = [
        _gw('gw-ok'),
        _gw('gw-gone', deployment_group_id='dg-0002'),
        _gw('gw-quiet'),
    ]
    status = {
        'gw-ok': [{'subsystem': 'cpu', 'cc_timestamp': now - 30.0}],
        'gw-gone': ClientError('gateway not found (404)', status_code=404),
        'gw-quiet': [],
    }
    conn = _AsyncHealthConn(gateways, status)
    out = await cogniac.AsyncCogniacEdgeFlow.get_all_health(conn, stale_seconds=900)

    assert [r['gateway_id'] for r in out] == ['gw-ok', 'gw-gone', 'gw-quiet']

    degraded = out[1]
    assert degraded['online'] is None
    assert degraded['last_seen'] is None
    assert '404' in degraded['error']
    assert degraded['deployment_group_id'] == 'dg-0002'

    assert out[0]['online'] is True and 'error' not in out[0]
    assert out[2]['online'] is False and 'error' not in out[2]


@pytest.mark.asyncio
async def test_async_instance_health():
    now = time()
    conn = _AsyncHealthConn([], {'gw-placeholder': [{'cc_timestamp': now - 5.0}]})
    ef = object.__new__(cogniac.AsyncCogniacEdgeFlow)
    object.__setattr__(ef, '_edgeflow_keys', [])
    object.__setattr__(ef, 'gateway_id', 'gw-placeholder')
    object.__setattr__(ef, 'name', 'ef-placeholder')
    object.__setattr__(ef, '_cc', conn)

    h = await ef.health()
    assert h['gateway_id'] == 'gw-placeholder'
    assert h['online'] is True
    assert h['last_seen'] == pytest.approx(now - 5.0)
    # fields absent on the gateway record surface as null, not AttributeError
    assert h['deployment_group_id'] is None
    assert h['current_workflow_id'] is None
