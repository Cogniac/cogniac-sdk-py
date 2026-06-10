"""
Live, read-only integration round-trips for the expanded coverage.

These require live Cogniac credentials (COG_API_KEY or COG_USER/COG_PASS, plus
COG_TENANT); they are skipped otherwise. Only read-only endpoints are
exercised — destructive create/delete operations are intentionally excluded.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestApplicationReadCoverage:

    def test_application_types_list_and_get(self, cc):
        types = cogniac.CogniacApplication.get_all_types(cc)
        items = types.get('data', types) if isinstance(types, dict) else types
        assert isinstance(items, (list, dict))
        # fetch one type by name if we can find a name
        name = None
        if isinstance(items, list) and items:
            name = items[0].get('name') if isinstance(items[0], dict) else None
        if name:
            one = cogniac.CogniacApplication.get_type(cc, name)
            assert isinstance(one, dict)

    def test_event_types_and_detections_pending(self, cc):
        apps = cc.get_all_applications()
        if not apps:
            pytest.skip("no applications on tenant")
        app = apps[0]
        ets = app.event_types()
        assert isinstance(ets, (list, dict))
        pending = app.detections_pending()
        assert isinstance(pending, (dict, int))

    def test_replay_status(self, cc):
        apps = cc.get_all_applications()
        if not apps:
            pytest.skip("no applications on tenant")
        status = apps[0].replay_status()
        assert isinstance(status, dict)

    def test_events_generator(self, cc):
        apps = cc.get_all_applications()
        if not apps:
            pytest.skip("no applications on tenant")
        # should not raise; may be empty
        evts = list(apps[0].events(limit=3))
        assert isinstance(evts, list)

    def test_consensus_history(self, cc):
        apps = cc.get_all_applications()
        if not apps:
            pytest.skip("no applications on tenant")
        hist = apps[0].consensus_history(limit=5)
        assert isinstance(hist, (dict, list))

    def test_performance_endpoints(self, cc):
        apps = cc.get_all_applications()
        if not apps:
            pytest.skip("no applications on tenant")
        app = apps[0]
        assert isinstance(app.performance_current_validation(limit=2), (dict, list))
        assert isinstance(app.performance_release_validation(limit=2), (dict, list))
        assert isinstance(app.performance_new_random(), (dict, list))

    def test_push_notifications(self, cc):
        apps = cc.get_all_applications()
        if not apps:
            pytest.skip("no applications on tenant")
        assert isinstance(apps[0].push_notifications(), (dict, list))

    def test_feedback_reads(self, cc):
        apps = cc.get_all_applications()
        if not apps:
            pytest.skip("no applications on tenant")
        app = apps[0]
        assert isinstance(app.feedback(limit=2), (dict, list))
        assert isinstance(app.feedback_request_count(), (dict, int))
        assert isinstance(app.pending_feedback_requests(), (dict, list))


@requires_live
class TestSubjectReadCoverage:

    def test_subject_consensus_history(self, cc):
        subjects = cc.get_all_subjects()
        if not subjects:
            pytest.skip("no subjects on tenant")
        hist = subjects[0].consensus_history(limit=5)
        assert isinstance(hist, (dict, list))

    def test_subject_detections_for_associated_media(self, cc):
        subjects = cc.get_all_subjects()
        for subject in subjects:
            assocs = list(subject.media_associations(limit=1))
            if assocs:
                media_id = assocs[0].get('media_id') or assocs[0].get('subject', {}).get('media_id')
                if media_id:
                    dets = subject.detections(media_id)
                    assert isinstance(dets, (dict, list))
                    return
        pytest.skip("no subject with an associated media item found")


@requires_live
class TestEdgeFlowReadCoverage:

    def test_metric_names(self, cc):
        names = cogniac.CogniacEdgeFlow.metric_names(cc)
        assert isinstance(names, (dict, list))

    def test_edgeflow_certificate_read(self, cc):
        efs = cc.get_all_edgeflows()
        if not efs:
            pytest.skip("no edgeflows on tenant")
        # certificate read may legitimately 404/403 depending on tenant config;
        # we only assert the call path works when it returns a value.
        try:
            cert = efs[0].get_certificate()
        except cogniac.ClientError:
            pytest.skip("no certificate configured / not permitted on this tenant")
        assert isinstance(cert, dict)


@requires_live
class TestCameraReadCoverage:

    def test_camera_genicam(self, cc):
        cams = cc.get_all_cameras()
        if not cams:
            pytest.skip("no cameras on tenant")
        try:
            xml = cams[0].genicam()
        except cogniac.ClientError:
            pytest.skip("camera has no genicam xml")
        assert isinstance(xml, str)


@requires_live
class TestDeploymentReadCoverage:

    def test_deployment_capacity_classes(self, cc):
        classes = cogniac.CogniacDeploymentCapacityClass.get_all(cc)
        assert isinstance(classes, list)
        if classes:
            cid = getattr(classes[0], 'deployment_capacity_class_id', None)
            if cid:
                one = cogniac.CogniacDeploymentCapacityClass.get(cc, cid)
                assert one.deployment_capacity_class_id == cid

    def test_deployments_list_and_subresources(self, cc):
        groups = cc.get_all_deployments()
        assert isinstance(groups, list)
        if not groups:
            pytest.skip("no deployment groups on tenant")
        dg = groups[0]
        assert isinstance(dg.edgeflows(), (list, dict))
        assert isinstance(dg.history(), (dict, list))
        assert isinstance(dg.prepull_status(), (dict, list))


@requires_live
class TestWorkflowReadCoverage:

    def test_workflows_list(self, cc):
        workflows = cc.get_all_workflows()
        assert isinstance(workflows, list)

    def test_edgeflow_targets(self, cc):
        targets = cogniac.CogniacWorkflow.edgeflow_targets(cc)
        assert isinstance(targets, (dict, list))

    def test_workflow_get_roundtrip(self, cc):
        workflows = cc.get_all_workflows()
        if not workflows:
            pytest.skip("no workflows on tenant")
        wid = getattr(workflows[0], 'workflow_id', None)
        if not wid:
            pytest.skip("workflow has no workflow_id")
        fetched = cogniac.CogniacWorkflow.get(cc, wid)
        assert fetched.workflow_id == wid


@requires_live
class TestUserReadCoverage:

    def test_users_current_tenants(self, cc):
        tenants = cogniac.CogniacUser.tenants(cc, user_id='current')
        assert isinstance(tenants, dict)
        assert 'tenants' in tenants

    def test_users_query(self, cc):
        result = cogniac.CogniacUser.get_all(cc)
        assert isinstance(result, (dict, list))


@requires_live
class TestBuildReadCoverage:

    def test_builds_list(self, cc):
        # may 404/403 if the tenant has no build access; treat as skip
        try:
            builds = cogniac.CogniacBuild.get_all(cc)
        except cogniac.ClientError:
            pytest.skip("builds not available on this tenant")
        assert isinstance(builds, list)


@requires_live
class TestTenantReadCoverage:

    def test_tenant_invites_read(self, cc):
        invites = cc.tenant.invites()
        assert isinstance(invites, (dict, list))
