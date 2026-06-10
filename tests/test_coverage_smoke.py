"""
Non-live smoke tests for the SDK + CLI coverage.

These tests do NOT require credentials. They verify:
  - every SDK method this surface touches exists on the sync class AND its
    async counterpart;
  - the new public entity classes are importable from the package root;
  - the CLI parser builds, and every catalog command parses to a callable
    handler (the full command list is enumerated below);
  - representative deprecated aliases — flat/hyphenated spellings, synonyms
    (gateway<->edgeflow, assertion<->detection), and plurals (apps, subjects) —
    resolve to the SAME handler as their canonical nested form;
  - the resource-alias helper expands sing/plur + abbreviation/synonym variants.
"""

import inspect
import pytest

import cogniac
from cogniac.cli import build_parser, resource_aliases, _SYNONYM_GROUPS


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

# methods that must exist on both the sync class and its async counterpart.
_APP_METHODS = [
    'update', 'classify', 'donate_model', 'export_model_to_meraki',
    'replay_status', 'replay_start', 'replay_stop', 'detections_pending',
    'event_types', 'events', 'consensus_history',
    'performance_current_validation', 'performance_release_validation',
    'performance_new_random', 'model_performance', 'models',
    'push_notifications', 'subscribe_push',
    'feedback', 'feedback_request', 'submit_feedback', 'feedback_request_count',
    'pending_feedback_requests', 'purge_feedback', 'delete_feedback_requests',
    'create_evaluation_metric', 'register_default_evaluation_metric',
    'copy_evaluation_metrics',
    'consensus_releases', 'consensus_release', 'consensus_release_items',
    'consensus_release_upstream_assertions', 'consensus_detection_release',
    'labeling_image_encoder', 'labeling_mask_decoder',
]

_APP_CLASSMETHODS = ['create', 'get', 'get_all', 'get_all_types', 'get_type']

_SUBJECT_METHODS = ['update', 'delete', 'detections', 'consensus_history',
                    'bulk_disassociate', 'associate_media', 'disassociate_media',
                    'media_associations']
_MEDIA_METHODS = ['update', 'delete', 'share', 'create_detection', 'detections',
                  'embeddings', 'download']
_EDGEFLOW_METHODS = ['update', 'delete', 'get_certificate', 'set_certificate',
                     'replace_certificate', 'delete_certificate', 'metrics', 'status']
_EDGEFLOW_CLASSMETHODS = ['create', 'get', 'get_all', 'metric_names', 'all_metrics']
_TENANT_METHODS = ['get_edgeflow_certificate', 'set_edgeflow_certificate',
                   'delete_edgeflow_certificate', 'delete_meraki_api_key',
                   'invites', 'create_invite', 'delete_invite', 'users']
_NETCAM_METHODS = ['update', 'delete', 'genicam', 'upload_genicam']


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


_USER_METHODS = ['get_all', 'get_by_id', 'delete_by_id', 'tenants',
                 'request_password_reset', 'invites', 'respond_invite']


@pytest.mark.parametrize("method", _USER_METHODS)
def test_user_classmethods_exist(method):
    assert callable(getattr(cogniac.CogniacUser, method, None))
    assert callable(getattr(cogniac.AsyncCogniacUser, method, None))


_DEPLOYMENT_METHODS = ['get_all', 'get', 'create', 'delete', 'edgeflows',
                       'history', 'prepull_status', 'prepull_start',
                       'set_target_workflow']


@pytest.mark.parametrize("method", _DEPLOYMENT_METHODS)
def test_deployment_methods_exist(method):
    assert hasattr(cogniac.CogniacDeployment, method)
    assert hasattr(cogniac.AsyncCogniacDeployment, method)


@pytest.mark.parametrize("method", ['get_all', 'get'])
def test_deployment_capacity_methods_exist(method):
    assert hasattr(cogniac.CogniacDeploymentCapacityClass, method)
    assert hasattr(cogniac.AsyncCogniacDeploymentCapacityClass, method)


_WORKFLOW_METHODS = ['get_all', 'get', 'create', 'delete', 'edgeflow_targets',
                     'new_version', 'get_version']


@pytest.mark.parametrize("method", _WORKFLOW_METHODS)
def test_workflow_methods_exist(method):
    assert hasattr(cogniac.CogniacWorkflow, method)
    assert hasattr(cogniac.AsyncCogniacWorkflow, method)


_BUILD_METHODS = ['get_all', 'get', 'create', 'delete', 'names', 'lint']


@pytest.mark.parametrize("method", _BUILD_METHODS)
def test_build_methods_exist(method):
    assert hasattr(cogniac.CogniacBuild, method)
    assert hasattr(cogniac.AsyncCogniacBuild, method)


def test_connection_convenience_methods():
    for name in ['edgeflows', 'gateways', 'get_all_deployments', 'get_deployment',
                 'get_all_workflows', 'get_workflow', 'get_all_applications',
                 'get_all_subjects', 'get_all_cameras', 'get_all_edgeflows']:
        assert callable(getattr(cogniac.CogniacConnection, name, None)), \
            "CogniacConnection.%s missing" % name


def test_gateways_is_deprecated_alias_of_edgeflows():
    # gateways() must remain as a (deprecated) alias that delegates to edgeflows()
    assert callable(cogniac.CogniacConnection.gateways)
    src = inspect.getsource(cogniac.CogniacConnection.gateways)
    assert 'edgeflows' in src


# ---------------------------------------------------------------------------
# Pagination generators — the reads that drain paging must be generators.
# ---------------------------------------------------------------------------

def _is_gen(fn):
    # unwrap any @retry / functools.wraps wrappers before inspecting
    inner = inspect.unwrap(fn)
    return (inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn)
            or inspect.isgeneratorfunction(inner) or inspect.isasyncgenfunction(inner))


@pytest.mark.parametrize("cls", [cogniac.CogniacApplication, cogniac.AsyncCogniacApplication])
@pytest.mark.parametrize("method", ['events', 'models', 'detections', 'feedback'])
def test_application_paged_reads_are_generators(cls, method):
    assert _is_gen(getattr(cls, method)), "%s.%s should be a generator" % (cls.__name__, method)


def test_consensus_release_subreads_yield_items():
    # sync wrappers return the underlying generator; async are async generators.
    assert _is_gen(cogniac.CogniacApplication._paged_release_items)
    assert _is_gen(cogniac.AsyncCogniacApplication._paged_release_items)
    assert _is_gen(cogniac.AsyncCogniacApplication.consensus_release_items)
    assert _is_gen(cogniac.AsyncCogniacApplication.consensus_release_upstream_assertions)
    # the sync public methods return a generator object when called
    src = inspect.getsource(cogniac.CogniacApplication.consensus_release_items)
    assert 'return self._paged_release_items' in src


@pytest.mark.parametrize("cls", [cogniac.CogniacDeployment, cogniac.AsyncCogniacDeployment])
def test_deployment_history_is_generator(cls):
    assert _is_gen(cls.history), "%s.history should drain last_key as a generator" % cls.__name__


@pytest.mark.parametrize("cls", [cogniac.CogniacSubject, cogniac.AsyncCogniacSubject])
def test_subject_media_associations_is_generator(cls):
    assert _is_gen(cls.media_associations)


# ---------------------------------------------------------------------------
# update(body) methods exist on every CRUD resource (sync + async)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sync_cls,async_cls", [
    (cogniac.CogniacApplication, cogniac.AsyncCogniacApplication),
    (cogniac.CogniacSubject, cogniac.AsyncCogniacSubject),
    (cogniac.CogniacMedia, cogniac.AsyncCogniacMedia),
    (cogniac.CogniacEdgeFlow, cogniac.AsyncCogniacEdgeFlow),
    (cogniac.CogniacNetworkCamera, cogniac.AsyncCogniacNetworkCamera),
])
def test_update_body_method_present(sync_cls, async_cls):
    for cls in (sync_cls, async_cls):
        assert callable(getattr(cls, 'update', None)), "%s.update missing" % cls.__name__
        # update takes a body positional
        sig = inspect.signature(cls.update)
        assert 'body' in sig.parameters, "%s.update should accept a body" % cls.__name__


# ---------------------------------------------------------------------------
# Async/sync symmetry — the async class must expose every method the sync class
# does for the resources covered here.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sync_cls,async_cls,methods", [
    (cogniac.CogniacApplication, cogniac.AsyncCogniacApplication, _APP_METHODS + _APP_CLASSMETHODS),
    (cogniac.CogniacSubject, cogniac.AsyncCogniacSubject, _SUBJECT_METHODS),
    (cogniac.CogniacMedia, cogniac.AsyncCogniacMedia, _MEDIA_METHODS),
    (cogniac.CogniacEdgeFlow, cogniac.AsyncCogniacEdgeFlow, _EDGEFLOW_METHODS + _EDGEFLOW_CLASSMETHODS),
    (cogniac.CogniacTenant, cogniac.AsyncCogniacTenant, _TENANT_METHODS),
    (cogniac.CogniacUser, cogniac.AsyncCogniacUser, _USER_METHODS),
    (cogniac.CogniacNetworkCamera, cogniac.AsyncCogniacNetworkCamera, _NETCAM_METHODS),
    (cogniac.CogniacDeployment, cogniac.AsyncCogniacDeployment, _DEPLOYMENT_METHODS),
    (cogniac.CogniacWorkflow, cogniac.AsyncCogniacWorkflow, _WORKFLOW_METHODS),
    (cogniac.CogniacBuild, cogniac.AsyncCogniacBuild, _BUILD_METHODS),
])
def test_methods_have_async_counterparts(sync_cls, async_cls, methods):
    for m in methods:
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
    for a in ['edgeflow-cert', 'gateway-certificate', 'gateway-cert', 'edgeflows-cert']:
        assert a in aliases, "%s should be an alias of edgeflow-certificate" % a


def test_alias_abbreviations():
    flat = {x for grp in _SYNONYM_GROUPS for x in grp}
    assert 'eval' in flat and 'perf' in flat
    aliases = resource_aliases('deployment-capacity')
    assert 'deployment-capacities' in aliases


def test_alias_detection_assertion_synonym():
    flat = {x for grp in _SYNONYM_GROUPS for x in grp}
    for a in ['detection', 'detections', 'assertion', 'assertions']:
        assert a in flat


def test_alias_media_uncountable():
    # 'media' is uncountable: it must NOT gain a 'medias' alias
    assert resource_aliases('media') == []
    assert resource_aliases('media-embeddings') == []


# ---------------------------------------------------------------------------
# CLI parser builds
# ---------------------------------------------------------------------------

def test_parser_builds():
    assert build_parser() is not None


def test_version_flag_present_but_no_version_subcommand():
    parser = build_parser()
    # the top-level --version flag prints the package version and exits
    with pytest.raises(SystemExit):
        parser.parse_args(['--version'])
    # the `version` subcommand was removed
    with pytest.raises(SystemExit):
        parser.parse_args(['version'])


def test_removed_label_mask_decoder_head():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(['application', 'label-mask-decoder-model', 'head', 'A1'])


# ---------------------------------------------------------------------------
# Every catalog command parses to a callable handler (the full nested catalog).
# ---------------------------------------------------------------------------

CATALOG_COMMANDS = [
    # auth
    ['auth'], ['auth', 'login'], ['auth', 'logout'],
    # tenant
    ['tenant', 'get'], ['tenant', 'list'],
    ['tenant', 'edgeflow', 'certificate', 'get'],
    ['tenant', 'edgeflow', 'certificate', 'set'],
    ['tenant', 'edgeflow', 'certificate', 'delete'],
    ['tenant', 'meraki-api-key', 'delete'],
    ['tenant', 'cloudcore-import-key', 'get', 'KEY'],
    ['tenant', 'user', 'list'],
    ['tenant', 'user', 'add', '--body', '{}'],
    ['tenant', 'user', 'delete', '--body', '{}'],
    ['tenant', 'user', 'role', 'set', '--body', '{}'],
    # application top-level
    ['application', 'list'], ['application', 'get', 'A1'], ['application', 'create', '--body', '{}'],
    ['application', 'update', 'A1', '--body', '{}'], ['application', 'delete', 'A1'],
    ['application', 'leaderboard', 'A1'], ['application', 'classify', 'A1', 'img.jpg'],
    ['application', 'events', 'A1'], ['application', 'event', 'types', 'A1'],
    ['application', 'detections', 'pending', 'A1'],
    ['application', 'replay', 'status', 'A1'], ['application', 'replay', 'start', 'A1'],
    ['application', 'replay', 'stop', 'A1'],
    ['application', 'performance', 'current', 'A1'], ['application', 'performance', 'release', 'A1'],
    ['application', 'performance', 'new-random', 'A1'],
    ['application', 'push', 'get', 'A1'], ['application', 'push', 'subscribe', 'A1'],
    # application feedback
    ['application', 'feedback', 'list', 'A1'], ['application', 'feedback', 'get', 'A1', 'F1'],
    ['application', 'feedback', 'create', 'A1', '--body', '{}'], ['application', 'feedback', 'count', 'A1'],
    ['application', 'feedback', 'pending', 'A1'], ['application', 'feedback', 'purge', 'A1'],
    ['application', 'feedback', 'purge-requests', 'A1'],
    # application model
    ['application', 'model', 'performance', 'A1', '--subject-uid', 's1'],
    ['application', 'model', 'donate', 'A1', '--source', 'A2'],
    ['application', 'model', 'export', 'A1', '--target', 'meraki'], ['application', 'model', 'list', 'A1'],
    # application consensus
    ['application', 'consensus', 'history', 'A1'],
    ['application', 'consensus', 'release', 'list', 'A1'],
    ['application', 'consensus', 'release', 'get', 'A1', 'R1'],
    ['application', 'consensus', 'release', 'items', 'A1', 'R1'],
    ['application', 'consensus', 'release', 'upstream', 'A1', 'R1'],
    ['application', 'consensus', 'release', 'detections', 'A1'],
    # application evaluation metrics
    ['application', 'evaluation', 'metrics', 'get', 'A1'],
    ['application', 'evaluation', 'metrics', 'create', 'A1', '--body', '{}'],
    ['application', 'evaluation', 'metrics', 'register-default', 'A1'],
    ['application', 'evaluation', 'metrics', 'copy', '--source', 'S1', '--target', 'T1'],
    # application labeling models
    ['application', 'label-image-encoder-model', 'download', 'A1'],
    ['application', 'label-mask-decoder-model', 'download', 'A1'],
    # application type
    ['application', 'type', 'list'], ['application', 'type', 'get', 'box_detection'],
    # application build
    ['application', 'build', 'list'], ['application', 'build', 'get', 'B1'],
    ['application', 'build', 'create', '--body', '{}'], ['application', 'build', 'delete', 'B1'],
    ['application', 'build', 'names', 'list'], ['application', 'build', 'lint', 'f.py'],
    # subject
    ['subject', 'list'], ['subject', 'get', 's1'], ['subject', 'create', 'myname'],
    ['subject', 'update', 's1', '--body', '{}'], ['subject', 'delete', 's1'],
    ['subject', 'search'], ['subject', 'media', 's1'],
    ['subject', 'associate', 's1', 'M1'], ['subject', 'disassociate', 's1', 'M1'],
    ['subject', 'consensus', 'history', 's1'], ['subject', 'detections', 's1', '--media-id', 'M1'],
    # media
    ['media', 'get', 'M1'], ['media', 'upload', 'f.jpg'], ['media', 'update', 'M1', '--body', '{}'],
    ['media', 'delete', 'M1'], ['media', 'download', 'M1'], ['media', 'search'], ['media', 'share', 'M1'],
    ['media', 'embeddings', 'get', 'M1'], ['media', 'detection', 'list', 'M1'],
    ['media', 'detection', 'create', 'M1'],
    # edgeflow
    ['edgeflow', 'list'], ['edgeflow', 'get', 'g1'], ['edgeflow', 'create'],
    ['edgeflow', 'update', 'g1', '--body', '{}'], ['edgeflow', 'delete', 'g1'], ['edgeflow', 'status', 'g1'],
    ['edgeflow', 'certificate', 'get', 'g1'], ['edgeflow', 'certificate', 'set', 'g1'],
    ['edgeflow', 'certificate', 'replace', 'g1'], ['edgeflow', 'certificate', 'delete', 'g1'],
    ['edgeflow', 'metrics', 'list'], ['edgeflow', 'metrics', 'names'],
    # camera
    ['camera', 'list'], ['camera', 'get', 'c1'], ['camera', 'create', '--body', '{}'],
    ['camera', 'update', 'c1', '--body', '{}'], ['camera', 'delete', 'c1'], ['camera', 'genicam', 'c1'],
    # deployment
    ['deployment', 'list'], ['deployment', 'get', 'd1'], ['deployment', 'create'],
    ['deployment', 'delete', 'd1'], ['deployment', 'edgeflows', 'd1'], ['deployment', 'history', 'd1'],
    ['deployment', 'prepull', 'status', 'd1'], ['deployment', 'prepull', 'start', 'd1', '--workflow', 'w1'],
    ['deployment', 'target', 'workflow', 'set', 'd1', '--workflow', 'w1'],
    ['deployment', 'capacity', 'list'], ['deployment', 'capacity', 'get', 'cc1'],
    # workflow
    ['workflow', 'list'], ['workflow', 'get', 'w1'], ['workflow', 'create'], ['workflow', 'delete', 'w1'],
    ['workflow', 'edgeflow', 'deployment-targets', 'list'],
    ['workflow', 'version', 'new', 'w1', '--body', '{}'], ['workflow', 'version', 'get', 'b1', '3'],
    # user
    ['user', 'list'], ['user', 'get', 'u1'], ['user', 'delete', 'u1'],
    ['user', 'tenants', 'u1'], ['user', 'password', 'reset', 'a@b.co'],
]


@pytest.mark.parametrize("argv", CATALOG_COMMANDS)
def test_catalog_command_resolves_to_handler(argv):
    parser = build_parser()
    ns = parser.parse_args(argv)
    assert hasattr(ns, 'func') and callable(ns.func), "no handler for %r" % (argv,)


# ---------------------------------------------------------------------------
# Hidden deprecated flat / hyphenated spellings still resolve to a handler.
# ---------------------------------------------------------------------------

DEPRECATED_FLAT_COMMANDS = [
    ['application-feedback', 'list', 'A1'],
    ['application-feedback', 'get', 'A1', 'F1'],
    ['application-model', 'performance', 'A1', '--subject-uid', 's1'],
    ['application-type', 'list'], ['application-type', 'get', 'box_detection'],
    ['application-types', 'list'],
    ['application-build', 'list'], ['application-build', 'names', 'list'],
    ['application-evaluation-metrics', 'get', 'A1'],
    ['application-label', 'image-encoder', 'A1'], ['application-label', 'mask-decoder', 'A1'],
    ['application', 'consensus-history', 'A1'],
    ['application', 'consensus-releases', 'A1'],
    ['application', 'consensus-release', 'A1', 'R1'],
    ['application', 'consensus-release-items', 'A1', 'R1'],
    ['application', 'consensus-release-upstream', 'A1', 'R1'],
    ['application', 'consensus-detection-releases', 'A1'],
    ['application', 'eval-metrics', 'A1'], ['application', 'evaluation-metrics', 'A1'],
    ['application', 'evaluation-metrics-create', 'A1'],
    ['application', 'evaluation-metrics-register-default', 'A1'],
    ['application', 'evaluation-metrics-copy', 'S1', 'T1'],
    ['application', 'donate-model', 'A1', 'A2'],
    ['application', 'replay-start', 'A1'], ['application', 'replay-stop', 'A1'],
    ['application', 'detections-pending', 'A1'], ['application', 'event-types', 'A1'],
    ['application', 'performance-current', 'A1'], ['application', 'performance-release', 'A1'],
    ['application', 'performance-new-random', 'A1'], ['application', 'push-subscribe', 'A1'],
    ['edgeflow-certificate', 'get', 'g1'], ['edgeflow-certificate', 'set', 'g1'],
    ['edgeflow-certificate', 'replace', 'g1'], ['edgeflow-certificate', 'delete', 'g1'],
    ['edgeflow-metrics', 'list'], ['edgeflow-metric-names'],
    ['tenant-edgeflow-certificate', 'get'], ['tenant-edgeflow-certificate', 'set'],
    ['tenant-edgeflow-certificate', 'delete'], ['tenant-meraki-key', 'delete'],
    ['tenant-import', 'KEY123'],
    ['deployment-capacity', 'list'], ['deployment-capacity', 'get', 'cc1'],
    ['workflow-version', 'new', 'w1', '--body', '{}'], ['workflow-version', 'get', 'b1', '3'],
    ['media-embeddings', 'M1'],
]


@pytest.mark.parametrize("argv", DEPRECATED_FLAT_COMMANDS)
def test_deprecated_flat_command_resolves_to_handler(argv):
    parser = build_parser()
    ns = parser.parse_args(argv)
    assert hasattr(ns, 'func') and callable(ns.func), "no handler for deprecated %r" % (argv,)


# ---------------------------------------------------------------------------
# Aliases (flat, synonym, plural) route to the SAME handler as canonical.
# ---------------------------------------------------------------------------

ALIAS_PAIRS = [
    # plural / synonym top-level nouns
    (['apps', 'list'], ['application', 'list']),
    (['app', 'get', 'A1'], ['application', 'get', 'A1']),
    (['applications', 'get', 'A1'], ['application', 'get', 'A1']),
    (['subjects', 'list'], ['subject', 'list']),
    (['gateway', 'list'], ['edgeflow', 'list']),
    (['gateways', 'get', 'g1'], ['edgeflow', 'get', 'g1']),
    (['cameras', 'list'], ['camera', 'list']),
    (['network-camera', 'list'], ['camera', 'list']),
    (['deployments', 'list'], ['deployment', 'list']),
    (['deployment-group', 'list'], ['deployment', 'list']),
    (['workflows', 'get', 'w1'], ['workflow', 'get', 'w1']),
    (['users', 'list'], ['user', 'list']),
    # sub-noun synonyms / plurals / abbreviations
    (['apps', 'types', 'list'], ['application', 'type', 'list']),
    (['application', 'types', 'list'], ['application', 'type', 'list']),
    (['app', 'eval', 'metrics', 'get', 'A1'], ['application', 'evaluation', 'metrics', 'get', 'A1']),
    (['edgeflow', 'cert', 'get', 'g1'], ['edgeflow', 'certificate', 'get', 'g1']),
    (['gateway', 'cert', 'get', 'g1'], ['edgeflow', 'certificate', 'get', 'g1']),
    (['media', 'assertion', 'list', 'M1'], ['media', 'detection', 'list', 'M1']),
    (['media', 'assertions', 'create', 'M1'], ['media', 'detection', 'create', 'M1']),
    (['deployment', 'capacities', 'list'], ['deployment', 'capacity', 'list']),
    (['workflow', 'versions', 'get', 'b1', '3'], ['workflow', 'version', 'get', 'b1', '3']),
    # flat / hyphenated deprecated -> nested
    (['application-feedback', 'list', 'A1'], ['application', 'feedback', 'list', 'A1']),
    (['app-feedback', 'get', 'A1', 'F1'], ['application', 'feedback', 'get', 'A1', 'F1']),
    (['application-model', 'performance', 'A1', '--subject-uid', 's1'],
     ['application', 'model', 'performance', 'A1', '--subject-uid', 's1']),
    (['application-type', 'list'], ['application', 'type', 'list']),
    (['application-build', 'list'], ['application', 'build', 'list']),
    (['application-evaluation-metrics', 'get', 'A1'], ['application', 'evaluation', 'metrics', 'get', 'A1']),
    (['edgeflow-certificate', 'get', 'g1'], ['edgeflow', 'certificate', 'get', 'g1']),
    (['edgeflow-metrics', 'list'], ['edgeflow', 'metrics', 'list']),
    (['edgeflow-metric-names'], ['edgeflow', 'metrics', 'names']),
    (['tenant-edgeflow-certificate', 'get'], ['tenant', 'edgeflow', 'certificate', 'get']),
    (['tenant-gateway-cert', 'get'], ['tenant', 'edgeflow', 'certificate', 'get']),
    (['tenant-meraki-key', 'delete'], ['tenant', 'meraki-api-key', 'delete']),
    (['deployment-capacity', 'list'], ['deployment', 'capacity', 'list']),
    (['workflow-version', 'get', 'b1', '3'], ['workflow', 'version', 'get', 'b1', '3']),
    (['media-embeddings', 'M1'], ['media', 'embeddings', 'get', 'M1']),
    # old flat application verbs -> nested
    (['application', 'consensus-history', 'A1'], ['application', 'consensus', 'history', 'A1']),
    (['application', 'consensus-release-items', 'A1', 'R1'],
     ['application', 'consensus', 'release', 'items', 'A1', 'R1']),
    (['application', 'eval-metrics', 'A1'], ['application', 'evaluation', 'metrics', 'get', 'A1']),
    (['application', 'detections-pending', 'A1'], ['application', 'detections', 'pending', 'A1']),
    (['application', 'event-types', 'A1'], ['application', 'event', 'types', 'A1']),
]


@pytest.mark.parametrize("alias_argv,canonical_argv", ALIAS_PAIRS)
def test_aliases_route_to_same_handler(alias_argv, canonical_argv):
    parser = build_parser()
    assert parser.parse_args(alias_argv).func is parser.parse_args(canonical_argv).func, \
        "%r should route to the same handler as %r" % (alias_argv, canonical_argv)
