"""
Baseline tests for CogniacApplication.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestAppRead:

    def test_get_all_applications(self, cc):
        apps = cc.get_all_applications()
        assert isinstance(apps, list)
        assert len(apps) > 0
        app = apps[0]
        assert app.application_id is not None
        assert app.name is not None

    def test_get_application(self, cc):
        apps = cc.get_all_applications()
        first = apps[0]
        fetched = cc.get_application(first.application_id)
        assert fetched.application_id == first.application_id
        assert fetched.name == first.name

    def test_app_str(self, cc):
        apps = cc.get_all_applications()
        app = apps[0]
        text = str(app)
        assert app.name in text

    def test_app_pending_feedback(self, cc):
        apps = cc.get_all_applications()
        app = apps[0]
        pending = app.pending_feedback()
        assert isinstance(pending, int)

    def test_app_detections_generator(self, cc):
        """Verify the paginated detections generator yields results."""
        apps = cc.get_all_applications()
        # find an app that likely has detections
        for app in apps:
            dets = list(app.detections(limit=3))
            if len(dets) > 0:
                assert 'media' in dets[0] or 'media_id' in dets[0]
                return
        pytest.skip("No apps with detections found")

    def test_app_evaluation_metrics(self, cc):
        """Find an app with eval metrics configured and validate response shape."""
        apps = cc.get_all_applications()
        for app in apps:
            metrics = app.evaluation_metrics()
            items = metrics.get('data', metrics) if isinstance(metrics, dict) else metrics
            if isinstance(items, list) and len(items) > 0:
                m = items[0]
                assert 'evaluation_metric_hash' in m
                assert 'evaluation_metric' in m
                assert 'name' in m['evaluation_metric']
                return
        pytest.skip("No apps with evaluation metrics configured")

    def test_app_leaderboard(self, cc):
        """Find an app with a ready leaderboard snapshot and validate response shape."""
        apps = cc.get_all_applications()
        for app in apps:
            result = app.leaderboard()
            if isinstance(result, dict) and 'snapshot' in result:
                assert result.get('app_id') == app.application_id
                assert 'primary_evaluation_metric_hash' in result
                assert isinstance(result['snapshot'], list)
                return
        pytest.skip("No app with a ready leaderboard snapshot found")

    def test_app_leaderboard_validates_args(self, cc):
        """Bad enum values should raise ValueError before any HTTP call."""
        apps = cc.get_all_applications()
        app = apps[0]
        with pytest.raises(ValueError):
            app.leaderboard(set_assignment='bogus')
        with pytest.raises(ValueError):
            app.leaderboard(snapshot_type='bogus')
        with pytest.raises(ValueError):
            app.leaderboard(eval_metrics='bogus')
