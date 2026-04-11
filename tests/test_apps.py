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
