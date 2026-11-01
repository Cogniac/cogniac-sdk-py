"""
Subject search no longer offers `similar` (no creds).

The API answers 400 to `GET /1/tenants/{tenant_id}/subjects?similar=...`, so
the SDK refuses `similar` before sending anything and says what to use instead.
`similar` stays in every public signature, so existing calls do not fail with a
TypeError. The CLI `--similar` flag fails the same way, with a non-zero exit.
"""

import inspect
import json

import pytest

import cogniac
from cogniac import cli


class _Resp:
    def json(self):
        return {'data': []}


class _Tenant:
    tenant_id = 'tenant-placeholder'


class _SyncConn:
    tenant = _Tenant()

    def __init__(self):
        self.gets = []

    def _get(self, url, **kw):
        self.gets.append(url)
        return _Resp()


class _AsyncConn:
    tenant_id = 'tenant-placeholder'

    def __init__(self):
        self.gets = []

    async def _get(self, url, **kw):
        self.gets.append(url)
        return _Resp()


def _assert_message(err):
    msg = str(err)
    assert 'similar' in msg
    assert 'no longer supported' in msg
    assert 'prefix' in msg
    assert 'name' in msg


# -- signatures stay callable ------------------------------------------------

@pytest.mark.parametrize('func', [
    cogniac.CogniacConnection.search_subjects,
    cogniac.CogniacSubject.search,
    cogniac.AsyncCogniacSubject.search,
])
def test_similar_stays_in_signature(func):
    param = inspect.signature(func).parameters['similar']
    assert param.default is None


# -- sync --------------------------------------------------------------------

def test_sync_search_similar_raises_before_request():
    conn = _SyncConn()
    with pytest.raises(ValueError) as exc:
        cogniac.CogniacSubject.search(conn, similar='cat')
    _assert_message(exc.value)
    assert conn.gets == []


def test_sync_search_similar_with_prefix_raises_before_request():
    conn = _SyncConn()
    with pytest.raises(ValueError):
        cogniac.CogniacSubject.search(conn, prefix='ca', similar='cat')
    assert conn.gets == []


def test_connection_search_subjects_similar_raises_before_request():
    conn = _SyncConn()
    with pytest.raises(ValueError) as exc:
        cogniac.CogniacConnection.search_subjects(conn, similar='cat')
    _assert_message(exc.value)
    assert conn.gets == []


def test_sync_search_without_similar_is_unchanged():
    conn = _SyncConn()
    assert cogniac.CogniacSubject.search(conn, prefix='ca', limit=5) == []
    assert conn.gets == [
        '/1/tenants/tenant-placeholder/subjects?limit=5&tenant_read_write=True&prefix=ca']


# -- async -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_async_search_similar_raises_before_request():
    conn = _AsyncConn()
    with pytest.raises(ValueError) as exc:
        await cogniac.AsyncCogniacSubject.search(conn, similar='cat')
    _assert_message(exc.value)
    assert conn.gets == []


@pytest.mark.asyncio
async def test_async_search_without_similar_is_unchanged():
    conn = _AsyncConn()
    assert await cogniac.AsyncCogniacSubject.search(conn, name='cat', limit=5) == []
    assert conn.gets == [
        '/1/tenants/tenant-placeholder/subjects?limit=5&tenant_read_write=True&name=cat']


# -- CLI ---------------------------------------------------------------------

class _CliConn:
    def __init__(self):
        self.calls = []

    def search_subjects(self, **kw):
        self.calls.append(kw)
        return []


@pytest.fixture
def cli_conn(monkeypatch):
    conn = _CliConn()
    opened = []

    def _get_connection(args=None):
        opened.append(args)
        return conn

    monkeypatch.setattr(cli, 'get_connection', _get_connection)
    conn.opened = opened
    return conn


def _run(argv):
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    cli._resolve_positional_ids(parser, args)
    args.func(args)


def test_cli_similar_exits_nonzero_before_connecting(cli_conn, capsys):
    with pytest.raises(SystemExit) as exc:
        _run(['subject', 'search', '--similar', 'cat'])
    assert exc.value.code != 0
    err = json.loads(capsys.readouterr().err)['error']
    assert '--similar' in err['message']
    assert 'no longer supported' in err['message']
    assert '--prefix' in err['message'] and '--name' in err['message']
    assert cli_conn.opened == []
    assert cli_conn.calls == []


def test_cli_search_without_similar_is_unchanged(cli_conn, capsys):
    _run(['subject', 'search', '--prefix', 'ca', '--limit', '5'])
    assert len(cli_conn.calls) == 1
    call = cli_conn.calls[0]
    assert call['prefix'] == 'ca' and call['limit'] == 5
    assert call.get('similar') is None
    assert json.loads(capsys.readouterr().out) == []


def test_cli_similar_not_advertised():
    sub = cli.build_parser()._subparsers._group_actions[0].choices['subject']
    search = sub._subparsers._group_actions[0].choices['search']
    assert '--similar' not in search.format_help()
    catalog = cli._command_catalog(cli.build_parser())
    entry = [c for c in catalog if c['command'] == 'subject search']
    assert len(entry) == 1
    assert '--similar' not in [a['name'] for a in entry[0]['args']]
    assert '--similar' not in (entry[0]['help'] or '')
    assert 'similar' not in (cli.__doc__ or '')
