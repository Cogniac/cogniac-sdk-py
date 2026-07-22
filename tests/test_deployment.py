"""
Deployment deploy / deploy-status coverage (no creds, mocked transport).

Guards the deploy-verb surface added for the "set target does not deploy"
foot-gun (issue #180) and the long-dispatch read-timeout ambiguity (issue #185):

  - CogniacDeployment.deploy() POSTs next_workflow_id (or deploy_now_workflow_id
    with now=True) to /1/deploymentGroups/{id} with a generous, configurable
    read timeout — this DISPATCHES a rollout, unlike set_target_workflow which
    only records intent.
  - CogniacDeployment.deploy_status() re-GETs the group and reports convergence
    (current == target with no pending next) idempotently.
  - CLI `deployment deploy` / `deployment deploy-status` wire to those methods;
    a client read timeout on dispatch exits nonzero with a deploy-status hint
    (the server may still complete) instead of a bare traceback.
  - CLI `deployment target workflow set` warns on stderr that nothing was
    deployed; stdout stays pure JSON.

No live API calls are made and no real deployment is ever dispatched.
"""

import json

import httpx
import pytest

import cogniac
from cogniac.common import ServerError
from cogniac.deployment import DEPLOY_DEFAULT_TIMEOUT


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
        self.posted = []          # (url, json_body, timeout)

    def _get(self, url, **kwargs):
        self.urls.append(url)
        return _Resp(self._payloads.pop(0))

    def _post(self, url, **kwargs):
        self.posted.append((url, kwargs.get('json'), kwargs.get('timeout')))
        return _Resp(self._payloads.pop(0))


def _deployment_with(payloads):
    return cogniac.CogniacDeployment(_Conn(payloads), {'deployment_group_id': 'dg-test-1'})


# ---------------------------------------------------------------------------
# CogniacDeployment.deploy — request body, endpoint, and timeout
# ---------------------------------------------------------------------------

def test_deploy_posts_next_workflow_id():
    dg = _deployment_with([{'deployment_group_id': 'dg-test-1', 'next_workflow_id': 'wf-test-1'}])
    result = dg.deploy('wf-test-1')
    url, body, timeout = dg._cc.posted[0]
    assert url == "/1/deploymentGroups/dg-test-1"
    assert body == {'next_workflow_id': 'wf-test-1'}
    assert result['next_workflow_id'] == 'wf-test-1'


def test_deploy_now_posts_deploy_now_workflow_id():
    dg = _deployment_with([{'deployment_group_id': 'dg-test-1'}])
    dg.deploy('wf-test-1', now=True)
    url, body, timeout = dg._cc.posted[0]
    assert url == "/1/deploymentGroups/dg-test-1"
    assert body == {'deploy_now_workflow_id': 'wf-test-1'}


def test_deploy_default_timeout_is_generous():
    # the dispatch blocks server-side until every EdgeFlow accepts, so the
    # default must be far above the connection's 60s default
    dg = _deployment_with([{}])
    dg.deploy('wf-test-1')
    _, _, timeout = dg._cc.posted[0]
    assert timeout == DEPLOY_DEFAULT_TIMEOUT
    assert timeout >= 300


def test_deploy_timeout_is_configurable():
    dg = _deployment_with([{}])
    dg.deploy('wf-test-1', timeout=42)
    _, _, timeout = dg._cc.posted[0]
    assert timeout == 42


class _FailingPostConn(_Conn):
    """_post always fails with the given exception (after recording the attempt)."""
    def __init__(self, exc):
        super().__init__([])
        self._exc = exc

    def _post(self, url, **kwargs):
        self.posted.append((url, kwargs.get('json'), kwargs.get('timeout')))
        raise self._exc


def test_deploy_does_not_retry_on_server_error():
    # the dispatch is NOT idempotent: a 5xx after the server began processing
    # could double-dispatch the rollout, so deploy() must not carry the
    # blanket server_error retry — a single POST attempt, then propagate
    conn = _FailingPostConn(ServerError("ServerError (500): transient"))
    dg = cogniac.CogniacDeployment(conn, {'deployment_group_id': 'dg-test-1'})
    with pytest.raises(ServerError):
        dg.deploy('wf-test-1')
    assert len(conn.posted) == 1


def test_deploy_read_timeout_propagates_without_retry():
    # a client read timeout likewise propagates after one attempt (the caller
    # resolves the ambiguity via deploy_status())
    conn = _FailingPostConn(httpx.ReadTimeout("The read operation timed out"))
    dg = cogniac.CogniacDeployment(conn, {'deployment_group_id': 'dg-test-1'})
    with pytest.raises(httpx.ReadTimeout):
        dg.deploy('wf-test-1')
    assert len(conn.posted) == 1


# ---------------------------------------------------------------------------
# CogniacDeployment.deploy_status — convergence logic
# ---------------------------------------------------------------------------

def _status_with(group):
    group.setdefault('deployment_group_id', 'dg-test-1')
    return _deployment_with([group]).deploy_status()


def test_deploy_status_converged():
    status = _status_with({'target_workflow_id': 'wf-test-1',
                           'current_workflow_id': 'wf-test-1',
                           'next_workflow_id': None})
    assert status['converged'] is True
    assert status['deployment_group_id'] == 'dg-test-1'
    assert status['target_workflow_id'] == 'wf-test-1'
    assert status['current_workflow_id'] == 'wf-test-1'
    assert status['next_workflow_id'] is None


def test_deploy_status_pending_next_not_converged():
    # dispatch accepted but rollout still in flight
    status = _status_with({'target_workflow_id': 'wf-test-2',
                           'current_workflow_id': 'wf-test-2',
                           'next_workflow_id': 'wf-test-2'})
    assert status['converged'] is False


def test_deploy_status_target_set_but_not_deployed():
    # the issue #180 foot-gun state: target recorded, nothing dispatched
    status = _status_with({'target_workflow_id': 'wf-test-2',
                           'current_workflow_id': 'wf-test-1',
                           'next_workflow_id': None})
    assert status['converged'] is False


def test_deploy_status_no_current_workflow_not_converged():
    status = _status_with({'target_workflow_id': None,
                           'current_workflow_id': None,
                           'next_workflow_id': None})
    assert status['converged'] is False


def test_deploy_status_is_a_get():
    dg = _deployment_with([{'target_workflow_id': 'wf-test-1',
                            'current_workflow_id': 'wf-test-1',
                            'next_workflow_id': None}])
    dg.deploy_status()
    assert dg._cc.urls == ["/1/deploymentGroups/dg-test-1"]
    assert dg._cc.posted == []


class _FlakyGetConn(_Conn):
    """_get fails `failures` times with a 5xx, then serves the queued payloads."""
    def __init__(self, failures, payloads):
        super().__init__(payloads)
        self._failures = failures
        self.get_attempts = 0

    def _get(self, url, **kwargs):
        self.get_attempts += 1
        if self.get_attempts <= self._failures:
            raise ServerError("ServerError (500): transient")
        return super()._get(url, **kwargs)


def test_deploy_status_retries_on_server_error():
    # deploy_status is an idempotent GET, so it keeps the repo-standard
    # server_error retry (unlike the non-idempotent deploy())
    conn = _FlakyGetConn(1, [{'target_workflow_id': 'wf-test-1',
                              'current_workflow_id': 'wf-test-1',
                              'next_workflow_id': None}])
    dg = cogniac.CogniacDeployment(conn, {'deployment_group_id': 'dg-test-1'})
    status = dg.deploy_status()
    assert conn.get_attempts == 2
    assert status['converged'] is True


# ---------------------------------------------------------------------------
# CLI wiring — deployment deploy / deploy-status / target workflow set
# ---------------------------------------------------------------------------

class _FakeDeployment:
    """Stands in for the CogniacDeployment the handler fetches; never talks to
    any API."""
    def __init__(self, deploy_exc=None):
        self.calls = []
        self._deploy_exc = deploy_exc

    def deploy(self, workflow_id, now=False, timeout=None):
        self.calls.append(('deploy', workflow_id, now, timeout))
        if self._deploy_exc is not None:
            raise self._deploy_exc
        return {'deployment_group_id': 'dg-test-1', 'next_workflow_id': workflow_id}

    def deploy_status(self):
        self.calls.append(('deploy_status',))
        return {'deployment_group_id': 'dg-test-1', 'converged': True}

    def set_target_workflow(self, workflow_id):
        self.calls.append(('set_target_workflow', workflow_id))
        return {'deployment_group_id': 'dg-test-1', 'target_workflow_id': workflow_id}


def _invoke_cli(argv, monkeypatch, fake_dg):
    from cogniac import cli
    from cogniac import deployment as deployment_module
    monkeypatch.setattr(cli, 'get_connection', lambda args=None: object())
    monkeypatch.setattr(deployment_module.CogniacDeployment, 'get',
                        classmethod(lambda cls, cc, dg_id: fake_dg))
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    cli._resolve_positional_ids(parser, args)
    args.func(args)


def test_cli_deploy_wires_to_sdk(monkeypatch, capsys):
    dg = _FakeDeployment()
    _invoke_cli(['deployment', 'deploy',
                 '--deployment-group-id', 'dg-test-1',
                 '--workflow-id', 'wf-test-1'], monkeypatch, dg)
    assert dg.calls == [('deploy', 'wf-test-1', False, DEPLOY_DEFAULT_TIMEOUT)]
    out = json.loads(capsys.readouterr().out)
    assert out['next_workflow_id'] == 'wf-test-1'


def test_cli_deploy_now_and_timeout_flags(monkeypatch, capsys):
    dg = _FakeDeployment()
    _invoke_cli(['deployment', 'deploy',
                 '--deployment-group-id', 'dg-test-1',
                 '--workflow-id', 'wf-test-1',
                 '--now', '--timeout', '600'], monkeypatch, dg)
    assert dg.calls == [('deploy', 'wf-test-1', True, 600.0)]


def test_cli_deploy_read_timeout_exits_with_status_hint(monkeypatch, capsys):
    # issue #185: a client read timeout must not surface as a bare traceback —
    # the dispatch may still complete server-side
    dg = _FakeDeployment(deploy_exc=httpx.ReadTimeout("The read operation timed out"))
    with pytest.raises(SystemExit) as exc:
        _invoke_cli(['deployment', 'deploy',
                     '--deployment-group-id', 'dg-test-1',
                     '--workflow-id', 'wf-test-1'], monkeypatch, dg)
    assert exc.value.code != 0
    captured = capsys.readouterr()
    err = json.loads(captured.err)
    assert err['error']['type'] == 'timeout'
    assert 'still complete' in err['error']['message']
    assert 'deploy-status' in err['error']['hint']
    assert 'dg-test-1' in err['error']['hint']


def test_cli_deploy_status_wires_to_sdk(monkeypatch, capsys):
    dg = _FakeDeployment()
    _invoke_cli(['deployment', 'deploy-status',
                 '--deployment-group-id', 'dg-test-1'], monkeypatch, dg)
    assert dg.calls == [('deploy_status',)]
    out = json.loads(capsys.readouterr().out)
    assert out['converged'] is True


def test_cli_target_set_warns_not_deployed_on_stderr(monkeypatch, capsys):
    # issue #180: setting the target must warn that nothing was deployed;
    # the warning goes to stderr so stdout stays pure JSON
    dg = _FakeDeployment()
    _invoke_cli(['deployment', 'target', 'workflow', 'set',
                 '--deployment-group-id', 'dg-test-1',
                 '--workflow-id', 'wf-test-1'], monkeypatch, dg)
    assert dg.calls == [('set_target_workflow', 'wf-test-1')]
    captured = capsys.readouterr()
    out = json.loads(captured.out)                      # stdout is pure JSON
    assert out['target_workflow_id'] == 'wf-test-1'
    warning = json.loads(captured.err)
    assert 'NOT deployed' in warning['warning']
    assert 'cogniac deployment deploy' in warning['warning']
    assert 'dg-test-1' in warning['warning']
    assert 'wf-test-1' in warning['warning']
