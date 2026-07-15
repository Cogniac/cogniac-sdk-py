"""
Unit tests for workflow diff / model-composition summary (issue #182).

These tests do NOT require live credentials — they operate on fixture
workflow dicts (and mock the HTTP layer where an entity object is needed).
"""

import copy
from unittest.mock import MagicMock

import cogniac
from cogniac.workflow import CogniacWorkflow, workflow_diff, workflow_summary


# ---------------------------------------------------------------------------
# fixture workflows (invented placeholder ids — no real tenant data)
# ---------------------------------------------------------------------------

def make_workflow_a():
    """Baseline workflow version fixture."""
    return {
        "tenant_id": "tttesttenant",
        "workflow_id": "wfbase0001:3",
        "base_id": "wfbase0001",
        "version": 3,
        "name": "example-inspection-pipeline",
        "description": "example pipeline",
        "edgeflow_model": "example-gpu-model",
        "created_by": "user@example.com",
        "created_at": 1700000000.0,
        "tenant_subject_config": {"subjects": [{"subject_uid": "subj_alpha", "name": "alpha"}]},
        "tenant_camera_config": {"cameras": []},
        "app_specs": [
            {
                # detection app: image at top level, name/type null (as seen in the wild)
                "application_id": "appdetect00001",
                "name": None,
                "type": None,
                "model_runtime_image": "registry.example.com/runtime/detector:1.2.3",
                "detection_thresholds": {"subj_alpha": 0.5},
                "input_subject_uids": ["subj_input"],
            },
            {
                # classification app: image + threshold nested under app_type_config
                "application_id": "appclassify001",
                "name": None,
                "type": None,
                "app_type_config": {
                    "model_runtime_image": "registry.example.com/runtime/classifier:4.5.6",
                    "threshold": 0.9,
                },
                "input_subject_uids": ["subj_alpha"],
            },
            {
                # app that will be removed in workflow B
                "application_id": "appocr00000001",
                "model_runtime_image": "registry.example.com/runtime/ocr:7.8.9",
                "input_subject_uids": ["subj_alpha"],
            },
            {
                # third spec shape seen in production: top-level name/type null,
                # NO spec-level app_type_config, and everything meaningful
                # (name, type, thresholds, mirrored image) embedded in the
                # app_config application-record snapshot
                "application_id": "appgauge000001",
                "name": None,
                "type": None,
                "input_subject_uids": ["subj_alpha"],
                "app_config": {
                    "application_id": "appgauge000001",
                    "name": "gauge-reader",
                    "type": "detection",
                    "model_runtime_image": "registry.example.com/runtime/gauge:2.0.0",
                    "detection_thresholds": {"subj_gauge": 0.4},
                    "input_threshold": 0.3,
                    "modified_at": 1690000000.0,
                },
            },
        ],
    }


def make_workflow_b():
    """Next version: one image retag, one threshold change, one app removed,
    one app added, and a name change."""
    wf = copy.deepcopy(make_workflow_a())
    wf["workflow_id"] = "wfbase0001:4"
    wf["version"] = 4
    wf["name"] = "example-inspection-pipeline-v2"
    wf["created_at"] = 1700001000.0
    specs = wf["app_specs"]
    # the incident scenario: a single model_runtime_image retag
    specs[0]["model_runtime_image"] = "registry.example.com/runtime/detector:1.2.4"
    # nested threshold change
    specs[1]["app_type_config"]["threshold"] = 0.75
    # remove the ocr app, add a counting app
    del specs[2]
    specs.append({
        "application_id": "appcount000001",
        "model_runtime_image": "registry.example.com/runtime/counter:0.1.0",
        "input_subject_uids": ["subj_alpha"],
    })
    return wf


# ---------------------------------------------------------------------------
# workflow_diff
# ---------------------------------------------------------------------------

class TestWorkflowDiff:

    def test_identical_workflows(self):
        wf = make_workflow_a()
        d = workflow_diff(wf, copy.deepcopy(wf))
        assert d["identical"] is True
        assert d["top_level_changes"] == {}
        assert d["apps_added"] == []
        assert d["apps_removed"] == []
        assert d["apps_changed"] == {}

    def test_diff_header_identifies_both_sides(self):
        d = workflow_diff(make_workflow_a(), make_workflow_b())
        assert d["workflow_a"] == {"workflow_id": "wfbase0001:3",
                                   "name": "example-inspection-pipeline",
                                   "version": 3}
        assert d["workflow_b"] == {"workflow_id": "wfbase0001:4",
                                   "name": "example-inspection-pipeline-v2",
                                   "version": 4}
        assert d["identical"] is False

    def test_image_retag_detected(self):
        """The incident case: a single app's model_runtime_image retag must be
        surfaced prominently, keyed by application_id."""
        d = workflow_diff(make_workflow_a(), make_workflow_b())
        entry = d["apps_changed"]["appdetect00001"]
        assert entry["model_runtime_image"] == {
            "old": "registry.example.com/runtime/detector:1.2.3",
            "new": "registry.example.com/runtime/detector:1.2.4",
        }
        # the generic deep diff carries the same change by dotted path
        assert entry["changed"]["model_runtime_image"] == {
            "old": "registry.example.com/runtime/detector:1.2.3",
            "new": "registry.example.com/runtime/detector:1.2.4",
        }

    def test_nested_image_retag_detected(self):
        """model_runtime_image nested under app_type_config is also detected."""
        a = make_workflow_a()
        b = copy.deepcopy(a)
        b["app_specs"][1]["app_type_config"]["model_runtime_image"] = \
            "registry.example.com/runtime/classifier:4.5.7"
        d = workflow_diff(a, b)
        entry = d["apps_changed"]["appclassify001"]
        assert entry["model_runtime_image"] == {
            "old": "registry.example.com/runtime/classifier:4.5.6",
            "new": "registry.example.com/runtime/classifier:4.5.7",
        }

    def test_threshold_change_detected(self):
        d = workflow_diff(make_workflow_a(), make_workflow_b())
        entry = d["apps_changed"]["appclassify001"]
        assert entry["thresholds"] == {
            "old": {"app_type_config.threshold": 0.9},
            "new": {"app_type_config.threshold": 0.75},
        }
        assert entry["changed"]["app_type_config.threshold"] == {"old": 0.9, "new": 0.75}

    def test_top_level_threshold_change_detected(self):
        a = make_workflow_a()
        b = copy.deepcopy(a)
        b["app_specs"][0]["detection_thresholds"]["subj_alpha"] = 0.6
        d = workflow_diff(a, b)
        entry = d["apps_changed"]["appdetect00001"]
        assert entry["thresholds"]["old"]["detection_thresholds"] == {"subj_alpha": 0.5}
        assert entry["thresholds"]["new"]["detection_thresholds"] == {"subj_alpha": 0.6}
        # no image change on this spec, so the prominent field is absent
        assert "model_runtime_image" not in entry

    def test_added_and_removed_apps(self):
        d = workflow_diff(make_workflow_a(), make_workflow_b())
        added_ids = [row["application_id"] for row in d["apps_added"]]
        removed_ids = [row["application_id"] for row in d["apps_removed"]]
        assert added_ids == ["appcount000001"]
        assert removed_ids == ["appocr00000001"]
        assert d["apps_added"][0]["model_runtime_image"] == \
            "registry.example.com/runtime/counter:0.1.0"
        assert d["apps_removed"][0]["model_runtime_image"] == \
            "registry.example.com/runtime/ocr:7.8.9"
        # added/removed apps are not double-reported as changed
        assert "appcount000001" not in d["apps_changed"]
        assert "appocr00000001" not in d["apps_changed"]

    def test_unchanged_app_not_reported(self):
        a = make_workflow_a()
        b = copy.deepcopy(a)
        b["app_specs"][0]["model_runtime_image"] = "registry.example.com/runtime/detector:9.9.9"
        d = workflow_diff(a, b)
        assert list(d["apps_changed"]) == ["appdetect00001"]

    def test_top_level_scalar_changes(self):
        d = workflow_diff(make_workflow_a(), make_workflow_b())
        assert d["top_level_changes"]["name"] == {
            "old": "example-inspection-pipeline",
            "new": "example-inspection-pipeline-v2",
        }
        # identity / bookkeeping fields are excluded from top-level changes
        for excluded in ("workflow_id", "version", "created_at", "app_specs"):
            assert excluded not in d["top_level_changes"]

    def test_top_level_composite_changes_are_terse(self):
        a = make_workflow_a()
        b = copy.deepcopy(a)
        b["tenant_subject_config"]["subjects"][0]["name"] = "alpha-renamed"
        d = workflow_diff(a, b)
        entry = d["top_level_changes"]["tenant_subject_config"]
        assert entry["changed"] is True
        assert entry["differing_paths"] == 1
        assert entry["paths"] == ["subjects"]

    def test_accepts_workflow_objects(self):
        cc = MagicMock()
        wf_a = CogniacWorkflow(cc, make_workflow_a())
        wf_b = CogniacWorkflow(cc, make_workflow_b())
        d = wf_a.diff(wf_b)
        assert d["identical"] is False
        assert "appdetect00001" in d["apps_changed"]
        # module function accepts objects too, and mixing objects/dicts works
        assert workflow_diff(wf_a, make_workflow_b()) == d

    def test_exported_from_package(self):
        assert cogniac.workflow_diff is workflow_diff
        assert cogniac.workflow_summary is workflow_summary

    def test_missing_app_specs_tolerated_and_flagged(self):
        a = make_workflow_a()
        del a["app_specs"]
        b = make_workflow_a()
        d = workflow_diff(a, b)
        assert [row["application_id"] for row in d["apps_added"]] == \
            ["appclassify001", "appdetect00001", "appgauge000001", "appocr00000001"]
        assert d["apps_removed"] == []
        # the absent side is explicitly flagged, the populated side is not
        assert d["workflow_a"]["app_specs_missing"] is True
        assert "app_specs_missing" not in d["workflow_b"]

    def test_empty_app_specs_not_flagged_as_missing(self):
        """An explicit empty pipeline is not the same as an absent app_specs
        key (versions-list summary records omit app_specs entirely)."""
        a = make_workflow_a()
        a["app_specs"] = []
        d = workflow_diff(a, make_workflow_a())
        assert "app_specs_missing" not in d["workflow_a"]
        assert len(d["apps_added"]) == 4

    # ---- app_config fallback (third spec shape seen in production) ----

    def test_app_config_only_image_retag_surfaced_prominently(self):
        """A retag visible only via the app_config record still fires the
        prominent model_runtime_image field (no top-level or app_type_config
        copy exists on this spec shape)."""
        a = make_workflow_a()
        b = copy.deepcopy(a)
        b["app_specs"][3]["app_config"]["model_runtime_image"] = \
            "registry.example.com/runtime/gauge:2.1.0"
        d = workflow_diff(a, b)
        entry = d["apps_changed"]["appgauge000001"]
        assert entry["model_runtime_image"] == {
            "old": "registry.example.com/runtime/gauge:2.0.0",
            "new": "registry.example.com/runtime/gauge:2.1.0",
        }

    def test_app_config_threshold_change_surfaced_prominently(self):
        a = make_workflow_a()
        b = copy.deepcopy(a)
        b["app_specs"][3]["app_config"]["input_threshold"] = 0.5
        d = workflow_diff(a, b)
        entry = d["apps_changed"]["appgauge000001"]
        assert entry["thresholds"]["old"]["app_config.input_threshold"] == 0.3
        assert entry["thresholds"]["new"]["app_config.input_threshold"] == 0.5

    def test_app_config_mirror_does_not_override_top_level(self):
        """Fallback, not merge: the app_config image mirror churns independently
        of the authoritative top-level field, so when the top level carries the
        image, mirror-only churn must not fire the prominent field (it still
        shows up in the generic deep diff)."""
        a = make_workflow_a()
        a["app_specs"][0]["app_config"] = {
            "name": "detector",
            "model_runtime_image": "registry.example.com/runtime/detector:1.2.2",  # stale mirror
        }
        b = copy.deepcopy(a)
        b["app_specs"][0]["app_config"]["model_runtime_image"] = \
            "registry.example.com/runtime/detector:1.2.3"
        d = workflow_diff(a, b)
        entry = d["apps_changed"]["appdetect00001"]
        assert "model_runtime_image" not in entry
        assert entry["changed"]["app_config.model_runtime_image"] == {
            "old": "registry.example.com/runtime/detector:1.2.2",
            "new": "registry.example.com/runtime/detector:1.2.3",
        }


# ---------------------------------------------------------------------------
# workflow_summary
# ---------------------------------------------------------------------------

class TestWorkflowSummary:

    def test_summary_shape(self):
        s = workflow_summary(make_workflow_a())
        assert s["workflow_id"] == "wfbase0001:3"
        assert s["base_id"] == "wfbase0001"
        assert s["version"] == 3
        assert s["edgeflow_model"] == "example-gpu-model"
        assert s["app_count"] == 4
        assert len(s["apps"]) == 4
        assert "app_specs_missing" not in s

    def test_summary_rows(self):
        s = workflow_summary(make_workflow_a())
        rows = {row["application_id"]: row for row in s["apps"]}
        # top-level image + thresholds
        detect = rows["appdetect00001"]
        assert detect["model_runtime_image"] == "registry.example.com/runtime/detector:1.2.3"
        assert detect["thresholds"] == {"detection_thresholds": {"subj_alpha": 0.5}}
        # nested (app_type_config) image + threshold
        classify = rows["appclassify001"]
        assert classify["model_runtime_image"] == "registry.example.com/runtime/classifier:4.5.6"
        assert classify["thresholds"] == {"app_type_config.threshold": 0.9}
        # null name/type are omitted rather than emitted as nulls
        assert "name" not in detect

    def test_summary_resolves_fields_from_app_config(self):
        """Third spec shape: no API join needed — name/type, the image, and
        thresholds all resolve from the embedded app_config record."""
        s = workflow_summary(make_workflow_a())
        row = {r["application_id"]: r for r in s["apps"]}["appgauge000001"]
        assert row["name"] == "gauge-reader"
        assert row["type"] == "detection"
        assert row["model_runtime_image"] == "registry.example.com/runtime/gauge:2.0.0"
        assert row["thresholds"] == {
            "app_config.detection_thresholds": {"subj_gauge": 0.4},
            "app_config.input_threshold": 0.3,
        }

    def test_summary_top_level_name_wins_over_app_config(self):
        wf = make_workflow_a()
        wf["app_specs"][3]["name"] = "authoritative-name"
        row = workflow_summary(wf)["apps"][3]
        assert row["name"] == "authoritative-name"

    def test_summary_includes_name_when_present(self):
        wf = make_workflow_a()
        wf["app_specs"][0]["name"] = "detector"
        wf["app_specs"][0]["type"] = "detection"
        row = workflow_summary(wf)["apps"][0]
        assert row["name"] == "detector"
        assert row["type"] == "detection"

    def test_summary_on_workflow_object(self):
        cc = MagicMock()
        wf = CogniacWorkflow(cc, make_workflow_a())
        assert wf.summary() == workflow_summary(make_workflow_a())

    def test_summary_flags_absent_app_specs(self):
        """Summary records from the versions list endpoint omit app_specs
        entirely; report that explicitly instead of claiming zero apps."""
        for strip in (lambda wf: wf.pop("app_specs"),
                      lambda wf: wf.update(app_specs=None)):
            wf = make_workflow_a()
            strip(wf)
            s = workflow_summary(wf)
            assert s["app_count"] == 0
            assert s["apps"] == []
            assert s["app_specs_missing"] is True

    def test_summary_empty_app_specs_not_flagged(self):
        wf = make_workflow_a()
        wf["app_specs"] = []
        s = workflow_summary(wf)
        assert s["app_count"] == 0
        assert "app_specs_missing" not in s


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

class TestCliWiring:

    def test_workflow_diff_command_parses(self):
        from cogniac.cli import build_parser, cmd_workflows_diff
        args = build_parser().parse_args(["workflow", "diff", "wfbase0001:3", "wfbase0001:4"])
        assert args.func is cmd_workflows_diff
        assert args.workflow_a == "wfbase0001:3"
        assert args.workflow_b == "wfbase0001:4"

    def test_workflow_summary_command_parses(self):
        from cogniac.cli import build_parser, cmd_workflows_summary
        args = build_parser().parse_args(["workflow", "summary", "--workflow-id", "wfbase0001:3"])
        assert args.func is cmd_workflows_summary
        assert args.workflow_id == "wfbase0001:3"
