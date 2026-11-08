"""
Offline tests for CogniacConnection's bootstrap round trips (no credentials needed).

Every CLI command builds a connection, so each request made in __init__ is paid on every
invocation. These tests pin how many requests construction makes, that the token call shares
the session's connection, and that the tenant-region redirect and 401 re-authentication still
work.
"""

import httpx
import pytest

from cogniac import cogniac as cogmod
from cogniac.cogniac import CogniacConnection

PREFIX = 'https://api.example.test'


class FakeApi:
    """httpx.MockTransport handler that records each request."""

    def __init__(self, region=None, expire_first_get=False):
        self.region = region
        self.expire_first_get = expire_first_get
        self.requests = []
        self.tokens_issued = 0

    def __call__(self, request):
        self.requests.append(request)
        path = request.url.path
        if path == '/1/token':
            self.tokens_issued += 1
            return httpx.Response(200, json={'access_token': 'tok%d' % self.tokens_issued})
        if self.expire_first_get and path == '/1/applications' and self.tokens_issued == 1:
            return httpx.Response(401, json={'message': 'token expired'})
        if path == '/1/tenants/current':
            return httpx.Response(200, json={'tenant_id': 't1', 'name': 'tenant one', 'region': self.region})
        if path == '/1/users/current':
            return httpx.Response(200, json={'user_id': 'u1', 'email': 'user@example.test'})
        if path in ('/1/applications', '/1/tenants/t1/applications'):
            return httpx.Response(200, json={'data': []})
        return httpx.Response(404, json={'message': 'no route %s' % path})

    def paths(self):
        return [r.url.path for r in self.requests]


@pytest.fixture
def api(monkeypatch):
    fake = FakeApi()
    monkeypatch.setattr(cogmod.httpx, 'HTTPTransport', lambda *a, **k: httpx.MockTransport(fake))

    def no_module_level_get(*a, **k):
        raise AssertionError('token call must go through the session client, not httpx.get')
    monkeypatch.setattr(cogmod.httpx, 'get', no_module_level_get)
    for var in ('COG_URL_PREFIX', 'COG_TENANT', 'COG_API_KEY', 'COG_USER', 'COG_PASS'):
        monkeypatch.delenv(var, raising=False)
    return fake


def test_explicit_url_prefix_makes_one_request(api):
    cc = CogniacConnection(api_key='k', tenant_id='t1', url_prefix=PREFIX)
    assert api.paths() == ['/1/token']
    assert api.requests[0].headers['Authorization'] == 'Key k'


def test_user_and_tenant_fetched_on_first_use_then_cached(api):
    cc = CogniacConnection(api_key='k', tenant_id='t1', url_prefix=PREFIX)
    assert cc.user.user_id == 'u1'
    assert cc.tenant.tenant_id == 't1'
    cc.user, cc.tenant
    assert api.paths() == ['/1/token', '/1/users/current', '/1/tenants/current']


def test_requests_after_token_carry_bearer_not_key(api):
    cc = CogniacConnection(api_key='k', tenant_id='t1', url_prefix=PREFIX)
    cc._get('/1/applications')
    assert api.requests[-1].headers['Authorization'] == 'Bearer tok1'


def test_default_url_prefix_still_follows_tenant_region(api, monkeypatch):
    # with no explicit url_prefix the tenant's region may redirect the connection, so the
    # tenant is still read during construction and later requests go to the region host
    monkeypatch.setattr(cogmod, 'stored_url_prefix', lambda: None)
    monkeypatch.setattr(cogmod, 'DEFAULT_COG_URL_PREFIX', PREFIX)
    api.region = 'region.example.test'
    cc = CogniacConnection(api_key='k', tenant_id='t1')
    assert api.paths() == ['/1/token', '/1/tenants/current']
    assert cc.url_prefix == 'https://region.example.test'
    cc._get('/1/applications')
    assert api.requests[-1].url.host == 'region.example.test'


def test_cog_url_prefix_env_counts_as_explicit(api, monkeypatch):
    monkeypatch.setenv('COG_URL_PREFIX', PREFIX)
    api.region = 'region.example.test'
    cc = CogniacConnection(api_key='k', tenant_id='t1')
    assert api.paths() == ['/1/token']
    assert cc.url_prefix == PREFIX


def test_expired_token_reauthenticates_on_the_same_client(api):
    api.expire_first_get = True
    cc = CogniacConnection(api_key='k', tenant_id='t1', url_prefix=PREFIX)
    session = cc.session
    resp = cc._get('/1/applications')
    assert resp.status_code == 200
    assert api.paths() == ['/1/token', '/1/applications', '/1/token', '/1/applications']
    assert api.requests[2].headers['Authorization'] == 'Key k'
    assert api.requests[-1].headers['Authorization'] == 'Bearer tok2'
    assert cc.session is session


def test_no_tenant_still_raises_helpful_error_on_tenant_access(api):
    cc = CogniacConnection(api_key='k', url_prefix=PREFIX)
    assert api.paths() == ['/1/token']
    with pytest.raises(Exception, match='Unspecified tenant'):
        cc.tenant


def test_tenant_scoped_list_does_not_read_the_tenant(api):
    from cogniac.app import CogniacApplication
    cc = CogniacConnection(api_key='k', tenant_id='t1', url_prefix=PREFIX)
    assert CogniacApplication.get_all(cc) == []
    assert api.paths() == ['/1/token', '/1/tenants/t1/applications']


def test_tenant_scoped_list_without_tenant_raises_helpful_error(api):
    from cogniac.app import CogniacApplication
    cc = CogniacConnection(api_key='k', url_prefix=PREFIX)
    with pytest.raises(Exception, match='Unspecified tenant'):
        CogniacApplication.get_all(cc)


# --- review round 1 (#196) -------------------------------------------------------------------

def _mock(monkeypatch, handler):
    """Route every client this module builds to `handler`; return the list of clients made."""
    clients = []
    real_client = httpx.Client

    def client(*a, **k):
        k['transport'] = httpx.MockTransport(handler)
        c = real_client(*a, **k)
        clients.append(c)
        return c
    monkeypatch.setattr(cogmod.httpx, 'Client', client)
    return clients


def test_failed_authentication_closes_the_client(api, monkeypatch):
    def handler(request):
        return httpx.Response(401, json={'message': 'bad key'})
    clients = _mock(monkeypatch, handler)
    with pytest.raises(Exception):
        CogniacConnection(api_key='bad', tenant_id='t1', url_prefix=PREFIX)
    assert clients and all(c.is_closed for c in clients)


def test_failed_region_read_closes_the_client(api, monkeypatch):
    monkeypatch.setattr(cogmod, 'stored_url_prefix', lambda: None)
    monkeypatch.setattr(cogmod, 'DEFAULT_COG_URL_PREFIX', PREFIX)

    def handler(request):
        if request.url.path == '/1/token':
            return httpx.Response(200, json={'access_token': 'tok'})
        return httpx.Response(403, json={'message': 'no role'})
    clients = _mock(monkeypatch, handler)
    with pytest.raises(Exception):
        CogniacConnection(api_key='k', tenant_id='t1')
    assert clients and all(c.is_closed for c in clients)


def test_cookies_from_the_token_call_do_not_ride_on_bearer_requests(api, monkeypatch):
    seen = []

    def handler(request):
        seen.append(request.headers.get('cookie'))
        if request.url.path == '/1/token':
            return httpx.Response(200, json={'access_token': 'tok'},
                                  headers={'set-cookie': 'sticky=lb1; Path=/'})
        return httpx.Response(200, json={'data': []})
    _mock(monkeypatch, handler)
    cc = CogniacConnection(api_key='k', tenant_id='t1', url_prefix=PREFIX)
    cc._get('/1/applications')
    assert seen == [None, None]


def test_reauthentication_replaces_the_header_set_instead_of_mutating_it(api):
    """Other threads may be building requests from the client's headers at that moment."""
    api.expire_first_get = True
    cc = CogniacConnection(api_key='k', tenant_id='t1', url_prefix=PREFIX)
    before = cc.session.headers
    cc._get('/1/applications')
    assert cc.session.headers is not before
    assert before['Authorization'] == 'Bearer tok1'
    assert cc.session.headers['Authorization'] == 'Bearer tok2'


def test_concurrent_401s_reauthenticate_one_at_a_time(api, monkeypatch):
    import threading
    import time
    lock = threading.Lock()
    state = {'in_token': 0, 'max_in_token': 0, 'tokens': 0}

    def handler(request):
        if request.url.path == '/1/token':
            with lock:
                state['in_token'] += 1
                state['max_in_token'] = max(state['max_in_token'], state['in_token'])
                state['tokens'] += 1
                n = state['tokens']
            time.sleep(0.02)
            with lock:
                state['in_token'] -= 1
            return httpx.Response(200, json={'access_token': 'tok%d' % n})
        if request.headers['authorization'] == 'Bearer tok1':
            return httpx.Response(401, json={'message': 'expired'})
        return httpx.Response(200, json={'data': []})
    _mock(monkeypatch, handler)
    cc = CogniacConnection(api_key='k', tenant_id='t1', url_prefix=PREFIX)
    errors = []

    def work():
        try:
            cc._get('/1/applications')
        except Exception as e:                                       # pragma: no cover
            errors.append(e)
    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert state['max_in_token'] == 1


def test_tenant_id_whitespace_is_stripped_for_tenant_scoped_urls(api):
    from cogniac.app import CogniacApplication
    cc = CogniacConnection(api_key='k', tenant_id=' t1\n', url_prefix=PREFIX)
    assert CogniacApplication.get_all(cc) == []
    assert api.paths()[-1] == '/1/tenants/t1/applications'


def test_tenant_scoped_urls_use_the_canonical_id_once_the_tenant_is_read(api):
    cc = CogniacConnection(api_key='k', tenant_id='t1', url_prefix=PREFIX)
    cc.tenant
    cc.tenant_id = 'alias-of-t1'
    assert cc._require_tenant_id() == 't1'


def test_user_password_auto_tenant_uses_the_resolved_url_prefix(api, monkeypatch):
    monkeypatch.setenv('COG_URL_PREFIX', PREFIX)
    calls = []

    def tenants(username=None, password=None, url_prefix=None):
        calls.append(url_prefix)
        return {'tenants': [{'tenant_id': 't1'}]}
    monkeypatch.setattr(CogniacConnection, 'get_all_authorized_tenants', staticmethod(tenants))
    monkeypatch.setenv('COG_USER', 'u')
    monkeypatch.setenv('COG_PASS', 'p')

    def handler(request):
        if request.url.path == '/21/users/mfa/status':
            return httpx.Response(200, json={})
        return FakeApi()(request)
    _mock(monkeypatch, handler)
    cc = CogniacConnection()
    assert calls == [PREFIX]
    assert cc.tenant_id == 't1'
