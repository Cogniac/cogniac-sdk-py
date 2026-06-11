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
import re
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


def test_get_routes_body_bearing_get_through_request():
    # Regression: httpx's Client.get() rejects a request body, but the model
    # package fetch (download_model -> GET /ccppkg) sends a json body. _get must
    # route body-bearing GETs through .request("GET", ...) while keeping plain
    # GETs on .get().
    from cogniac.cogniac import CogniacConnection

    class _Resp:
        status_code = 200

    class _Session:
        def __init__(self):
            self.last = None

        def get(self, url, **kw):
            self.last = ('get', kw)
            return _Resp()

        def request(self, method, url, **kw):
            self.last = ('request', method, kw)
            return _Resp()

    conn = object.__new__(CogniacConnection)
    conn.session = _Session()
    conn.url_prefix = 'https://example.invalid'
    conn.timeout = 60

    conn._get('/1/thing')
    assert conn.session.last[0] == 'get'

    conn._get('/1/thing', json={'ccp_filename': 'm.tgz'})
    assert conn.session.last[0] == 'request' and conn.session.last[1] == 'GET'
    assert conn.session.last[2].get('json') == {'ccp_filename': 'm.tgz'}


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
# Resource ids are required --<resource>-id flags (the canonical CLI surface).
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
    (['edgeflow-metrics', 'list'], ['edgeflow', 'metrics', 'list']),
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
    """Minimal fake connection: each _get returns the next queued payload."""
    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.urls = []

    def _get(self, url, **kwargs):
        self.urls.append(url)
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
