"""
CogniacWorkflow Object Client

Copyright (C) 2024 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


##
#  pure helpers: workflow summary / diff
##

# Top-level workflow fields excluded from the diff: identity fields (reported in
# the diff header), per-version bookkeeping, and the bulky rendered deployment
# artifact whose differences are derived from app_specs anyway.
_DIFF_EXCLUDED_TOP_LEVEL = frozenset([
    'app_specs', '_apply_jsons',
    'workflow_id', 'base_id', 'version',
    'created_at', 'created_by', 'updated_at', 'updated_by',
    'latest_version', 'latest_workflow_id',
    'system_software_updates_available',
])

_MISSING = object()


def _as_workflow_dict(workflow):
    """Accept a CogniacWorkflow / AsyncCogniacWorkflow instance or a plain
    workflow dict and return a plain dict of the workflow's API fields."""
    if isinstance(workflow, dict):
        return workflow
    return {k: v for k, v in workflow.__dict__.items() if not k.startswith('_')}


def _spec_model_runtime_image(spec):
    """Return the model runtime image of an app spec.

    The image is usually at the top level of the spec (`model_runtime_image`)
    but on some workflows lives nested under `app_type_config`; handle both."""
    if not isinstance(spec, dict):
        return None
    image = spec.get('model_runtime_image')
    if image is None:
        app_type_config = spec.get('app_type_config')
        if isinstance(app_type_config, dict):
            image = app_type_config.get('model_runtime_image')
    return image


def _spec_thresholds(spec):
    """Return every threshold-like field of an app spec as a flat dict.

    Threshold fields vary by app type (e.g. `threshold`, `detection_thresholds`)
    and may live at the top level of the spec or nested under `app_type_config`,
    so match any key containing 'threshold' in either location."""
    thresholds = {}
    if not isinstance(spec, dict):
        return thresholds
    containers = [('', spec)]
    app_type_config = spec.get('app_type_config')
    if isinstance(app_type_config, dict):
        containers.append(('app_type_config.', app_type_config))
    for prefix, container in containers:
        for key, value in container.items():
            if 'threshold' in key.lower():
                thresholds[prefix + key] = value
    return thresholds


def _flatten(value, prefix=''):
    """Flatten nested dicts into {dotted.path: leaf_value}.
    Lists and scalars are treated as leaf values (compared whole)."""
    if isinstance(value, dict) and value:
        flat = {}
        for k, v in value.items():
            path = "%s.%s" % (prefix, k) if prefix else str(k)
            flat.update(_flatten(v, path))
        return flat
    return {prefix: value} if prefix else {}


def _value_changes(a, b):
    """Generic deep compare of two values (typically dicts).

    Returns {dotted.path: change} where change is {'old': ..., 'new': ...};
    the 'old'/'new' key is omitted when the path is absent on that side."""
    flat_a = _flatten(a)
    flat_b = _flatten(b)
    changes = {}
    for path in sorted(set(flat_a) | set(flat_b)):
        old = flat_a.get(path, _MISSING)
        new = flat_b.get(path, _MISSING)
        if old == new:
            continue
        change = {}
        if old is not _MISSING:
            change['old'] = old
        if new is not _MISSING:
            change['new'] = new
        changes[path] = change
    return changes


def summarize_app_spec(spec):
    """Return a compact one-row summary of a single app spec: application_id,
    model_runtime_image, and any threshold fields (plus name/type when the
    workflow actually carries them — they are often null in app_specs)."""
    if not isinstance(spec, dict):
        return {'application_id': None, 'model_runtime_image': None}
    row = {
        'application_id': spec.get('application_id'),
        'model_runtime_image': _spec_model_runtime_image(spec),
    }
    for key in ('name', 'type', 'app_type'):
        if spec.get(key) is not None:
            row[key] = spec[key]
    thresholds = _spec_thresholds(spec)
    if thresholds:
        row['thresholds'] = thresholds
    return row


def workflow_summary(workflow):
    """Return a compact model-composition summary of a workflow.

    workflow: a CogniacWorkflow / AsyncCogniacWorkflow instance or a plain
              workflow dict (as returned by GET /1/workflows/{workflow_id}).

    Returns a dict with workflow identity fields plus one summary row per
    app spec (see summarize_app_spec)."""
    wf = _as_workflow_dict(workflow)
    app_specs = wf.get('app_specs') or []
    return {
        'workflow_id': wf.get('workflow_id'),
        'base_id': wf.get('base_id'),
        'version': wf.get('version'),
        'name': wf.get('name'),
        'edgeflow_model': wf.get('edgeflow_model'),
        'app_count': len(app_specs),
        'apps': [summarize_app_spec(s) for s in app_specs],
    }


def _workflow_identity(wf):
    return {'workflow_id': wf.get('workflow_id'),
            'name': wf.get('name'),
            'version': wf.get('version')}


def _group_specs_by_app(app_specs):
    """Group app specs by application_id, preserving order within each group
    (a workflow may legitimately carry multiple specs for one application)."""
    groups = {}
    for spec in (app_specs or []):
        key = spec.get('application_id') if isinstance(spec, dict) else None
        groups.setdefault(key, []).append(spec if isinstance(spec, dict) else {})
    return groups


def workflow_diff(workflow_a, workflow_b):
    """Compute a compact, reviewable diff between two workflows.

    workflow_a, workflow_b: CogniacWorkflow / AsyncCogniacWorkflow instances or
    plain workflow dicts. workflow_a is treated as the 'old' side and
    workflow_b as the 'new' side.

    Returns a dict:
      workflow_a / workflow_b: identity of each side (workflow_id, name, version)
      top_level_changes:       changed top-level fields (name, description,
                               edgeflow_model, ...). Scalar fields report
                               {'old', 'new'}; composite fields (e.g. the
                               tenant_*_config snapshots) report a terse
                               {'changed': True, 'differing_paths': N,
                                'paths': [first few dotted paths]}.
      apps_added:              summary rows for app specs only in workflow_b
      apps_removed:            summary rows for app specs only in workflow_a
      apps_changed:            {application_id: {model_runtime_image?,
                               thresholds?, changed}} — the well-known fields
                               are surfaced as {'old', 'new'} when they differ,
                               and 'changed' is the full generic deep diff of
                               the app spec keyed by dotted path.
      identical:               True when nothing above differs.
    """
    a = _as_workflow_dict(workflow_a)
    b = _as_workflow_dict(workflow_b)

    # --- top-level fields (excluding app_specs, identity, and bookkeeping) ---
    top_level_changes = {}
    for key in sorted((set(a) | set(b)) - _DIFF_EXCLUDED_TOP_LEVEL):
        old = a.get(key, _MISSING)
        new = b.get(key, _MISSING)
        if old == new:
            continue
        if isinstance(old, (dict, list)) or isinstance(new, (dict, list)):
            # composite (e.g. tenant config snapshots): stay terse
            paths = sorted(_value_changes(
                old if old is not _MISSING else None,
                new if new is not _MISSING else None))
            entry = {'changed': True}
            if paths:
                entry['differing_paths'] = len(paths)
                entry['paths'] = paths[:10]
            top_level_changes[key] = entry
        else:
            change = {}
            if old is not _MISSING:
                change['old'] = old
            if new is not _MISSING:
                change['new'] = new
            top_level_changes[key] = change

    # --- app_specs, keyed by application_id ---
    groups_a = _group_specs_by_app(a.get('app_specs'))
    groups_b = _group_specs_by_app(b.get('app_specs'))
    apps_added = []
    apps_removed = []
    apps_changed = {}
    for app_id in sorted(set(groups_a) | set(groups_b), key=lambda k: (k is None, str(k))):
        specs_a = groups_a.get(app_id, [])
        specs_b = groups_b.get(app_id, [])
        # pair positionally within the application_id group; extras are adds/removes
        for i in range(max(len(specs_a), len(specs_b))):
            if i >= len(specs_a):
                apps_added.append(summarize_app_spec(specs_b[i]))
                continue
            if i >= len(specs_b):
                apps_removed.append(summarize_app_spec(specs_a[i]))
                continue
            spec_a, spec_b = specs_a[i], specs_b[i]
            changes = _value_changes(spec_a, spec_b)
            if not changes:
                continue
            entry = {}
            image_a = _spec_model_runtime_image(spec_a)
            image_b = _spec_model_runtime_image(spec_b)
            if image_a != image_b:
                entry['model_runtime_image'] = {'old': image_a, 'new': image_b}
            thresholds_a = _spec_thresholds(spec_a)
            thresholds_b = _spec_thresholds(spec_b)
            if thresholds_a != thresholds_b:
                entry['thresholds'] = {'old': thresholds_a, 'new': thresholds_b}
            entry['changed'] = changes
            key = str(app_id) if len(specs_a) <= 1 and len(specs_b) <= 1 \
                else "%s[%d]" % (app_id, i)
            apps_changed[key] = entry

    return {
        'workflow_a': _workflow_identity(a),
        'workflow_b': _workflow_identity(b),
        'top_level_changes': top_level_changes,
        'apps_added': apps_added,
        'apps_removed': apps_removed,
        'apps_changed': apps_changed,
        'identical': not (top_level_changes or apps_added or apps_removed or apps_changed),
    }


##
#  CogniacWorkflow
##
class CogniacWorkflow(object):
    """
    CogniacWorkflow

    A workflow is an immutable, frozen snapshot of an application pipeline that
    can be deployed to EdgeFlow / CloudFlow.

    Get an existing workflow with
    CogniacConnection.get_workflow() or CogniacWorkflow.get()

    Get all of the tenant's workflows with
    CogniacConnection.get_all_workflows() or CogniacWorkflow.get_all()
    """

    ##
    #  get_all
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_all(cls, connection):
        """
        Return all CogniacWorkflow objects belonging to the authenticated tenant.

        See GET /1/tenants/{tenant_id}/workflows.
        """
        resp = connection._get("/1/tenants/%s/workflows" % connection.tenant.tenant_id)
        data = resp.json()
        items = data.get('data', data) if isinstance(data, dict) else data
        return [CogniacWorkflow(connection, w) for w in items]

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get(cls, connection, workflow_id):
        """
        Return a single CogniacWorkflow by workflow_id.

        See GET /1/workflows/{workflow_id}.
        """
        resp = connection._get("/1/workflows/%s" % workflow_id)
        return CogniacWorkflow(connection, resp.json())

    ##
    #  create
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def create(cls, connection, body=None):
        """
        Create a new workflow.

        body (dict):  CreateWorkflowRequest body

        See POST /1/workflows.
        """
        resp = connection._post("/1/workflows", json=body if body is not None else {})
        return CogniacWorkflow(connection, resp.json())

    ##
    #  edgeflow_targets
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def edgeflow_targets(cls, connection, edgeflow_model=None):
        """
        Return the supported EdgeFlow model targets, or details for a single model.

        edgeflow_model (str):  optional EdgeFlow model name; when supplied, the
                               detailed target info for that model is returned.

        See GET /1/workflows/eftargets and GET /1/workflows/eftargets/{edgeflow_model}.
        """
        if edgeflow_model is not None:
            resp = connection._get("/1/workflows/eftargets/%s" % edgeflow_model)
        else:
            resp = connection._get("/1/workflows/eftargets")
        return resp.json()

    ##
    #  new_version
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def new_version(cls, connection, base_id, body):
        """
        Create a new version of a workflow.

        base_id (str):  the base workflow id
        body (dict):    CreateWorkflowVersionRequest body

        See POST /1/workflows/{base_id}/versions.
        """
        resp = connection._post("/1/workflows/%s/versions" % base_id, json=body)
        return CogniacWorkflow(connection, resp.json())

    ##
    #  get_all_versions
    ##
    @classmethod
    def get_all_versions(cls, connection, base_id, reverse=True, limit=None, last_key=None):
        """
        Yield every version of a workflow base as CogniacWorkflow objects,
        following the DynamoDB last_key cursor until the versions are drained.

        The versions endpoint yields summary records (workflow_id, version,
        name, created_at, created_by, description, edgeflow_model, base_id,
        tenant_id) WITHOUT app_specs; fetch the full workflow via get()
        before diffing or summarizing.

        base_id (str)    the workflow base id; a full workflow_id of the form
                         <base_id>:<version> is also accepted (the version
                         suffix is ignored)
        reverse (bool)   newest first when True (default)
        limit (int)      yield a maximum of limit versions
        last_key (str)   resume from a previous last_key cursor

        See GET /1/workflows/{base_id}/versions.
        """
        base_id = base_id.split(':', 1)[0]  # tolerate a full <base_id>:<version>

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        def get_next(last_key):
            params = {'reverse': reverse}
            if limit is not None:
                params['limit'] = limit
            if last_key is not None:
                params['last_key'] = last_key
            resp = connection._get("/1/workflows/%s/versions" % base_id, params=params)
            return resp.json()

        count = 0
        while True:
            resp = get_next(last_key)
            data = resp['data'] if isinstance(resp, dict) and 'data' in resp else resp
            for record in data or []:
                yield CogniacWorkflow(connection, record)
                count += 1
                if limit and count == limit:
                    return
            last_key = resp.get('last_key') if isinstance(resp, dict) else None
            if not last_key:
                return

    ##
    #  get_version
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_version(cls, connection, base_id, version):
        """
        Return a specific workflow version.

        See GET /1/workflows/{base_id}/versions/{version}.
        """
        resp = connection._get("/1/workflows/%s/versions/%s" % (base_id, version))
        return CogniacWorkflow(connection, resp.json())

    def __init__(self, connection, workflow_dict):
        self._cc = connection
        self._workflow_keys = workflow_dict.keys()
        for k, v in workflow_dict.items():
            super(CogniacWorkflow, self).__setattr__(k, v)

    def __str__(self):
        return "%s (%s)" % (getattr(self, 'name', '?'), getattr(self, 'workflow_id', '?'))

    def __repr__(self):
        return self.__str__()

    ##
    #  summary
    ##
    def summary(self):
        """
        Return a compact model-composition summary of this workflow:
        one row per app spec with application_id, model_runtime_image, and
        threshold fields. Pure local computation (no API call).
        """
        return workflow_summary(self)

    ##
    #  diff
    ##
    def diff(self, other):
        """
        Return a compact diff between this workflow ('old' side) and another
        workflow ('new' side): top-level field changes, apps added/removed,
        and per-app-spec field changes keyed by application_id.

        other: a CogniacWorkflow instance or a plain workflow dict.

        Pure local computation (no API call); see workflow_diff().
        """
        return workflow_diff(self, other)

    ##
    #  delete
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def delete(self):
        """
        Delete this workflow.

        See DELETE /1/workflows/{workflow_id}.
        """
        self._cc._delete("/1/workflows/%s" % self.workflow_id)
