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
