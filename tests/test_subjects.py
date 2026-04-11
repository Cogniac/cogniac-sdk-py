"""
Baseline tests for CogniacSubject.
"""

import pytest
from tests.conftest import requires_live
import cogniac


@requires_live
class TestSubjectRead:

    def test_get_all_subjects(self, cc):
        subjects = cc.get_all_subjects()
        assert isinstance(subjects, list)
        assert len(subjects) > 0
        s = subjects[0]
        assert s.subject_uid is not None
        assert s.name is not None

    def test_get_subject(self, cc):
        subjects = cc.get_all_subjects()
        first = subjects[0]
        fetched = cc.get_subject(first.subject_uid)
        assert fetched.subject_uid == first.subject_uid
        assert fetched.name == first.name

    def test_search_subjects_by_prefix(self, cc):
        results = cc.search_subjects(prefix="test", limit=5)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_subject_str(self, cc):
        subjects = cc.get_all_subjects()
        s = subjects[0]
        text = str(s)
        assert s.name in text
        assert s.subject_uid in text


@requires_live
class TestSubjectLifecycle:

    def test_create_update_delete(self, cc):
        # create
        s = cogniac.CogniacSubject.create(cc, name="sdk-test-lifecycle")
        assert s.name == "sdk-test-lifecycle"
        assert s.subject_uid is not None

        try:
            # update via __setattr__
            s.description = "updated by test"
            assert s.description == "updated by test"

            # read back
            fetched = cogniac.CogniacSubject.get(cc, s.subject_uid)
            assert fetched.description == "updated by test"

            # immutable attr raises
            with pytest.raises(AttributeError):
                s.subject_uid = "bad"
        finally:
            # cleanup
            s.delete()
