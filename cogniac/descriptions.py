"""
Tenant, application and subject descriptions kept in a file under version control.

A descriptions file (`descriptions-<tenant_id>.yaml`) lists the descriptions to manage for one tenant:

    tenant:
      tenant_id: <tenant_id>
      name: <tenant name>                # for readability only; never applied
      description: |
        ...
    applications:
      <application_id>:
        name: <application name>
        description: |
          ...
    subjects:
      <subject_uid>:
        name: <subject name>
        description: |
          ...

Only descriptions are managed. Anything not listed is left alone; a listed entry must have a
`description` key, and `description: ""` clears that description. `plan` compares the file with the
live tenant and `apply` writes the descriptions that differ, from the file and the live values alone.

Copyright (C) 2026 Cogniac Corporation
"""

import yaml

from .common import ClientError

MAX_LENGTH = 8000
_SECTIONS = ('applications', 'subjects')


class DescriptionsError(ValueError):
    """The descriptions file is invalid, or names an application or subject the tenant doesn't have."""


def load(path):
    """Read and validate a descriptions file; return it as a dict. Raises DescriptionsError."""
    with open(path) as f:
        doc = yaml.safe_load(f) or {}
    validate(doc)
    return doc


def validate(doc):
    problems = []
    if not isinstance(doc, dict):
        raise DescriptionsError("the file is not a mapping")
    unknown = set(doc) - {'tenant'} - set(_SECTIONS)
    if unknown:
        problems.append("unknown top-level key(s): %s" % ', '.join(sorted(unknown)))
    tenant = doc.get('tenant')
    if not isinstance(tenant, dict) or not tenant.get('tenant_id'):
        problems.append("tenant.tenant_id is missing")
    elif 'description' in tenant:
        problems += _check('tenant', tenant)
    for section in _SECTIONS:
        entries = doc.get(section) or {}
        if not isinstance(entries, dict):
            problems.append("%s is not a mapping" % section)
            continue
        for key, entry in entries.items():
            where = "%s.%s" % (section, key)
            if not isinstance(entry, dict) or 'description' not in entry:
                problems.append("%s: no description key" % where)
            else:
                problems += _check(where, entry)
    if problems:
        raise DescriptionsError("; ".join(problems))


def _check(where, entry):
    text = entry['description']
    if text is not None and not isinstance(text, str):
        return ["%s: description is not text" % where]
    if text and len(text) > MAX_LENGTH:
        return ["%s: description is %d characters, over %d" % (where, len(text), MAX_LENGTH)]
    return []


def _norm(text):
    """None and "" both mean no description."""
    return text or ''


def _live(cc, doc):
    """[(section, key, live object or None, file entry)] for the tenant and each listed entry;
    raises DescriptionsError for ids the tenant doesn't have."""
    rows, missing = [], []
    if 'description' in doc['tenant']:
        rows.append(('tenant', doc['tenant']['tenant_id'], cc.get_tenant(), doc['tenant']))
    for section, get in (('applications', cc.get_application), ('subjects', cc.get_subject)):
        for key, entry in (doc.get(section) or {}).items():
            try:
                rows.append((section, key, get(key), entry))
            except ClientError as e:
                if getattr(e, 'status_code', None) != 404:
                    raise
                missing.append("%s.%s" % (section, key))
    if missing:
        raise DescriptionsError("not found in tenant %s: %s" % (doc['tenant']['tenant_id'], ', '.join(missing)))
    return rows


def _check_tenant(cc, doc):
    tenant_id = doc['tenant']['tenant_id']
    if cc.tenant.tenant_id != tenant_id:
        raise DescriptionsError("the file is for tenant %s; the connection is for %s" % (tenant_id, cc.tenant.tenant_id))


def plan(cc, doc):
    """Compare a descriptions file with the live tenant. Returns
    {"tenant_id", "changes": [{section, id, live, file}], "name_changes": [...], "unchanged": n}.
    name_changes are reported only: names in the file are never applied."""
    _check_tenant(cc, doc)
    changes, names, unchanged = [], [], 0
    for section, key, obj, entry in _live(cc, doc):
        live = getattr(obj, 'description', None)  # an unset field is absent from the record
        if _norm(live) != _norm(entry['description']):
            changes.append({'section': section, 'id': key, 'live': _norm(live), 'file': _norm(entry['description'])})
        else:
            unchanged += 1
        if 'name' in entry and entry['name'] != getattr(obj, 'name', None):
            names.append({'section': section, 'id': key, 'live': getattr(obj, 'name', None), 'file': entry['name']})
    return {'tenant_id': doc['tenant']['tenant_id'], 'changes': changes, 'name_changes': names, 'unchanged': unchanged}


def apply(cc, doc, result=None):
    """Write the descriptions that differ from the live tenant (from plan(), or `result` of an earlier
    plan of the same file). Returns the list of changes written."""
    result = result or plan(cc, doc)
    for change in result['changes']:
        body = {'description': change['file']}
        if change['section'] == 'tenant':
            cc._post("/1/tenants/%s" % change['id'], json=body)
        elif change['section'] == 'applications':
            cc.get_application(change['id']).update(body)
        else:
            cc.get_subject(change['id']).update(body)
    return result['changes']


def export(cc, application_ids=None, doc=None):
    """The live descriptions as a descriptions file dict: the tenant and, by default, every application
    and subject; with application_ids, only those applications and their input and output subjects; with
    doc (an existing file), the entries it lists, and the tenant's description only if it lists that."""
    tenant = cc.tenant
    if doc is not None:
        _check_tenant(cc, doc)
        apps = {key: cc.get_application(key) for key in (doc.get('applications') or {})}
        subjects = {key: cc.get_subject(key) for key in (doc.get('subjects') or {})}
    elif application_ids:
        apps = {key: cc.get_application(key) for key in application_ids}
        uids = sorted({uid for app in apps.values()
                       for uid in (app.input_subjects or []) + (app.output_subjects or [])})
        subjects = {uid: cc.get_subject(uid) for uid in uids}
    else:
        apps = {app.application_id: app for app in cc.get_all_applications()}
        subjects = {s.subject_uid: s for s in cc.get_all_subjects()}
    entry = lambda obj: {'name': getattr(obj, 'name', None), 'description': _norm(getattr(obj, 'description', None))}
    tenant_entry = {'tenant_id': tenant.tenant_id, **entry(tenant)}
    if doc is not None and 'description' not in doc['tenant']:  # a refresh doesn't start managing the tenant
        del tenant_entry['description']
    return {'tenant': tenant_entry,
            'applications': {key: entry(apps[key]) for key in sorted(apps)},
            'subjects': {key: entry(subjects[key]) for key in sorted(subjects)}}


class _Dumper(yaml.SafeDumper):
    pass


_Dumper.add_representer(str, lambda dumper, text: dumper.represent_scalar(
    'tag:yaml.org,2002:str', text, style='|' if '\n' in text else None))


def dump(doc):
    """A descriptions file dict as YAML, with multi-line descriptions as literal blocks."""
    return yaml.dump(doc, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=1000)
