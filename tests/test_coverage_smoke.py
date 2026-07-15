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

import argparse
import inspect
import json
import re
import pytest

import cogniac
import cogniac.cli as cli
from cogniac.cli import (build_parser, resource_aliases, _SYNONYM_GROUPS, _resolve_positional_ids,
                         error_exit, output, _command_catalog, _timestamp, _body_arg)
from cogniac.common import server_error, raise_errors, ClientError, ServerError


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
    'labeling_image_encoder', 'labeling_mask_decoder', 'download_model',
]

_APP_CLASSMETHODS = ['create', 'get', 'get_all', 'get_all_types', 'get_type']

_SUBJECT_METHODS = ['update', 'delete', 'detections', 'consensus_history',
                    'bulk_disassociate', 'associate_media', 'disassociate_media',
                    'media_associations']
_MEDIA_METHODS = ['update', 'delete', 'share', 'create_detection', 'detections',
                  'embeddings', 'download']
_EDGEFLOW_METHODS = ['update', 'delete', 'get_certificate', 'set_certificate',
                     'replace_certificate', 'delete_certificate', 'metrics', 'status',
                     # device-control events
                     'reboot', 'ping', 'upgrade', 'set_boot_software_version',
                     'factory_reset', 'flush_upload_queue', 'time_bound_media_upload',
                     'trigger_camera_capture']
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

# instance methods (api-key management) — present on sync + async
_USER_INSTANCE_METHODS = ['api_keys', 'api_key', 'create_api_key', 'delete_api_key']


@pytest.mark.parametrize("method", _USER_METHODS)
def test_user_classmethods_exist(method):
    assert callable(getattr(cogniac.CogniacUser, method, None))
    assert callable(getattr(cogniac.AsyncCogniacUser, method, None))


@pytest.mark.parametrize("method", _USER_INSTANCE_METHODS)
def test_user_instance_methods_exist(method):
    assert callable(getattr(cogniac.CogniacUser, method, None))
    assert callable(getattr(cogniac.AsyncCogniacUser, method, None))


_DEPLOYMENT_METHODS = ['get_all', 'get', 'create', 'delete', 'edgeflows',
                       'history', 'prepull_status', 'prepull_start',
                       'set_target_workflow', 'deploy', 'deploy_status']


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


def test_get_routes_through_request_to_support_a_body():
    # Regression: httpx's Client.get() rejects a request body, so _get routes
    # every GET through .request("GET", ...) (matching _delete). This keeps
    # body-bearing GETs like the model-package fetch (download_model -> GET
    # /ccppkg) working. The fake exposes only request(), so any regression back
    # to .get() raises AttributeError loudly.
    from cogniac.cogniac import CogniacConnection

    class _Resp:
        status_code = 200

    class _Session:
        def __init__(self):
            self.last = None

        def request(self, method, url, **kw):
            self.last = ('request', method, kw)
            return _Resp()

    conn = object.__new__(CogniacConnection)
    conn.session = _Session()
    conn.url_prefix = 'https://example.invalid'
    conn.timeout = 60

    conn._get('/1/thing')
    assert conn.session.last[:2] == ('request', 'GET')

    conn._get('/1/thing', json={'ccp_filename': 'm.tgz'})
    assert conn.session.last[:2] == ('request', 'GET')
    assert conn.session.last[2].get('json') == {'ccp_filename': 'm.tgz'}


def test_get_retries_on_429_and_succeeds():
    """_get must retry on 429 and return the successful response.

    Verifies the retry actually fires: the session sees the 429 first, then
    returns 200 on the second call. Without the server_or_credential_error
    predicate on _get's @retry decorator this test fails because tenacity
    does not retry on ClientError(429).
    """
    from cogniac.cogniac import CogniacConnection

    class _Resp:
        def __init__(self, code):
            self.status_code = code
            self.text = ''
            self.headers = {}

    calls = []

    class _Session:
        def request(self, method, url, **kw):
            resp = _Resp(429 if len(calls) == 0 else 200)
            calls.append(resp.status_code)
            return resp

    conn = object.__new__(CogniacConnection)
    conn.session = _Session()
    conn.url_prefix = 'https://example.invalid'
    conn.timeout = 60

    resp = conn._get('/1/thing')
    assert resp.status_code == 200
    assert calls == [429, 200], "expected one 429 retry then 200, got %r" % calls


def test_get_retries_on_5xx_and_succeeds():
    """_get retries on server errors (5xx) in addition to 429."""
    from cogniac.cogniac import CogniacConnection

    class _Resp:
        def __init__(self, code):
            self.status_code = code
            self.text = ''
            self.headers = {}

    calls = []

    class _Session:
        def request(self, method, url, **kw):
            code = 500 if len(calls) == 0 else 200
            calls.append(code)
            return _Resp(code)

    conn = object.__new__(CogniacConnection)
    conn.session = _Session()
    conn.url_prefix = 'https://example.invalid'
    conn.timeout = 60

    resp = conn._get('/1/thing')
    assert resp.status_code == 200
    assert calls == [500, 200]


def test_post_retries_on_429_but_not_500():
    """_post retries 429 (safe, idempotent enough) but NOT 5xx (avoids double-submit)."""
    from cogniac.cogniac import CogniacConnection
    from cogniac.common import ServerError
    import pytest as _pytest

    class _Resp:
        def __init__(self, code):
            self.status_code = code
            self.text = 'err'
            self.headers = {}

    # 500 on first call → should propagate immediately, not retry
    calls = []

    class _Session500:
        def post(self, url, **kw):
            calls.append(500)
            return _Resp(500)

    conn = object.__new__(CogniacConnection)
    conn.session = _Session500()
    conn.url_prefix = 'https://example.invalid'
    conn.timeout = 60

    with _pytest.raises(ServerError):
        conn._post('/1/thing')
    assert calls == [500], "500 must NOT be retried on _post, got %r" % calls

    # 429 on first call → should retry
    calls.clear()

    class _Session429:
        def post(self, url, **kw):
            code = 429 if len(calls) == 0 else 200
            calls.append(code)
            return _Resp(code)

    conn2 = object.__new__(CogniacConnection)
    conn2.session = _Session429()
    conn2.url_prefix = 'https://example.invalid'
    conn2.timeout = 60

    resp = conn2._post('/1/thing')
    assert resp.status_code == 200
    assert calls == [429, 200]


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
    (cogniac.CogniacUser, cogniac.AsyncCogniacUser, _USER_METHODS + _USER_INSTANCE_METHODS),
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
# Every command parses to a callable handler, and every handler only reads
# argparse dests its command defines. These walk the built parser (including
# hidden deprecated spellings), so new commands are covered automatically — the
# kind of mechanical check that catches the dest/flag mismatches that bit us.
# ---------------------------------------------------------------------------

def _leaf_commands(parser, path=(), seen=None):
    """Yield (path, leaf_parser) for every command that binds a handler. Aliases
    (the same parser object reached under multiple names) are visited once under
    their canonical (first-registered) name."""
    if seen is None:
        seen = set()
    if parser.get_default('func') is not None:
        yield path, parser
    for spa in [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]:
        canon = {}
        for name, sub in spa.choices.items():
            canon.setdefault(id(sub), name)
        done = set()
        for name, sub in spa.choices.items():
            if id(sub) in done:
                continue
            done.add(id(sub))
            yield from _leaf_commands(sub, path + (canon[id(sub)],), seen)


def _dummy_value(action):
    if action.choices:
        return str(list(action.choices)[0])
    if action.type in (int, float):
        return '1'
    return 'x'


def _minimal_argv(path, leaf):
    """The command path plus a dummy value for each required argument."""
    argv = list(path)
    for a in leaf._actions:
        if isinstance(a, (argparse._HelpAction, argparse._SubParsersAction)):
            continue
        if not a.option_strings:                       # positional
            if a.nargs not in ('?', '*'):
                argv.append(_dummy_value(a))
        elif getattr(a, 'required', False):            # required flag
            argv.append(a.option_strings[0])
            if a.nargs != 0:
                argv.append(_dummy_value(a))
    return argv


def _all_leaves():
    return list(_leaf_commands(build_parser()))


def test_every_command_parses_to_a_handler():
    parser = build_parser()
    leaves = _all_leaves()
    assert len(leaves) > 100, "expected the full command tree, got %d" % len(leaves)
    for path, leaf in leaves:
        argv = _minimal_argv(path, leaf)
        ns = parser.parse_args(argv)
        assert hasattr(ns, 'func') and callable(ns.func), "no handler for %r" % (argv,)


# globals/inherited dests a handler may read besides its command's own args
_SHARED_DESTS = {'format', 'tenant', 'command', 'func'}


def test_handlers_only_read_defined_dests():
    """Every direct ``args.<x>`` a handler reads must be a dest its command
    defines (or a shared/global). Catches handler/parser attribute mismatches
    (e.g. a handler reading args.build_id when the parser registers it as
    application_build_id)."""
    bad = []
    for path, leaf in _all_leaves():
        func = leaf.get_default('func')
        try:
            src = inspect.getsource(func)
        except (OSError, TypeError):
            continue
        dests = {a.dest for a in leaf._actions if a.dest and a.dest != 'help'}
        # reads only: \b forces a full-identifier capture; the lookahead drops
        # assignment targets `args.x =` while keeping `==` comparisons
        for attr in set(re.findall(r"args\.([A-Za-z_]\w*)\b(?!\s*=(?!=))", src)):
            if attr in dests or attr in _SHARED_DESTS or attr.endswith('_command'):
                continue
            bad.append("%s reads args.%s (not a dest of `%s`)" % (func.__name__, attr, ' '.join(path)))
    assert not bad, "handler/parser attribute mismatches:\n" + "\n".join(sorted(set(bad)))


# ---------------------------------------------------------------------------
# Aliases (flat, synonym, plural) route to the SAME handler as canonical.
# Resource ids are --<resource>-id flags (canonical) with a deprecated positional
# mirror; see the dual-form tests near the end of this file.
# ---------------------------------------------------------------------------

ALIAS_PAIRS = [
    # plural / synonym top-level nouns
    (['apps', 'list'], ['application', 'list']),
    (['app', 'get', '--application-id', 'A1'], ['application', 'get', '--application-id', 'A1']),
    (['applications', 'get', '--application-id', 'A1'], ['application', 'get', '--application-id', 'A1']),
    (['subjects', 'list'], ['subject', 'list']),
    (['gateway', 'list'], ['edgeflow', 'list']),
    (['gateways', 'get', '--edgeflow-id', 'g1'], ['edgeflow', 'get', '--edgeflow-id', 'g1']),
    (['cameras', 'list'], ['camera', 'list']),
    (['network-camera', 'list'], ['camera', 'list']),
    (['deployments', 'list'], ['deployment', 'list']),
    (['deployment-group', 'list'], ['deployment', 'list']),
    (['workflows', 'get', '--workflow-id', 'w1'], ['workflow', 'get', '--workflow-id', 'w1']),
    (['users', 'list'], ['user', 'list']),
    # sub-noun synonyms / plurals / abbreviations
    (['apps', 'types', 'list'], ['application', 'type', 'list']),
    (['application', 'types', 'list'], ['application', 'type', 'list']),
    (['app', 'eval', 'metrics', 'get', '--application-id', 'A1'],
     ['application', 'evaluation', 'metrics', 'get', '--application-id', 'A1']),
    (['edgeflow', 'cert', 'get', '--edgeflow-id', 'g1'], ['edgeflow', 'certificate', 'get', '--edgeflow-id', 'g1']),
    (['gateway', 'cert', 'get', '--edgeflow-id', 'g1'], ['edgeflow', 'certificate', 'get', '--edgeflow-id', 'g1']),
    (['media', 'assertion', 'list', '--media-id', 'M1'], ['media', 'detection', 'list', '--media-id', 'M1']),
    (['media', 'assertions', 'create', '--media-id', 'M1'], ['media', 'detection', 'create', '--media-id', 'M1']),
    (['deployment', 'capacities', 'list'], ['deployment', 'capacity', 'list']),
    # flat / hyphenated deprecated -> nested
    (['application-feedback', 'list', '--application-id', 'A1'],
     ['application', 'feedback', 'list', '--application-id', 'A1']),
    (['application-type', 'list'], ['application', 'type', 'list']),
    (['application-build', 'list'], ['application', 'build', 'list']),
    (['edgeflow-certificate', 'get', '--edgeflow-id', 'g1'], ['edgeflow', 'certificate', 'get', '--edgeflow-id', 'g1']),
    (['edgeflow-metrics', 'list', '--metric-name', 'cpu'],
     ['edgeflow', 'metrics', 'list', '--metric-name', 'cpu']),
    (['edgeflow-metric-names'], ['edgeflow', 'metrics', 'names']),
    (['tenant-edgeflow-certificate', 'get'], ['tenant', 'edgeflow-certificate', 'get']),
    (['tenant-gateway-cert', 'get'], ['tenant', 'edgeflow-certificate', 'get']),
    (['tenant', 'gateway-certificate', 'get'], ['tenant', 'edgeflow-certificate', 'get']),
    (['tenant', 'edgeflow', 'certificate', 'get'], ['tenant', 'edgeflow-certificate', 'get']),  # deprecated two-token
    (['tenant-meraki-key', 'delete'], ['tenant', 'meraki-api-key', 'delete']),
    (['deployment-capacity', 'list'], ['deployment', 'capacity', 'list']),
    # old flat application verbs -> nested
    (['application', 'consensus-history', '--application-id', 'A1'],
     ['application', 'consensus', 'history', '--application-id', 'A1']),
    (['application', 'detections-pending', '--application-id', 'A1'],
     ['application', 'detections', 'pending', '--application-id', 'A1']),
    (['application', 'event-types', '--application-id', 'A1'],
     ['application', 'event', 'types', '--application-id', 'A1']),
    # edgeflow<->gateway in compound positions; event plural; api-key plural
    (['gateway', 'event', 'reboot', '--edgeflow-id', 'g1'], ['edgeflow', 'event', 'reboot', '--edgeflow-id', 'g1']),
    (['edgeflow', 'events', 'reboot', '--edgeflow-id', 'g1'], ['edgeflow', 'event', 'reboot', '--edgeflow-id', 'g1']),
    (['gateways', 'event', 'factory-reset', '--edgeflow-id', 'g1'],
     ['edgeflow', 'event', 'factory-reset', '--edgeflow-id', 'g1']),
    (['user', 'api-keys', 'list', '--user-id', 'u1'], ['user', 'api-key', 'list', '--user-id', 'u1']),
]


@pytest.mark.parametrize("alias_argv,canonical_argv", ALIAS_PAIRS)
def test_aliases_route_to_same_handler(alias_argv, canonical_argv):
    parser = build_parser()
    assert parser.parse_args(alias_argv).func is parser.parse_args(canonical_argv).func, \
        "%r should route to the same handler as %r" % (alias_argv, canonical_argv)


# ---------------------------------------------------------------------------
# Mocked-transport pagination (no creds): exercises the generator bodies that
# pure existence/parser checks can't — empty responses, bare lists, paging
# envelopes, and client-side limit. Guards the bugs the review surfaced.
# ---------------------------------------------------------------------------

class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Conn:
    """Minimal fake connection: each _get/_post returns the next queued payload."""
    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.urls = []
        self.posted = []

    def _get(self, url, **kwargs):
        self.urls.append(url)
        return _Resp(self._payloads.pop(0))

    def _post(self, url, **kwargs):
        self.posted.append((url, kwargs.get('json')))
        return _Resp(self._payloads.pop(0))


def _app_with(payloads):
    # bypass CogniacApplication.__setattr__ (it guards immutable keys / auto-POSTs)
    app = object.__new__(cogniac.CogniacApplication)
    object.__setattr__(app, '_cc', _Conn(payloads))
    object.__setattr__(app, 'application_id', 'A1')
    return app


def test_paged_release_items_empty_does_not_crash():
    # an empty consensus release serializes to JSON null -> must not raise
    app = _app_with([None])
    assert list(app.consensus_release_items('R1')) == []


def test_paged_release_items_bare_list():
    app = _app_with([['a', 'b', 'c']])
    assert list(app.consensus_release_items('R1')) == ['a', 'b', 'c']


def test_feedback_empty_does_not_crash():
    app = _app_with([None])
    assert list(app.feedback()) == []


def test_feedback_limit_not_truncated_at_100():
    # bare list of 150, limit 120 -> client-side cap returns 120 (not min(100))
    app = _app_with([list(range(150))])
    got = list(app.feedback(limit=120))
    assert len(got) == 120
    assert got[-1] == 119


def test_feedback_follows_paging_envelope():
    app = _app_with([
        {'data': [1, 2], 'paging': {'next': '/21/applications/A1/feedbackRequests?page=2'}},
        {'data': [3], 'paging': {}},
    ])
    assert list(app.feedback()) == [1, 2, 3]


# ---------------------------------------------------------------------------
# CogniacNetworkCamera.update back-compat shim: deprecated per-field kwargs are
# still accepted (merged into the body) but warn; the body form is unchanged.
# ---------------------------------------------------------------------------

def _camera_with(payloads):
    cam = object.__new__(cogniac.CogniacNetworkCamera)
    object.__setattr__(cam, '_cc', _Conn(payloads))
    object.__setattr__(cam, 'network_camera_id', 'c1')
    return cam


def test_network_camera_update_body_form():
    cam = _camera_with([{'network_camera_id': 'c1', 'url': 'u'}])
    cam.update({'url': 'u'})
    assert cam._cc.posted[0][1] == {'url': 'u'}


def test_network_camera_update_kwargs_compat_warns_and_merges():
    import warnings
    cam = _camera_with([{'network_camera_id': 'c1', 'url': 'u', 'current_IP': '10.0.0.1'}])
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cam.update(url='u', current_IP='10.0.0.1')
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)
    # deprecated kwargs are merged into the request body
    assert cam._cc.posted[0][1] == {'url': 'u', 'current_IP': '10.0.0.1'}


def test_async_network_camera_update_accepts_kwargs():
    import inspect
    sig = inspect.signature(cogniac.AsyncCogniacNetworkCamera.update)
    assert any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()), \
        "async update should accept **kwargs for back-compat"


# ---------------------------------------------------------------------------
# Dual-form resource ids: the canonical --<resource>-id flag and a deprecated
# positional mirror both resolve to the same dest; a required id given in
# neither form exits 2. Verbs that take another positional (classify, workflow
# version get) stay flag-only. Keeps the published skill's positional spellings
# working without re-introducing the positional/flag ambiguity.
# ---------------------------------------------------------------------------

def _parse(argv):
    p = build_parser()
    ns = p.parse_args(argv)
    _resolve_positional_ids(p, ns)
    return ns


@pytest.mark.parametrize("argv", [
    ['application', 'get', 'A1'],                       # deprecated positional
    ['application', 'get', '--application-id', 'A1'],   # canonical flag
])
def test_id_positional_and_flag_resolve_to_same_dest(argv):
    assert _parse(argv).application_id == 'A1'


@pytest.mark.parametrize("argv", [
    ['subject', 'media', 'S1'],
    ['edgeflow', 'status', 'E1'],
    ['media', 'download', 'M1'],
    ['camera', 'get', 'C1'],
    ['deployment', 'get', 'D1'],
    ['workflow', 'get', 'W1'],
])
def test_deprecated_positional_id_still_parses(argv):
    # the positional spelling the published skill documents must keep working
    assert argv[-1] in vars(_parse(argv)).values()


@pytest.mark.parametrize("argv", [
    ['application', 'get'],
    ['subject', 'get'],
    ['media', 'get'],
    ['edgeflow', 'get'],
])
def test_required_id_missing_in_both_forms_exits_2(argv):
    with pytest.raises(SystemExit) as exc:
        _parse(argv)
    assert exc.value.code == 2


@pytest.mark.parametrize("argv", [
    ['subject', 'associate', 'S1', 'M1'],
    ['subject', 'associate', '--subject-uid', 'S1', '--media-id', 'M1'],
])
def test_two_id_verb_resolves_both_ids(argv):
    ns = _parse(argv)
    assert ns.subject_uid == 'S1' and ns.media_id == 'M1'


def test_classify_id_is_flag_only_with_trailing_positional():
    # classify takes <image-file>, so its id stays a required flag (no mirror)
    assert _parse(['application', 'classify', '--application-id', 'A1', 'img.jpg']).application_id == 'A1'
    with pytest.raises(SystemExit):     # lone positional is the image file -> --application-id still required
        _parse(['application', 'classify', 'img.jpg'])


# ---------------------------------------------------------------------------
# List-cap defaults restored on the expensive reads (guards unbounded walks).
# ---------------------------------------------------------------------------

def test_subject_media_default_limit_is_100():
    assert _parse(['subject', 'media', 'S1']).limit == 100


def test_edgeflow_status_default_limit_is_10():
    assert _parse(['edgeflow', 'status', 'E1']).limit == 10


def test_edgeflow_status_accepts_start_end_time_range():
    # --start/--end use the _timestamp type: epoch or ISO 8601 -> float epoch seconds
    ns = _parse(['edgeflow', 'status', 'E1',
                 '--start', '1700000000', '--end', '2026-01-02T03:04:05Z'])
    assert ns.start == 1700000000.0
    assert isinstance(ns.end, float)
    # start/end default to None (omitted) when not passed
    bare = _parse(['edgeflow', 'status', 'E1'])
    assert bare.start is None and bare.end is None


def test_edgeflow_status_handler_forwards_start_end(monkeypatch):
    # the handler must pass start/end straight through to CogniacEdgeFlow.status()
    captured = {}

    class _FakeEdgeflow:
        def status(self, **kwargs):
            captured.update(kwargs)
            return iter([])

    class _FakeConn:
        def get_edgeflow(self, _id):
            return _FakeEdgeflow()

    monkeypatch.setattr(cli, 'get_connection', lambda args: _FakeConn())
    ns = _parse(['edgeflow', 'status', 'E1',
                 '--start', '1700000000', '--end', '1700003600',
                 '--subsystem', 'inference'])
    ns.func(ns)
    assert captured['start'] == 1700000000.0
    assert captured['end'] == 1700003600.0
    assert captured['subsystem_name'] == 'inference'
    assert captured['limit'] == 10


# ---------------------------------------------------------------------------
# Usage/error ergonomics: no alias wall in usage; a typo'd command suggests a
# close match instead of dumping every alias spelling.
# ---------------------------------------------------------------------------

def test_usage_string_has_no_alias_wall():
    usage = build_parser().format_usage()
    assert '<command>' in usage
    assert 'applications' not in usage and 'gateways' not in usage
    assert len(usage) < 300


def test_invalid_command_suggests_close_match(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(['aplication', 'list'])
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert 'did you mean' in err and 'application' in err
    assert 'gateways' not in err          # concise: not the full alias list


# ---------------------------------------------------------------------------
# SDK retry + field normalization (issues #158 / #157).
# ---------------------------------------------------------------------------

def test_server_error_retries_429_not_other_4xx():
    assert server_error(ClientError('rate limited', 429)) is True
    assert server_error(ServerError('boom')) is True
    assert server_error(ClientError('bad request', 400)) is False


def test_raise_errors_429_raises_retryable_with_retry_after():
    class _Resp:
        status_code = 429
        text = '{"message": "slow down"}'
        headers = {'Retry-After': '7'}

    with pytest.raises(ClientError) as exc:
        raise_errors(_Resp())
    assert exc.value.status_code == 429
    assert getattr(exc.value, 'retry_after', None) == 7.0
    assert server_error(exc.value) is True            # 429 is retryable


def test_raise_errors_429_without_retry_after_header():
    class _Resp:
        status_code = 429
        text = 'rate limited'
        headers = {}

    with pytest.raises(ClientError) as exc:
        raise_errors(_Resp())
    assert exc.value.status_code == 429
    assert getattr(exc.value, 'retry_after', None) is None


# app_data/custom_data JSON-string normalization (#157) is implemented by
# common.parse_json_str; the sync paths are covered in tests/test_json_normalization.py.
# This adds the async parity that that file lacks (async_media.subjects()).

def test_async_media_subjects_normalizes_json_strings():
    import asyncio

    class _AResp:
        def json(self):
            return {'data': [{'subject': {'app_data': '{"k": 1}'},
                              'media': {'custom_data': '[1, 2]'}}]}

    class _AConn:
        async def _get(self, url, **kw):
            return _AResp()

    m = object.__new__(cogniac.AsyncCogniacMedia)
    object.__setattr__(m, '_cc', _AConn())
    object.__setattr__(m, 'media_id', 'm1')
    data = asyncio.run(m.subjects())
    assert data[0]['subject']['app_data'] == {'k': 1}
    assert data[0]['media']['custom_data'] == [1, 2]


# ---------------------------------------------------------------------------
# Structured error envelope (wskish #6): typed, un-nested server JSON, hints.
# ---------------------------------------------------------------------------

def test_error_envelope_unnests_server_json(capsys):
    with pytest.raises(SystemExit) as exc:
        error_exit("ClientError", 'ClientError (400): {"message": "bad subject"}')
    assert exc.value.code == 1
    env = json.loads(capsys.readouterr().err)["error"]
    assert env == {"type": "client", "status": 400, "message": "bad subject"}


def test_error_envelope_auth_carries_hint(capsys):
    with pytest.raises(SystemExit):
        error_exit("CredentialError", 'Invalid username password credentials (401): nope')
    env = json.loads(capsys.readouterr().err)["error"]
    assert env["type"] == "auth" and env["status"] == 401 and "login" in env["hint"]


def test_error_envelope_rate_limit(capsys):
    with pytest.raises(SystemExit):
        error_exit("ClientError", 'RateLimited (429): slow down')
    env = json.loads(capsys.readouterr().err)["error"]
    assert env["type"] == "rate_limit" and env["status"] == 429


# ---------------------------------------------------------------------------
# Output: JSON Lines (wskish #8) and the truncation signal (wskish #7).
# ---------------------------------------------------------------------------

def test_output_jsonl_one_object_per_line(capsys):
    output([{'a': 1}, {'a': 2}], argparse.Namespace(format='jsonl', limit=None))
    assert capsys.readouterr().out.strip().split("\n") == ['{"a": 1}', '{"a": 2}']


def test_output_truncation_notice_to_stderr_only(capsys):
    output([1, 2], argparse.Namespace(format='json', limit=2))
    cap = capsys.readouterr()
    assert json.loads(cap.err)["truncated"] is True
    assert json.loads(cap.out) == [1, 2]            # stdout stays a clean array


def test_output_no_truncation_when_under_limit(capsys):
    output([1, 2], argparse.Namespace(format='json', limit=10))
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# commands catalog (wskish #3); --body @file/stdin (wskish #2); typed
# timestamps (wskish #5); trailing global flags (#4); --full-media (#160).
# ---------------------------------------------------------------------------

def test_commands_catalog_is_complete_and_honest():
    cat = {c['command']: c for c in _command_catalog(build_parser())}
    assert len(cat) > 100
    get = cat['application get']
    aid = next(a for a in get['args'] if a['name'] == '--application-id')
    assert aid['required'] is True                  # required via _reqid even though the flag isn't argparse-required
    assert all(a['name'] not in ('--format', '--tenant') for a in get['args'])   # globals omitted


def test_body_arg_reads_file_and_passes_inline_through(tmp_path):
    f = tmp_path / "b.json"
    f.write_text('{"x": 1}')
    assert _body_arg('@' + str(f)) == '{"x": 1}'
    assert _body_arg('{"y": 2}') == '{"y": 2}'


def test_body_arg_reads_stdin(monkeypatch):
    import io as _io
    monkeypatch.setattr('sys.stdin', _io.StringIO('{"z": 9}'))
    assert _body_arg('-') == '{"z": 9}'


def test_timestamp_accepts_epoch_and_iso():
    assert _timestamp('1700000000') == 1700000000.0
    assert isinstance(_timestamp('2026-01-02T03:04:05Z'), float)
    with pytest.raises(argparse.ArgumentTypeError):
        _timestamp('not-a-timestamp')


def test_trailing_global_flags_after_command():
    p = build_parser()
    assert p.parse_args(['application', 'list', '--format', 'table']).format == 'table'
    ns = p.parse_args(['subject', 'get', 'S1', '--tenant', 't9'])
    _resolve_positional_ids(p, ns)
    assert ns.tenant == 't9' and ns.subject_uid == 'S1'


def test_subject_media_full_media_flag():
    p = build_parser()
    ns = p.parse_args(['subject', 'media', 'S1', '--full-media']); _resolve_positional_ids(p, ns)
    assert ns.full_media is True
    ns = p.parse_args(['subject', 'media', 'S1']); _resolve_positional_ids(p, ns)
    assert ns.full_media is False and ns.limit == 100
