"""
Baseline tests for CogniacEdgeFlow.
"""

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
