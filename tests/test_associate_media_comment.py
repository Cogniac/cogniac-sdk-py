"""
associate_media sends an optional assertion comment (no creds).

The capture body carries `comment` only when the caller passes one; without it
the body is unchanged.
"""

import pytest

import cogniac


class _Resp:
    def json(self):
        return {'capture_id': 'capture-placeholder'}


class _SyncConn:
    def __init__(self):
        self.posts = []

    def _post(self, url, json=None, **kw):
        self.posts.append((url, json))
        return _Resp()


class _AsyncConn:
    def __init__(self):
        self.posts = []

    async def _post(self, url, json=None, **kw):
        self.posts.append((url, json))
        return _Resp()


def _subject(cls, conn):
    return cls(conn, {'subject_uid': 'subject-placeholder'})


def test_associate_media_sends_comment():
    conn = _SyncConn()
    _subject(cogniac.CogniacSubject, conn).associate_media('media-placeholder', comment='x')
    url, body = conn.posts[-1]
    assert url == '/1/subjects/subject-placeholder/media'
    assert body['comment'] == 'x'


def test_associate_media_omits_comment_when_not_given():
    conn = _SyncConn()
    _subject(cogniac.CogniacSubject, conn).associate_media('media-placeholder')
    assert 'comment' not in conn.posts[-1][1]


@pytest.mark.asyncio
async def test_async_associate_media_sends_comment():
    conn = _AsyncConn()
    await _subject(cogniac.AsyncCogniacSubject, conn).associate_media('media-placeholder', comment='x')
    url, body = conn.posts[-1]
    assert url == '/1/subjects/subject-placeholder/media'
    assert body['comment'] == 'x'


@pytest.mark.asyncio
async def test_async_associate_media_omits_comment_when_not_given():
    conn = _AsyncConn()
    await _subject(cogniac.AsyncCogniacSubject, conn).associate_media('media-placeholder')
    assert 'comment' not in conn.posts[-1][1]
