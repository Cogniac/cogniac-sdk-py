"""
Async integration tests for AsyncCogniacMedia.
"""

import os
import tempfile
import pytest
from tests.conftest import requires_live, JPEG_BYTES
import cogniac


@requires_live
class TestAsyncMediaRead:

    @pytest.mark.asyncio
    async def test_search_media(self):
        """Search for media by filename — may return empty but shouldn't error."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            results = await cogniac.AsyncCogniacMedia.search(cc, filename="test", limit=3)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_get_media(self):
        """Get a known media item by finding one via subject associations."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            subjects = await cogniac.AsyncCogniacSubject.get_all(cc)
            for s in subjects:
                assocs = []
                async for a in s.media_associations(limit=1):
                    assocs.append(a)
                if assocs:
                    media_id = assocs[0]['media']['media_id']
                    media = await cogniac.AsyncCogniacMedia.get(cc, media_id)
                    assert media.media_id == media_id
                    return
            pytest.skip("No subjects with media associations found")

    @pytest.mark.asyncio
    async def test_media_subjects(self):
        """Fetch subjects for a known media item."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            subjects = await cogniac.AsyncCogniacSubject.get_all(cc)
            for s in subjects:
                assocs = []
                async for a in s.media_associations(limit=1):
                    assocs.append(a)
                if assocs:
                    media_id = assocs[0]['media']['media_id']
                    media = await cogniac.AsyncCogniacMedia.get(cc, media_id)
                    subs = await media.subjects()
                    assert isinstance(subs, list)
                    return
            pytest.skip("No subjects with media associations found")

    @pytest.mark.asyncio
    async def test_media_detections(self):
        """Fetch detections for a known media item."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            subjects = await cogniac.AsyncCogniacSubject.get_all(cc)
            for s in subjects:
                assocs = []
                async for a in s.media_associations(limit=1):
                    assocs.append(a)
                if assocs:
                    media_id = assocs[0]['media']['media_id']
                    media = await cogniac.AsyncCogniacMedia.get(cc, media_id)
                    dets = await media.detections()
                    assert isinstance(dets, list)
                    return
            pytest.skip("No subjects with media associations found")

    @pytest.mark.asyncio
    async def test_media_immutable_raises(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            subjects = await cogniac.AsyncCogniacSubject.get_all(cc)
            for s in subjects:
                assocs = []
                async for a in s.media_associations(limit=1):
                    assocs.append(a)
                if assocs:
                    media_id = assocs[0]['media']['media_id']
                    media = await cogniac.AsyncCogniacMedia.get(cc, media_id)
                    with pytest.raises(AttributeError):
                        media.media_id = "bad"
                    return
            pytest.skip("No subjects with media associations found")

    @pytest.mark.asyncio
    async def test_media_mutable_guard_raises(self):
        """Assigning to a mutable key should raise, directing user to set()."""
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            subjects = await cogniac.AsyncCogniacSubject.get_all(cc)
            for s in subjects:
                assocs = []
                async for a in s.media_associations(limit=1):
                    assocs.append(a)
                if assocs:
                    media_id = assocs[0]['media']['media_id']
                    media = await cogniac.AsyncCogniacMedia.get(cc, media_id)
                    with pytest.raises(AttributeError, match="set"):
                        media.meta_tags = ["should-not-work"]
                    return
            pytest.skip("No subjects with media associations found")


@requires_live
class TestAsyncMediaLifecycle:

    @pytest.mark.asyncio
    async def test_upload_and_delete(self):
        """Upload a small test image via async API, verify, delete."""
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            f.write(JPEG_BYTES)
            tmpfile = f.name

        try:
            async with await cogniac.AsyncCogniacConnection.create() as cc:
                media = await cogniac.AsyncCogniacMedia.create(
                    cc, tmpfile,
                    external_media_id="async-sdk-test-upload",
                    meta_tags=["async-sdk-test"]
                )
                assert media.media_id is not None

                # read back
                fetched = await cogniac.AsyncCogniacMedia.get(cc, media.media_id)
                assert fetched.media_id == media.media_id

                # download as bytes
                content = await fetched.download()
                assert len(content) > 0

                # cleanup
                await media.delete()
        finally:
            os.unlink(tmpfile)

    @pytest.mark.asyncio
    async def test_download_to_file(self):
        """Upload, download to file via async streaming, verify content, delete."""
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            f.write(JPEG_BYTES)
            tmpfile = f.name

        try:
            async with await cogniac.AsyncCogniacConnection.create() as cc:
                media = await cogniac.AsyncCogniacMedia.create(
                    cc, tmpfile,
                    external_media_id="async-sdk-test-dl-file",
                    meta_tags=["async-sdk-test"]
                )
                try:
                    fetched = await cogniac.AsyncCogniacMedia.get(cc, media.media_id)

                    # download to file
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as outf:
                        outfile = outf.name
                        await fetched.download(filep=outf)

                    # verify the file was written and handle is still usable
                    assert os.path.getsize(outfile) > 0
                    os.unlink(outfile)
                finally:
                    await media.delete()
        finally:
            os.unlink(tmpfile)
