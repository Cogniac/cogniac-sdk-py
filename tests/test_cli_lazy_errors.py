"""
Offline tests: CLI behaviour that moved when the tenant and user reads became lazy (#196).

The reads used to happen inside `get_connection`, so their failures were reported there. They
now happen inside the command handlers, so these pin what `main()` and `cmd_auth` report.
"""

import json
import sys

import httpx
import pytest
import time

from cogniac import cli
from cogniac import cogniac as cogmod

PREFIX = 'https://api.example.test'
_REAL_CLIENT = httpx.Client


def _run(monkeypatch, capsys, mode, *argv):
    def handler(request):
        path = request.url.path
        if path == '/1/token':
            return httpx.Response(200, json={'access_token': 'tok'})
        if path == '/1/users/current/tenants':
            return httpx.Response(200, json={'tenants': [{'tenant_id': 't1', 'name': 'x'}]})
        if mode == '500':
            return httpx.Response(500, json={'message': 'boom'})
        if mode == '403':
            return httpx.Response(403, json={'message': 'no role on tenant'})
        if mode == 'drop':
            raise httpx.ConnectError('connection dropped')
        return httpx.Response(200, json={'tenant_id': 't1', 'name': 'x', 'region': None,
                                         'user_id': 'u1'})
    def client(*a, **k):
        k['transport'] = httpx.MockTransport(handler)
        return _REAL_CLIENT(*a, **k)
    monkeypatch.setattr(cogmod.httpx, 'Client', client)
    monkeypatch.setattr(httpx, 'get', lambda url, **k: client().get(url, **k))
    monkeypatch.setattr(time, 'sleep', lambda s: None)  # tenacity's backoff
    for var, val in (('COG_API_KEY', 'k'), ('COG_TENANT', 't1'), ('COG_URL_PREFIX', PREFIX)):
        monkeypatch.setenv(var, val)
    monkeypatch.setattr(sys, 'argv', ['cogniac'] + list(argv))
    rc = 0
    try:
        cli.main()
    except SystemExit as e:
        rc = e.code
    out, err = capsys.readouterr()
    return rc, out, err


@pytest.mark.parametrize('mode,etype', [('500', 'server'), ('drop', 'connection'),
                                        ('403', 'client')])
def test_a_failed_lazy_read_reports_the_json_envelope_typed_by_its_cause(monkeypatch, capsys,
                                                                         mode, etype):
    rc, out, err = _run(monkeypatch, capsys, mode, 'tenant')
    assert rc == 1 and out == ''
    assert json.loads(err)['error']['type'] == etype


def test_auth_makes_an_authenticated_request_before_reporting_valid(monkeypatch, capsys):
    rc, out, _ = _run(monkeypatch, capsys, '403', 'auth')
    result = json.loads(out)
    assert result['valid'] is False
    assert 'no role on tenant' in result['detail']
    rc, out, _ = _run(monkeypatch, capsys, 'ok', 'auth')
    assert json.loads(out)['valid'] is True
