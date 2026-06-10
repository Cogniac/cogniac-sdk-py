"""
Non-live smoke tests for the expanded SDK + CLI coverage.

These tests do NOT require credentials. They verify:
  - every new method exists on the sync and async entity classes;
  - the new public entity classes are importable from the package root;
  - the CLI parser builds and every new command/alias resolves to a handler;
  - the resource-alias helper expands sing/plur + abbreviation/synonym variants.
"""

import inspect
import pytest

import cogniac
from cogniac.cli import build_parser, resource_aliases


# ---------------------------------------------------------------------------
# Package exports
# ---------------------------------------------------------------------------

def test_new_classes_exported():
    for name in [
        'CogniacDeployment', 'CogniacDeploymentCapacityClass',
        'CogniacWorkflow', 'CogniacBuild',
        'AsyncCogniacDeployment', 'AsyncCogniacDeploymentCapacityClass',
        'AsyncCogniacWorkflow', 'AsyncCogniacBuild',
    ]:
        assert hasattr(cogniac, name), "cogniac.%s should be exported" % name


# ---------------------------------------------------------------------------
# SDK method existence — sync and async paired
# ---------------------------------------------------------------------------

# (class, [method names]) — methods must exist on both the sync class and its
# async counterpart.
_APP_METHODS = [
    'classify', 'donate_model', 'export_model_to_meraki',
    'replay_status', 'replay_start', 'replay_stop', 'detections_pending',
    'event_types', 'events', 'consensus_history',
    'performance_current_validation', 'performance_release_validation',
    'performance_new_random', 'model_performance',
    'push_notifications', 'subscribe_push',
    'feedback', 'feedback_request', 'submit_feedback', 'feedback_request_count',
    'pending_feedback_requests', 'purge_feedback', 'delete_feedback_requests',
    'create_evaluation_metric', 'register_default_evaluation_metric',
    'copy_evaluation_metrics',
    'consensus_releases', 'consensus_release', 'consensus_release_items',
    'consensus_release_upstream_assertions', 'consensus_detection_release',
    'labeling_image_encoder', 'labeling_mask_decoder', 'labeling_mask_decoder_head',
]

_APP_CLASSMETHODS = ['get_all_types', 'get_type']

_SUBJECT_METHODS = ['detections', 'consensus_history', 'bulk_disassociate']
_MEDIA_METHODS = ['share', 'create_detection', 'embeddings']
_EDGEFLOW_METHODS = ['delete', 'get_certificate', 'set_certificate',
                     'replace_certificate', 'delete_certificate', 'metrics']
_EDGEFLOW_CLASSMETHODS = ['create', 'metric_names', 'all_metrics']
_TENANT_METHODS = ['get_edgeflow_certificate', 'set_edgeflow_certificate',
                   'delete_edgeflow_certificate', 'delete_meraki_api_key',
                   'invites', 'create_invite', 'delete_invite']
_NETCAM_METHODS = ['genicam', 'upload_genicam']


@pytest.mark.parametrize("method", _APP_METHODS)
def test_application_methods_exist(method):
    assert callable(getattr(cogniac.CogniacApplication, method, None)), \
        "CogniacApplication.%s missing" % method
    assert callable(getattr(cogniac.AsyncCogniacApplication, method, None)), \
        "AsyncCogniacApplication.%s missing" % method


@pytest.mark.parametrize("method", _APP_CLASSMETHODS)
def test_application_classmethods_exist(method):
    assert callable(getattr(cogniac.CogniacApplication, method, None))
    assert callable(getattr(cogniac.AsyncCogniacApplication, method, None))


@pytest.mark.parametrize("method", _SUBJECT_METHODS)
def test_subject_methods_exist(method):
    assert callable(getattr(cogniac.CogniacSubject, method, None))
    assert callable(getattr(cogniac.AsyncCogniacSubject, method, None))


@pytest.mark.parametrize("method", _MEDIA_METHODS)
def test_media_methods_exist(method):
    assert callable(getattr(cogniac.CogniacMedia, method, None))
    assert callable(getattr(cogniac.AsyncCogniacMedia, method, None))


@pytest.mark.parametrize("method", _EDGEFLOW_METHODS)
def test_edgeflow_methods_exist(method):
    assert callable(getattr(cogniac.CogniacEdgeFlow, method, None))
    assert callable(getattr(cogniac.AsyncCogniacEdgeFlow, method, None))


@pytest.mark.parametrize("method", _EDGEFLOW_CLASSMETHODS)
def test_edgeflow_classmethods_exist(method):
    assert callable(getattr(cogniac.CogniacEdgeFlow, method, None))
    assert callable(getattr(cogniac.AsyncCogniacEdgeFlow, method, None))


@pytest.mark.parametrize("method", _TENANT_METHODS)
def test_tenant_methods_exist(method):
    assert callable(getattr(cogniac.CogniacTenant, method, None))
    assert callable(getattr(cogniac.AsyncCogniacTenant, method, None))


@pytest.mark.parametrize("method", _NETCAM_METHODS)
def test_network_camera_methods_exist(method):
    assert callable(getattr(cogniac.CogniacNetworkCamera, method, None))
    assert callable(getattr(cogniac.AsyncCogniacNetworkCamera, method, None))


@pytest.mark.parametrize("method", ['get_all', 'get_by_id', 'delete_by_id',
                                    'tenants', 'request_password_reset',
                                    'invites', 'respond_invite'])
def test_user_classmethods_exist(method):
    assert callable(getattr(cogniac.CogniacUser, method, None))
    assert callable(getattr(cogniac.AsyncCogniacUser, method, None))


@pytest.mark.parametrize("method", ['get_all', 'get', 'create', 'delete',
                                    'edgeflows', 'history', 'prepull_status',
                                    'prepull_start', 'set_target_workflow'])
def test_deployment_methods_exist(method):
    assert hasattr(cogniac.CogniacDeployment, method)
    assert hasattr(cogniac.AsyncCogniacDeployment, method)


@pytest.mark.parametrize("method", ['get_all', 'get'])
def test_deployment_capacity_methods_exist(method):
    assert hasattr(cogniac.CogniacDeploymentCapacityClass, method)
    assert hasattr(cogniac.AsyncCogniacDeploymentCapacityClass, method)


@pytest.mark.parametrize("method", ['get_all', 'get', 'create', 'delete',
                                    'edgeflow_targets', 'new_version', 'get_version'])
def test_workflow_methods_exist(method):
    assert hasattr(cogniac.CogniacWorkflow, method)
    assert hasattr(cogniac.AsyncCogniacWorkflow, method)


@pytest.mark.parametrize("method", ['get_all', 'get', 'create', 'delete', 'names', 'lint'])
def test_build_methods_exist(method):
    assert hasattr(cogniac.CogniacBuild, method)
    assert hasattr(cogniac.AsyncCogniacBuild, method)


def test_connection_convenience_methods():
    for name in ['edgeflows', 'gateways', 'get_all_deployments', 'get_deployment',
                 'get_all_workflows', 'get_workflow']:
        assert callable(getattr(cogniac.CogniacConnection, name, None)), \
            "CogniacConnection.%s missing" % name


def test_gateways_is_deprecated_alias_of_edgeflows():
    # gateways() must remain as a (deprecated) alias that delegates to edgeflows()
    assert callable(cogniac.CogniacConnection.gateways)
    src = inspect.getsource(cogniac.CogniacConnection.gateways)
    assert 'edgeflows' in src


# ---------------------------------------------------------------------------
# Async/sync parity — the async class must expose every public method the sync
# class does (for the resources we extended).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sync_cls,async_cls", [
    (cogniac.CogniacApplication, cogniac.AsyncCogniacApplication),
    (cogniac.CogniacSubject, cogniac.AsyncCogniacSubject),
    (cogniac.CogniacMedia, cogniac.AsyncCogniacMedia),
    (cogniac.CogniacEdgeFlow, cogniac.AsyncCogniacEdgeFlow),
    (cogniac.CogniacTenant, cogniac.AsyncCogniacTenant),
    (cogniac.CogniacUser, cogniac.AsyncCogniacUser),
    (cogniac.CogniacNetworkCamera, cogniac.AsyncCogniacNetworkCamera),
    (cogniac.CogniacDeployment, cogniac.AsyncCogniacDeployment),
    (cogniac.CogniacWorkflow, cogniac.AsyncCogniacWorkflow),
    (cogniac.CogniacBuild, cogniac.AsyncCogniacBuild),
])
def test_new_methods_have_async_counterparts(sync_cls, async_cls):
    # only check the methods this PR adds (a curated set per resource);
    # the historical surface is covered by the explicit lists above.
    extended = {
        'CogniacApplication': _APP_METHODS + _APP_CLASSMETHODS,
        'CogniacSubject': _SUBJECT_METHODS,
        'CogniacMedia': _MEDIA_METHODS,
        'CogniacEdgeFlow': _EDGEFLOW_METHODS + _EDGEFLOW_CLASSMETHODS,
        'CogniacTenant': _TENANT_METHODS,
        'CogniacUser': ['get_all', 'get_by_id', 'delete_by_id', 'tenants',
                        'request_password_reset', 'invites', 'respond_invite'],
        'CogniacNetworkCamera': _NETCAM_METHODS,
        'CogniacDeployment': ['get_all', 'get', 'create', 'delete', 'edgeflows',
                              'history', 'prepull_status', 'prepull_start',
                              'set_target_workflow'],
        'CogniacWorkflow': ['get_all', 'get', 'create', 'delete', 'edgeflow_targets',
                            'new_version', 'get_version'],
        'CogniacBuild': ['get_all', 'get', 'create', 'delete', 'names', 'lint'],
    }[sync_cls.__name__]
    for m in extended:
        assert hasattr(async_cls, m), "%s missing async method %s" % (async_cls.__name__, m)


# ---------------------------------------------------------------------------
# Alias helper
# ---------------------------------------------------------------------------

def test_alias_singular_plural():
    aliases = resource_aliases('application')
    for a in ['app', 'apps', 'applications']:
        assert a in aliases
    assert 'application' not in aliases  # canonical excluded


def test_alias_synonyms_gateway():
    aliases = resource_aliases('edgeflow')
    for a in ['edgeflows', 'gateway', 'gateways']:
        assert a in aliases


def test_alias_compound_certificate():
    aliases = resource_aliases('edgeflow-certificate')
    # abbreviation 'cert' and synonym 'gateway' combine across both tokens
    for a in ['edgeflow-cert', 'gateway-certificate', 'gateway-cert', 'edgeflows-cert']:
        assert a in aliases, "%s should be an alias of edgeflow-certificate" % a


def test_alias_abbreviations():
    assert 'eval' in {x for grp in __import__('cogniac.cli', fromlist=['_SYNONYM_GROUPS'])._SYNONYM_GROUPS for x in grp}
    # perf <-> performance and eval <-> evaluation expand in compounds
    aliases = resource_aliases('deployment-capacity')
    assert 'deployment-capacities' in aliases


def test_alias_media_uncountable():
    # 'media' is uncountable: it must NOT gain a 'medias' alias
    assert resource_aliases('media') == []
    assert resource_aliases('media-embeddings') == []


# ---------------------------------------------------------------------------
# CLI parser builds + commands resolve to handlers
# ---------------------------------------------------------------------------

def test_parser_builds():
    assert build_parser() is not None


@pytest.mark.parametrize("argv", [
    ['application', 'list'],
    ['apps', 'get', 'A1'],
    ['app', 'classify', 'A1', 'img.jpg'],
    ['application', 'donate-model', 'A1', 'A2'],
    ['app', 'export-meraki', 'A1'],
    ['application', 'replay', 'A1'],
    ['app', 'replay-start', 'A1'],
    ['app', 'replay-stop', 'A1'],
    ['application', 'detections-pending', 'A1'],
    ['app', 'event-types', 'A1'],
    ['app', 'events', 'A1', '--limit', '5'],
    ['app', 'consensus-history', 'A1'],
    ['app', 'performance-current', 'A1'],
    ['app', 'performance-release', 'A1'],
    ['app', 'performance-new-random', 'A1'],
    ['app', 'push', 'A1'],
    ['app', 'push-subscribe', 'A1', '--device-id', 'D1'],
    ['app', 'consensus-releases', 'A1'],
    ['app', 'consensus-release', 'A1', 'R1'],
    ['app', 'consensus-release-items', 'A1', 'R1'],
    ['app', 'consensus-release-upstream', 'A1', 'R1'],
    ['app', 'consensus-detection-releases', 'A1'],
    ['app', 'evaluation-metrics', 'A1'],
    ['app', 'evaluation-metrics-create', 'A1'],
    ['app', 'evaluation-metrics-register-default', 'A1'],
    ['app', 'evaluation-metrics-copy', 'S1', 'T1'],
    ['application-types', 'list'],
    ['app-type', 'get', 'box_detection'],
    ['application-feedback', 'list', 'A1'],
    ['app-feedback', 'get', 'A1', 'F1'],
    ['app-feedback', 'create', 'A1'],
    ['app-feedback', 'count', 'A1'],
    ['app-feedback', 'pending', 'A1'],
    ['app-feedback', 'purge', 'A1'],
    ['app-feedback', 'purge-requests', 'A1'],
    ['application-model', 'performance', 'A1', '--subject-uid', 's1'],
    ['application-build', 'list'],
    ['app-build', 'get', 'B1'],
    ['app-build', 'create'],
    ['app-build', 'delete', 'B1'],
    ['app-build', 'names'],
    ['app-build', 'lint', 'f.py'],
    ['application-label', 'image-encoder', 'A1'],
    ['application-label', 'image-encoder-upload', 'A1', 'f.png'],
    ['application-label', 'mask-decoder', 'A1'],
    ['application-label', 'mask-decoder-head', 'A1'],
    ['media-embeddings', 'M1'],
    ['subject', 'consensus-history', 's1'],
    ['subject', 'detections', 's1', 'M1'],
    ['media', 'share', 'M1'],
    ['media', 'create-detection', 'M1'],
    ['edgeflow', 'create'],
    ['edgeflow', 'delete', 'g1'],
    ['edgeflow-certificate', 'get', 'g1'],
    ['edgeflow-certificate', 'set', 'g1'],
    ['edgeflow-certificate', 'replace', 'g1'],
    ['edgeflow-certificate', 'delete', 'g1'],
    ['edgeflow-metrics', 'list'],
    ['edgeflow-metrics', 'list', 'g1'],
    ['edgeflow-metric-names'],
    ['camera', 'genicam', 'c1'],
    ['deployment', 'list'],
    ['deployment', 'get', 'd1'],
    ['deployment', 'create'],
    ['deployment', 'delete', 'd1'],
    ['deployment', 'edgeflows', 'd1'],
    ['deployment', 'history', 'd1'],
    ['deployment', 'prepull', 'd1'],
    ['deployment', 'prepull-start', 'd1', 'w1'],
    ['deployment', 'target-workflow', 'd1', 'w1'],
    ['deployment-capacity', 'list'],
    ['deployment-capacity', 'get', 'cc1'],
    ['workflow', 'list'],
    ['workflow', 'get', 'w1'],
    ['workflow', 'create'],
    ['workflow', 'delete', 'w1'],
    ['workflow', 'edgeflow-targets'],
    ['workflow-version', 'new', 'w1', '--body', '{}'],
    ['workflow-version', 'get', 'b1', '3'],
    ['users', 'list'],
    ['users', 'get', 'u1'],
    ['users', 'delete', 'u1'],
    ['users', 'tenants', 'current'],
    ['users', 'request-password-reset', 'a@b.co'],
    ['tenant-edgeflow-certificate', 'get'],
    ['tenant-edgeflow-certificate', 'set'],
    ['tenant-edgeflow-certificate', 'delete'],
    ['tenant-meraki-key', 'delete'],
    ['tenant-import', 'KEY123'],
])
def test_command_resolves_to_handler(argv):
    parser = build_parser()
    ns = parser.parse_args(argv)
    assert hasattr(ns, 'func') and callable(ns.func), "no handler for %r" % (argv,)


@pytest.mark.parametrize("alias_argv,canonical_argv", [
    (['gateway', 'list'], ['edgeflow', 'list']),
    (['gateways', 'get', 'g1'], ['edgeflow', 'get', 'g1']),
    (['apps', 'list'], ['application', 'list']),
    (['cameras', 'list'], ['camera', 'list']),
    (['deployments', 'list'], ['deployment', 'list']),
    (['deployment-group', 'list'], ['deployment', 'list']),
    (['workflows', 'get', 'w1'], ['workflow', 'get', 'w1']),
    (['tenant-gateway-cert', 'get'], ['tenant-edgeflow-certificate', 'get']),
])
def test_aliases_route_to_same_handler(alias_argv, canonical_argv):
    parser = build_parser()
    assert parser.parse_args(alias_argv).func is parser.parse_args(canonical_argv).func
