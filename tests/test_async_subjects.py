"""
Async integration tests for AsyncCogniacSubject.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestAsyncSubjectRead:

    @pytest.mark.asyncio
    async def test_get_all_subjects(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            subjects = await cogniac.AsyncCogniacSubject.get_all(cc)
            assert isinstance(subjects, list)
            assert len(subjects) > 0
            s = subjects[0]
            assert s.subject_uid is not None
            assert s.name is not None

    @pytest.mark.asyncio
    async def test_get_subject(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            subjects = await cogniac.AsyncCogniacSubject.get_all(cc)
            first = subjects[0]
            fetched = await cogniac.AsyncCogniacSubject.get(cc, first.subject_uid)
            assert fetched.subject_uid == first.subject_uid

    @pytest.mark.asyncio
    async def test_search_subjects_by_prefix(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            results = await cogniac.AsyncCogniacSubject.search(cc, prefix="test", limit=5)
            assert isinstance(results, list)
            assert len(results) > 0


@requires_live
class TestAsyncSubjectLifecycle:

    @pytest.mark.asyncio
    async def test_create_set_delete(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            s = await cogniac.AsyncCogniacSubject.create(cc, name="async-sdk-test")
            assert s.name == "async-sdk-test"
            assert s.subject_uid is not None

            try:
                # update via explicit set()
                await s.set(description="async updated")
                assert s.description == "async updated"

                # read back
                fetched = await cogniac.AsyncCogniacSubject.get(cc, s.subject_uid)
                assert fetched.description == "async updated"

                # immutable raises
                with pytest.raises(AttributeError):
                    s.subject_uid = "bad"
            finally:
                await s.delete()

    @pytest.mark.asyncio
    async def test_media_associations_generator(self):
        async with await cogniac.AsyncCogniacConnection.create() as cc:
            subjects = await cogniac.AsyncCogniacSubject.get_all(cc)
            for s in subjects:
                assocs = []
                async for a in s.media_associations(limit=3):
                    assocs.append(a)
                if len(assocs) > 0:
                    assert 'media' in assocs[0]
                    return
            pytest.skip("No subjects with media associations found")
