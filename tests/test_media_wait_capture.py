"""
detections(wait_capture_id=...) against the API's capture deadline (no creds).

The API ends a wait_capture_id poll at a 60s deadline with a 504 capture_timeout body
whose capture_consumed field says whether re-polling the same capture_id can still
deliver the detections; the proxy in front of it times out at 70s. These tests drive
the real connection _get path (sync and async) with a scripted HTTP session.
"""

import asyncio
from types import SimpleNamespace

import httpx
import pytest
import tenacity

import cogniac
from cogniac.cogniac import CogniacConnection
from cogniac.async_connection import AsyncCogniacConnection


MEDIA_ID = 'media-placeholder'
CAPTURE_ID = 'capture-placeholder'
DETECTIONS = {'detections': [{'detection_id': 'd1', 'app_data': '{"score": 1}'}]}


def _capture_timeout(consumed):
    return httpx.Response(504, json={'error': 'capture_timeout',
                                     'message': 'Detections not ready within 60s.',
                                     'capture_id': CAPTURE_ID, 'media_id': MEDIA_ID,
                                     'capture_consumed': consumed, 'assertions': []})


def _nginx_504():
    return httpx.Response(504, text='<html><head><title>504 Gateway Time-out</title></head></html>',
                          headers={'content-type': 'text/html'})


def _poll(kind, responses, monkeypatch, wait_capture_id=CAPTURE_ID):
    """Call detections() on a sync or async media over a scripted session.

    Each request returns the next scripted response (the last one repeats) and
    advances a fake clock by 61s, as a poll that runs into the API's deadline does.
    Returns (result, exception, calls) where calls is a list of (url, timeout);
    re-authentications are appended to calls as ('reauth', None).
    """
    clock = [0.0]
    calls = []
    monkeypatch.setattr(tenacity, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr('time.sleep', lambda s: None)
    real_sleep = asyncio.sleep

    async def no_sleep(seconds, *args, **kwargs):
        await real_sleep(0)
    monkeypatch.setattr(asyncio, 'sleep', no_sleep)

    requests = []

    def respond(url, kw):
        calls.append((str(url), kw.get('timeout')))
        requests.append(1)
        clock[0] += 61
        return responses[min(len(requests), len(responses)) - 1]

    class _Session:
        def request(self, method, url, **kw):
            return respond(url, kw)

    class _AsyncSession:
        async def request(self, method, url, **kw):
            return respond(url, kw)

    async def async_reauth():
        calls.append(('reauth', None))

    if kind == 'sync':
        conn = object.__new__(CogniacConnection)
        conn.session = _Session()
        conn._CogniacConnection__authenticate = lambda: calls.append(('reauth', None))
        media_cls = cogniac.CogniacMedia
    else:
        conn = object.__new__(AsyncCogniacConnection)
        conn.session = _AsyncSession()
        conn._AsyncCogniacConnection__authenticate = async_reauth
        media_cls = cogniac.AsyncCogniacMedia
    conn.url_prefix = 'https://example.invalid'
    conn.timeout = 60
    media = media_cls(conn, {'media_id': MEDIA_ID})

    result = exc = None
    try:
        if kind == 'sync':
            result = media.detections(wait_capture_id=wait_capture_id)
        else:
            result = asyncio.run(media.detections(wait_capture_id=wait_capture_id))
    except Exception as e:
        exc = e
    return result, exc, calls


KINDS = ['sync', 'async']


@pytest.mark.parametrize('kind', KINDS)
def test_wait_poll_timeout_is_above_the_proxy_timeout(kind, monkeypatch):
    # the client must not hang up before the API's 60s deadline 504 arrives through the 70s proxy
    result, exc, calls = _poll(kind, [httpx.Response(200, json=DETECTIONS)], monkeypatch)
    assert exc is None
    assert result[0]['app_data'] == {'score': 1}
    assert calls[0][0].endswith('/1/media/%s/detections?wait_capture_id=%s' % (MEDIA_ID, CAPTURE_ID))
    assert calls[0][1] > 70, "wait_capture_id poll timeout %r does not exceed the 70s proxy" % calls[0][1]


@pytest.mark.parametrize('kind', KINDS)
def test_plain_detections_keep_the_connection_timeout_and_retry(kind, monkeypatch):
    # calls without wait_capture_id are unchanged: connection timeout, 5xx retried
    result, exc, calls = _poll(kind, [httpx.Response(504, text='busy'), httpx.Response(200, json=DETECTIONS)],
                               monkeypatch, wait_capture_id=None)
    assert exc is None
    assert result[0]['detection_id'] == 'd1'
    assert [c[1] for c in calls] == [60, 60]
    assert all('wait_capture_id' not in c[0] for c in calls)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('first', [_capture_timeout(False), _capture_timeout(None), _nginx_504()],
                         ids=['consumed-false', 'consumed-null', 'nginx-html'])
def test_unconsumed_or_unknown_504_repolls_the_same_capture(kind, first, monkeypatch):
    result, exc, calls = _poll(kind, [first, httpx.Response(200, json=DETECTIONS)], monkeypatch)
    assert exc is None
    assert result[0]['detection_id'] == 'd1'
    assert len(calls) == 2
    assert all(c[0].endswith('?wait_capture_id=%s' % CAPTURE_ID) for c in calls)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('response', [_capture_timeout(True), httpx.Response(503, json={'message': 'gone'})],
                         ids=['504-consumed-true', '503'])
def test_consumed_capture_raises_a_new_capture_error_without_repolling(kind, response, monkeypatch):
    result, exc, calls = _poll(kind, [response, httpx.Response(200, json=DETECTIONS)], monkeypatch)
    assert len(calls) == 1, "re-polled a consumed capture %d times" % len(calls)
    assert type(exc).__name__ == 'CaptureConsumedError', "got %r" % exc
    assert type(exc) is getattr(cogniac, 'CaptureConsumedError', None)
    assert isinstance(exc, cogniac.ServerError)
    assert exc.status_code == response.status_code
    assert exc.capture_id == CAPTURE_ID
    assert 'new capture' in str(exc)


@pytest.mark.parametrize('kind', KINDS)
def test_500_is_reported_without_repolling(kind, monkeypatch):
    result, exc, calls = _poll(kind, [httpx.Response(500, json={'message': 'boom'}),
                                      httpx.Response(200, json=DETECTIONS)], monkeypatch)
    assert len(calls) == 1, "re-polled after a 500 %d times" % len(calls)
    assert type(exc) is cogniac.ServerError, "got %r" % exc
    assert exc.status_code == 500


@pytest.mark.parametrize('kind', KINDS)
def test_repolling_stops_once_the_capture_is_about_180s_old(kind, monkeypatch):
    # every poll runs into the 60s deadline (61s on the fake clock): polls end at 61, 122 and 183s
    result, exc, calls = _poll(kind, [_capture_timeout(False)], monkeypatch)
    assert len(calls) == 3, "polled %d times" % len(calls)
    assert type(exc) is cogniac.ServerError, "got %r" % exc
    assert exc.status_code == 504


@pytest.mark.parametrize('kind', KINDS)
def test_expired_credentials_reauthenticate_and_repoll(kind, monkeypatch):
    result, exc, calls = _poll(kind, [httpx.Response(401, text='expired'), httpx.Response(200, json=DETECTIONS)],
                               monkeypatch)
    assert exc is None, "got %r" % exc
    assert result[0]['detection_id'] == 'd1'
    assert [c[0] == 'reauth' for c in calls] == [False, True, False]
