"""
Cogniac CLI - Agent-friendly command-line interface to the Cogniac API.

Outputs JSON by default (--format table for human-readable). Errors are JSON on
stderr; exit code 1 for runtime errors, 2 for usage errors.

The command surface is nested, noun-first / verb-last:

    cogniac <noun> [<sub-noun> ...] <verb> [--<resource>-id ID] [options]

Resource ids are passed as --<resource>-id flags (--application-id, --subject-uid,
--media-id, --edgeflow-id, ...). For backward compatibility each id may also be
given as a positional argument (deprecated; the flag is the canonical form).
Plural and synonym spellings of every token are accepted (app/apps/application,
edgeflow/gateway, cert/certificate, ...).

Representative read commands (run `cogniac <noun> --help` to discover the rest):
    cogniac tenant get                         # current tenant (bare `cogniac tenant` works too)
    cogniac tenant list                        # tenants you are authorized for
    cogniac application list
    cogniac application get --application-id ID
    cogniac application leaderboard --application-id ID [--set-assignment ...] [--top N] [--full]
    cogniac subject list
    cogniac subject get --subject-uid UID
    cogniac subject search [--prefix P] [--name N] [--similar S] [--ids ID ...] [--limit L]
    cogniac subject media --subject-uid UID [--limit L] [--consensus C] [--probability-lower P] [--probability-upper P]
    cogniac media get --media-id ID [--download [FILE]]
    cogniac media download --media-id ID [-o OUTPUT]
    cogniac media search [--md5 M] [--filename F] [--external-media-id E] [--domain-unit D] [--limit L]
    cogniac edgeflow list
    cogniac edgeflow get --edgeflow-id ID
    cogniac edgeflow status --edgeflow-id ID [--subsystem S] [--limit L]
    cogniac camera list
    cogniac camera get --network-camera-id ID
    cogniac deployment list
    cogniac deployment get --deployment-group-id ID
    cogniac workflow get --workflow-id ID

Auth commands:
    cogniac auth                               # check credentials (env vars or stored login)
    cogniac auth login [--no-browser]          # browser login; stores a per-user API key
    cogniac auth logout                        # remove the stored login credential

Representative write commands:
    cogniac subject create <name> [--description D] [--external-id E]
    cogniac subject associate --subject-uid UID --media-id ID [--consensus C]
    cogniac media upload <filename> [--subject-uid UID] [--external-media-id E] [--domain-unit D] [--meta-tags T ...]

Global options:
    --format json|table   (default: json)
    --tenant TENANT_ID    (overrides COG_TENANT for this invocation)

Copyright (C) 2016 Cogniac Corporation.
"""

import argparse
import difflib
import json
import re
import sys
import os
from datetime import datetime
from importlib.metadata import version as _pkg_version, PackageNotFoundError

from tabulate import tabulate

from .cogniac import CogniacConnection, DEFAULT_COG_URL_PREFIX
from .credentials import (
    stored_api_key, stored_url_prefix, save_credentials,
    delete_credentials, credentials_path,
)

try:
    __pkg_version__ = _pkg_version("cogniac")
except PackageNotFoundError:
    __pkg_version__ = "unknown"
from .common import CredentialError, ServerError, ClientError, raise_errors

# Attributes set by SDK internals, not from the API response
_INTERNAL_ATTRS = frozenset([
    'session', 'timeout', 'url_prefix', 'ip_address',
])

# Column subsets for table output per resource type
_TABLE_COLUMNS = {
    'tenant':    ['tenant_id', 'name', 'description', 'region'],
    'tenants':   ['tenant_id', 'name', 'roles'],
    'app':       ['application_id', 'name', 'type', 'active', 'description'],
    'subject':   ['subject_uid', 'name', 'description'],
    'media':     ['media_id', 'filename', 'media_format', 'image_width', 'image_height', 'status'],
    'edgeflow':  ['gateway_id', 'name', 'model', 'description'],
    'camera':    ['network_camera_id', 'camera_name', 'url', 'active'],
    'media_assoc': ['media_id', 'subject_uid', 'probability', 'consensus', 'updated_at'],
    'deployment': ['deployment_group_id', 'name', 'target_workflow_id', 'current_workflow_id'],
    'workflow':   ['workflow_id', 'name', 'tenant_id', 'created_at', 'created_by'],
    'leaderboard': ['rank', 'model_id', 'F1', 'precision', 'recall', 'TP', 'FP', 'FN', 'model_image_id'],
    'eval_metric': ['evaluation_metric_hash', 'name', 'primary', 'active', 'weighted', 'user_tag'],
}


# Token-level abbreviation/synonym groups. Each group is a set of
# interchangeable spellings for a single resource-name token. The alias
# generator expands a canonical (possibly compound) resource name into every
# spelling reachable by (a) swapping singular<->plural on each token and
# (b) substituting any synonym within a group.
_SYNONYM_GROUPS = [
    {'application', 'applications', 'app', 'apps'},
    {'edgeflow', 'edgeflows', 'gateway', 'gateways'},
    {'certificate', 'cert'},
    {'evaluation', 'eval'},
    {'performance', 'perf'},
    {'metrics', 'metric'},
    {'subject', 'subjects'},
    {'camera', 'cameras'},
    {'deployment', 'deployments'},
    {'workflow', 'workflows'},
    {'version', 'versions'},
    {'capacity', 'capacities'},
    {'tenant', 'tenants'},
    {'meraki', 'meraki'},
    {'key', 'keys'},
    {'import', 'imports'},
    {'type', 'types'},
    {'model', 'models'},
    {'build', 'builds'},
    {'label', 'labels'},
    {'feedback', 'feedback'},
    {'embeddings', 'embeddings'},
    {'user', 'users'},
    {'event', 'events'},
    {'detection', 'detections', 'assertion', 'assertions'},
    {'media', 'media'},  # uncountable: no plural variant
]


def _token_variants(token):
    """Return the set of interchangeable spellings for a single token."""
    for group in _SYNONYM_GROUPS:
        if token in group:
            return set(group)
    # default: offer naive singular/plural toggling
    variants = {token}
    if token.endswith('s'):
        variants.add(token[:-1])
    else:
        variants.add(token + 's')
    return variants


def resource_aliases(canonical):
    """Generate all sing/plur + abbreviation/synonym aliases for a (possibly
    hyphen-compound) canonical resource name.

    e.g. resource_aliases('edgeflow-certificate') yields edgeflow-cert,
    gateway-certificate, gateway-cert, edgeflows-cert, ... The canonical name
    itself is excluded from the returned alias list (argparse takes it as the
    primary name and aliases= for the rest)."""
    tokens = canonical.split('-')
    combos = ['']
    for tok in tokens:
        new = []
        for prefix in combos:
            for var in sorted(_token_variants(tok)):
                new.append(var if not prefix else prefix + '-' + var)
        combos = new
    return sorted(set(combos) - {canonical})


def obj_to_dict(obj):
    """Convert a Cogniac entity object to a JSON-serializable dict."""
    d = {}
    for k, v in obj.__dict__.items():
        if k.startswith('_'):
            continue
        if k in _INTERNAL_ATTRS:
            continue
        # Handle nested objects that have __dict__ but aren't plain dicts
        if hasattr(v, '__dict__') and not isinstance(v, dict):
            v = obj_to_dict(v)
        d[k] = v
    return d


def output(data, args, table_type=None):
    """Emit data on stdout as JSON (default), JSON Lines (`--format jsonl`), or a
    table (`--format table`, when a table type is known).

    When a list result is capped by `--limit`, a one-line truncation notice is
    written to **stderr** (stdout stays a clean array / JSONL stream) so an agent
    knows more may exist."""
    fmt = getattr(args, 'format', 'json')
    limit = getattr(args, 'limit', None)
    if isinstance(data, list) and limit and len(data) >= limit:
        sys.stderr.write(json.dumps({
            "truncated": True,
            "count": len(data),
            "hint": "results capped by --limit %d; raise --limit or use --cursor to fetch more" % limit,
        }) + "\n")
    if fmt == 'jsonl':
        if isinstance(data, list):
            for item in data:
                print(json.dumps(item, default=str))
        else:
            print(json.dumps(data, default=str))
    elif fmt == 'table' and table_type:
        _output_table(data, table_type)
    else:
        print(json.dumps(data, indent=2, default=str))


def _output_table(data, table_type):
    """Print data as a formatted table."""
    cols = _TABLE_COLUMNS.get(table_type)
    if not cols:
        # fallback to json
        print(json.dumps(data, indent=2, default=str))
        return

    if isinstance(data, dict):
        rows = [data]
    elif isinstance(data, list):
        rows = data
    else:
        print(json.dumps(data, indent=2, default=str))
        return

    table_rows = []
    for row in rows:
        table_rows.append([_truncate(str(row.get(c, '')), 60) for c in cols])

    print(tabulate(table_rows, headers=cols, tablefmt='simple'))


def _truncate(s, maxlen):
    return s if len(s) <= maxlen else s[:maxlen - 3] + '...'


# error_exit's string label -> structured envelope "type"
_ERROR_TYPES = {
    'CredentialError': 'auth',
    'AuthError': 'auth',
    'LoginError': 'auth',
    'LoginCancelled': 'auth',
    'ClientError': 'client',
    'BadRequest': 'client',
    'UsageError': 'client',
    'ServerError': 'server',
    'ConnectionError': 'connection',
}
_ERROR_HINTS = {
    'auth': "check COG_API_KEY / COG_USER+COG_PASS, or run 'cogniac auth login'",
    'connection': "check network connectivity and COG_URL_PREFIX",
    'server': "transient server error; retry shortly",
}


def error_exit(error_type, detail, exit_code=1):
    """Print a structured JSON error envelope to stderr and exit.

    Envelope: ``{"error": {"type", "status", "message", "hint"}}`` — agents
    branch on ``type``; ``status`` is the HTTP status when known; ``message`` is
    the server's message (un-nested from the wrapper text, and from the server's
    JSON body when it sent one, rather than double-encoded); ``hint`` is a
    self-heal suggestion when one applies."""
    etype = _ERROR_TYPES.get(error_type, 'error')
    detail = detail or ''
    status = None
    m = re.search(r'\((\d{3})\)', detail)
    if m:
        status = int(m.group(1))
    message = detail
    # un-nest the server's JSON body if present so it isn't double-encoded
    jm = re.search(r'(\{.*\}|\[.*\])\s*$', detail, re.S)
    if jm:
        try:
            body = json.loads(jm.group(1))
            if isinstance(body, dict):
                message = body.get('message') or body.get('detail') or body.get('error') or message
        except ValueError:
            pass
    hint = _ERROR_HINTS.get(etype)
    if status == 429:
        etype, hint = 'rate_limit', "rate-limited; retry after a short backoff"
    env = {"type": etype}
    if status is not None:
        env["status"] = status
    env["message"] = message
    if hint:
        env["hint"] = hint
    sys.stderr.write(json.dumps({"error": env}) + "\n")
    sys.exit(exit_code)


def get_connection(args=None):
    """Create an authenticated CogniacConnection, or exit with JSON error.

    If args has a non-empty `tenant` attribute, it overrides COG_TENANT.
    """
    tenant_id = getattr(args, 'tenant', None) if args is not None else None
    try:
        if tenant_id:
            return CogniacConnection(tenant_id=tenant_id)
        return CogniacConnection()
    except CredentialError as e:
        error_exit("CredentialError", str(e))
    except Exception as e:
        error_exit("ConnectionError", str(e))


# -- Read command handlers --

def cmd_tenant(args):
    cc = get_connection(args)
    output(obj_to_dict(cc.tenant), args, 'tenant')


def cmd_tenant_accounting_get(args):
    cc = get_connection(args)
    output({"accounting": getattr(cc.tenant, "accounting", None)}, args)


def cmd_tenant_accounting_set(args):
    cc = get_connection(args)
    cc.tenant.accounting = args.value
    output({"accounting": cc.tenant.accounting}, args)


def cmd_tenants(args):
    url_prefix = os.environ.get('COG_URL_PREFIX') or stored_url_prefix() or DEFAULT_COG_URL_PREFIX
    try:
        result = CogniacConnection.get_all_authorized_tenants(url_prefix=url_prefix)
        fmt = getattr(args, 'format', 'json')
        if fmt == 'table':
            output(result.get('tenants', []), args, 'tenants')
        else:
            output(result, args)
    except CredentialError as e:
        error_exit("CredentialError", str(e))
    except Exception as e:
        error_exit("Error", str(e))


def cmd_apps_list(args):
    cc = get_connection(args)
    apps = cc.get_all_applications()
    output([obj_to_dict(a) for a in apps], args, 'app')


def cmd_apps_get(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(obj_to_dict(app), args, 'app')
    except ClientError as e:
        error_exit("ClientError", str(e))


def _round_metric(v):
    """Round metric floats to 4 decimals for display; pass through non-floats."""
    return round(v, 4) if isinstance(v, float) else v


def _strip_subj_results(snapshot):
    """Return a deep-ish copy of snapshot entries with per-subject breakdowns dropped."""
    brief = []
    for entry in snapshot:
        e = dict(entry)
        results = e.get('results')
        if isinstance(results, dict):
            new_results = {}
            for h, v in results.items():
                if isinstance(v, dict) and isinstance(v.get('result'), dict):
                    inner = {k: val for k, val in v['result'].items() if k != 'subj_results'}
                    new_results[h] = {**v, 'result': inner}
                else:
                    new_results[h] = v
            e['results'] = new_results
        brief.append(e)
    return brief


def cmd_apps_leaderboard(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        result = app.leaderboard(
            set_assignment=args.set_assignment,
            snapshot_type=args.snapshot_type,
            eval_metrics=args.eval_metrics,
        )
        fmt = getattr(args, 'format', 'json')
        snapshot = result.get('snapshot') if isinstance(result, dict) else None
        primary_hash = result.get('primary_evaluation_metric_hash') if isinstance(result, dict) else None
        top = getattr(args, 'top', None)

        if fmt == 'table':
            if not snapshot:
                # 202 / not-yet-available — fall back to JSON so the message is visible
                print(json.dumps(result, indent=2, default=str))
                return
            rows = []
            for entry in snapshot:
                app_res = (entry.get('results', {})
                                .get(primary_hash, {})
                                .get('result', {})
                                .get('app_results', {})) if primary_hash else {}
                rows.append({
                    'rank': entry.get('primary_metric_rank', ''),
                    'model_id': entry.get('model_id', ''),
                    'F1': _round_metric(app_res.get('F1', '')),
                    'precision': _round_metric(app_res.get('precision', '')),
                    'recall': _round_metric(app_res.get('recall', '')),
                    'TP': app_res.get('TP', ''),
                    'FP': app_res.get('FP', ''),
                    'FN': app_res.get('FN', ''),
                    'model_image_id': entry.get('model_image_id', ''),
                })
            if top:
                rows = rows[:top]
            output(rows, args, 'leaderboard')
            return

        # JSON output: brief by default, --full for raw
        if not args.full and snapshot:
            brief = dict(result)
            brief['snapshot'] = _strip_subj_results(snapshot)
            if top:
                brief['snapshot'] = brief['snapshot'][:top]
            output(brief, args)
        else:
            if top and snapshot:
                result = dict(result)
                result['snapshot'] = snapshot[:top]
            output(result, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_apps_eval_metrics_list(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        metrics = app.evaluation_metrics()
        items = metrics.get('data', metrics) if isinstance(metrics, dict) else metrics
        fmt = getattr(args, 'format', 'json')
        if fmt == 'table' and isinstance(items, list):
            rows = []
            for m in items:
                em = m.get('evaluation_metric', {}) if isinstance(m, dict) else {}
                weights = em.get('subject_weights') or {}
                weighted = bool(weights) and len(set(weights.values())) > 1
                rows.append({
                    'evaluation_metric_hash': m.get('evaluation_metric_hash', ''),
                    'name': em.get('name', ''),
                    'primary': m.get('primary', ''),
                    'active': m.get('active', ''),
                    'weighted': weighted,
                    'user_tag': m.get('user_tag', ''),
                })
            output(rows, args, 'eval_metric')
        else:
            output(items, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_subjects_list(args):
    cc = get_connection(args)
    subjects = cc.get_all_subjects()
    output([obj_to_dict(s) for s in subjects], args, 'subject')


def cmd_subjects_get(args):
    cc = get_connection(args)
    try:
        subject = cc.get_subject(args.subject_uid)
        output(obj_to_dict(subject), args, 'subject')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_subjects_search(args):
    cc = get_connection(args)
    ids = args.ids if args.ids else []
    subjects = cc.search_subjects(
        ids=ids,
        prefix=args.prefix,
        similar=args.similar,
        name=args.name,
        limit=args.limit,
    )
    output([obj_to_dict(s) for s in subjects], args, 'subject')


def cmd_subjects_media(args):
    cc = get_connection(args)
    try:
        subject = cc.get_subject(args.subject_uid)
        associations = subject.media_associations(
            probability_lower=args.probability_lower,
            probability_upper=args.probability_upper,
            consensus=args.consensus,
            reverse=getattr(args, 'reverse', True),
            limit=args.limit,
            abridged_media=not getattr(args, 'full_media', False),
        )
        results = list(associations)
        fmt = getattr(args, 'format', 'json')
        if fmt == 'table':
            # flatten for table display
            flat = []
            for a in results:
                s = a.get('subject', {})
                flat.append({
                    'media_id': s.get('media_id', ''),
                    'subject_uid': s.get('subject_uid', ''),
                    'probability': s.get('probability', ''),
                    'consensus': s.get('consensus', ''),
                    'updated_at': s.get('updated_at', ''),
                })
            output(flat, args, 'media_assoc')
        else:
            output(results, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_media_get(args):
    cc = get_connection(args)
    try:
        media = cc.get_media(args.media_id)
        if args.download:
            # --download flag: behave like 'cogniac media download'
            args.output = args.download if args.download is not True else None
            args.media_id = media.media_id
            return cmd_media_download(args, media=media)
        output(obj_to_dict(media), args, 'media')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_media_download(args, media=None):
    cc = get_connection(args)
    try:
        if media is None:
            media = cc.get_media(args.media_id)
        ext = (media.media_format or 'bin').lower()
        if ext == 'jpeg':
            ext = 'jpg'
        output_path = args.output or f"{args.media_id}.{ext}"
        with open(output_path, 'wb') as f:
            media.download(f)
        print(json.dumps({"media_id": args.media_id, "file": output_path, "size": os.path.getsize(output_path)}))
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_media_search(args):
    cc = get_connection(args)
    results = cc.search_media(
        md5=args.md5,
        filename=args.filename,
        external_media_id=args.external_media_id,
        domain_unit=args.domain_unit,
        limit=args.limit,
    )
    output([obj_to_dict(m) for m in results], args, 'media')


def cmd_edgeflows_list(args):
    cc = get_connection(args)
    edgeflows = cc.get_all_edgeflows()
    output([obj_to_dict(e) for e in edgeflows], args, 'edgeflow')


def cmd_edgeflows_get(args):
    cc = get_connection(args)
    try:
        edgeflow = cc.get_edgeflow(args.edgeflow_id)
        output(obj_to_dict(edgeflow), args, 'edgeflow')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_edgeflows_status(args):
    cc = get_connection(args)
    try:
        edgeflow = cc.get_edgeflow(args.edgeflow_id)
        if getattr(args, 'list_subsystems', False):
            _emit_subsystem_summary(edgeflow, args)
            return
        events = edgeflow.status(
            subsystem_name=args.subsystem,
            limit=args.limit,
        )
        output([e for e in events], args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def _emit_subsystem_summary(edgeflow, args):
    """Discovery aid for `edgeflows status --list-subsystems`.

    High-frequency subsystems (e.g. per-model detection counters) crowd the
    most-recent-N events, so low-frequency subsystems (gpus/cpu/memory/upload/
    http-input-* etc.) never surface at a small --limit. This scans a bounded
    window of device history once and aggregates the distinct `subsystem`
    values, with each one's latest timestamp and how many times it appeared in
    the scanned window — independent of per-subsystem sample frequency.

    stdout stays a clean JSON array; if the scan hits --scan-limit (so a rarer
    subsystem may still be missed), a diagnostic notice goes to stderr, per the
    CLI's stdout/stderr contract."""
    scan_limit = getattr(args, 'scan_limit', None) or 2000
    summary = {}
    scanned = 0
    for event in edgeflow.status(limit=scan_limit):
        scanned += 1
        subsystem = event.get('subsystem')
        if not subsystem:
            continue
        ts = event.get('edgeflow_timestamp')
        entry = summary.get(subsystem)
        if entry is None:
            summary[subsystem] = {'subsystem': subsystem, 'last_seen': ts, 'count': 1}
        else:
            entry['count'] += 1
            if ts is not None and (entry['last_seen'] is None or ts > entry['last_seen']):
                entry['last_seen'] = ts
    result = sorted(summary.values(), key=lambda d: d['subsystem'])
    if scanned >= scan_limit:
        sys.stderr.write(json.dumps({
            "scan_capped": True,
            "scanned": scanned,
            "hint": "subsystem scan hit --scan-limit %d; a rarely-reported subsystem "
                    "may be missing. Raise --scan-limit to widen the scan." % scan_limit,
        }) + "\n")
    # The result is bounded by --scan-limit, not --limit; suppress output()'s
    # --limit truncation notice (which would otherwise misfire on the distinct
    # subsystem count) by clearing limit for this emit.
    args.limit = None
    output(result, args)


def cmd_cameras_list(args):
    cc = get_connection(args)
    cameras = cc.get_all_cameras()
    output([obj_to_dict(c) for c in cameras], args, 'camera')


def cmd_cameras_get(args):
    cc = get_connection(args)
    try:
        camera = cc.get_camera(args.network_camera_id)
        output(obj_to_dict(camera), args, 'camera')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_deployments_list(args):
    cc = get_connection(args)
    from .deployment import CogniacDeployment
    try:
        groups = CogniacDeployment.get_all(cc)
        output([obj_to_dict(g) for g in groups], args, 'deployment')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_deployments_get(args):
    cc = get_connection(args)
    from .deployment import CogniacDeployment
    try:
        dg = CogniacDeployment.get(cc, args.deployment_group_id)
        output(obj_to_dict(dg), args, 'deployment')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_workflows_get(args):
    cc = get_connection(args)
    from .workflow import CogniacWorkflow
    try:
        wf = CogniacWorkflow.get(cc, args.workflow_id)
        output(obj_to_dict(wf), args, 'workflow')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_auth(args):
    """Check credentials. If a tenant is specified (via --tenant or COG_TENANT),
    also verify that a real session can be minted against it via /1/token."""
    has_api_key = 'COG_API_KEY' in os.environ
    has_user_pass = 'COG_USER' in os.environ and 'COG_PASS' in os.environ
    has_stored = stored_api_key() is not None
    flag_tenant = getattr(args, 'tenant', None)
    env_tenant = os.environ.get('COG_TENANT')
    effective_tenant = flag_tenant or env_tenant

    if not has_api_key and not has_user_pass and not has_stored:
        error_exit("AuthError", "No credentials found. Run `cogniac auth login`, or set COG_API_KEY or COG_USER+COG_PASS environment variables.")

    if has_api_key:
        auth_method = "api_key"
    elif has_user_pass:
        auth_method = "user_pass"
    else:
        auth_method = "stored_login"

    result = {
        "auth_method": auth_method,
        "tenant_set": effective_tenant is not None,
    }
    if auth_method == "stored_login":
        result["credentials_path"] = credentials_path()

    if effective_tenant:
        result["tenant_id"] = effective_tenant
        result["tenant_source"] = "flag" if flag_tenant else "env"

    url_prefix = os.environ.get('COG_URL_PREFIX') or stored_url_prefix() or DEFAULT_COG_URL_PREFIX
    result["url_prefix"] = url_prefix
    try:
        tenants = CogniacConnection.get_all_authorized_tenants(url_prefix=url_prefix)
        result["tenant_count"] = len(tenants.get('tenants', []))
    except Exception as e:
        result["valid"] = False
        result["detail"] = str(e)
        output(result, args)
        return

    if effective_tenant:
        try:
            CogniacConnection(tenant_id=effective_tenant, url_prefix=url_prefix)
            result["valid"] = True
        except Exception as e:
            result["valid"] = False
            result["detail"] = str(e)
    else:
        result["valid"] = True
        result["note"] = (
            "Credentials valid. List tenants with `cogniac tenants`, then pass "
            "--tenant <id> (or set COG_TENANT) to work with the specified tenant."
        )

    output(result, args)


def cmd_auth_login(args):
    """Authenticate via the browser (loopback redirect) and store a per-user
    API key at ~/.config/cogniac/credentials so future invocations need no
    environment setup."""
    import datetime
    import socket
    from .auth_login import login

    url_prefix = os.environ.get('COG_URL_PREFIX') or stored_url_prefix() or DEFAULT_COG_URL_PREFIX
    try:
        api_key, url_prefix = login(url_prefix, open_browser=not getattr(args, 'no_browser', False))
    except KeyboardInterrupt:
        error_exit("LoginCancelled", "Login cancelled.")
    except Exception as e:
        error_exit("LoginError", str(e))

    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = None
    label = "cogniac CLI %s %s" % (hostname or "", datetime.date.today().isoformat())
    path = save_credentials(api_key, url_prefix=url_prefix,
                            label=label.strip(),
                            hostname=hostname,
                            created_at=datetime.datetime.now().isoformat(timespec='seconds'))

    result = {"status": "logged_in", "credentials_path": path, "url_prefix": url_prefix}
    # Best-effort verification that the freshly-minted key works; report identity if so.
    try:
        import httpx
        resp = httpx.get(url_prefix + "/1/users/current/tenants",
                         headers={"Authorization": "Key %s" % api_key}, timeout=30,
                         follow_redirects=True)
        raise_errors(resp)
        result["tenant_count"] = len(resp.json().get('tenants', []))
        result["verified"] = True
    except Exception as e:
        result["verified"] = False
        result["detail"] = str(e)
    output(result, args)


def cmd_auth_logout(args):
    """Remove the stored login credential."""
    removed = delete_credentials()
    result = {
        "status": "logged_out" if removed else "not_logged_in",
        "credentials_path": credentials_path(),
        "removed": removed,
    }
    output(result, args)


def cmd_user(args):
    """Show current user info including system roles."""
    cc = get_connection(args)
    resp = cc.session.get(cc.url_prefix + '/1/users/current')
    resp.raise_for_status()
    output(resp.json(), args, 'user')


# -- Write command handlers --

def cmd_subjects_create(args):
    cc = get_connection(args)
    try:
        subject = cc.create_subject(
            name=args.name,
            description=args.description,
            external_id=args.external_id,
        )
        output(obj_to_dict(subject), args, 'subject')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_subjects_associate(args):
    cc = get_connection(args)
    try:
        subject = cc.get_subject(args.subject_uid)
        result = subject.associate_media(
            media=args.media_id,
            consensus=args.consensus,
        )
        output(result, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_media_upload(args):
    cc = get_connection(args)
    try:
        media = cc.create_media(
            filename=args.filename,
            external_media_id=args.external_media_id,
            domain_unit=args.domain_unit,
            meta_tags=args.meta_tags,
        )
        # If a subject was specified, associate the media with it
        if args.subject_uid:
            subject = cc.get_subject(args.subject_uid)
            subject.associate_media(media=media.media_id)
        output(obj_to_dict(media), args, 'media')
    except ClientError as e:
        error_exit("ClientError", str(e))


# -- New read/action command handlers --

def _json_body(args):
    """Parse the optional --body JSON flag into a dict (or None)."""
    raw = getattr(args, 'body', None)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError) as e:
        error_exit("BadRequest", "Invalid --body JSON: %s" % e)


# ---- per-field update flags --------------------------------------------------
#
# `<resource> update` accepts both a whole-object `--body JSON` and per-field
# flags for that resource's mutable fields. The flags are convenient for simple
# edits; `--body` is the escape hatch for the full object. Supplied flags are
# layered on top of `--body` (flags win on key collisions). A field flag left
# unset (value None) is omitted entirely, so an update only touches the fields
# the caller named.

def _bool_value(s):
    """argparse type: parse a true/false flag value (tri-state via default None)."""
    v = str(s).strip().lower()
    if v in ('true', '1', 'yes', 'y', 'on'):
        return True
    if v in ('false', '0', 'no', 'n', 'off'):
        return False
    raise argparse.ArgumentTypeError("expected true/false, got %r" % s)


def _json_value(s):
    """argparse type: parse a JSON-valued flag (object/array/scalar)."""
    try:
        return json.loads(s)
    except (ValueError, TypeError) as e:
        raise argparse.ArgumentTypeError("invalid JSON: %s" % e)


# (flag, dest/body-key, kind). kind drives both the argparse type and how the
# value is read back when assembling the request body.
_UPDATE_FIELDS = {
    'application': [
        ('--name', 'name', 'str'),
        ('--description', 'description', 'str'),
        ('--active', 'active', 'bool'),
        ('--input-subjects', 'input_subjects', 'strlist'),
        ('--output-subjects', 'output_subjects', 'strlist'),
        ('--app-managers', 'app_managers', 'strlist'),
        ('--detection-post-urls', 'detection_post_urls', 'json'),
        ('--detection-thresholds', 'detection_thresholds', 'json'),
        ('--subject-weights', 'subject_weights', 'json'),
        ('--custom-fields', 'custom_fields', 'json'),
        ('--app-type-config', 'app_type_config', 'json'),
        ('--edgeflow-upload-policies', 'edgeflow_upload_policies', 'json'),
        ('--override-upstream-detection-filter', 'override_upstream_detection_filter', 'bool'),
        ('--feedback-resample-ratio', 'feedback_resample_ratio', 'float'),
        ('--reviewers', 'reviewers', 'json'),
        ('--inference-execution-policies', 'inference_execution_policies', 'json'),
    ],
    'subject': [
        ('--name', 'name', 'str'),
        ('--description', 'description', 'str'),
        ('--expires-in', 'expires_in', 'float'),
        ('--external-id', 'external_id', 'str'),
        ('--custom-data', 'custom_data', 'json'),
    ],
    'media': [
        ('--set-assignment', 'set_assignment', 'str'),
        ('--force-set', 'force_set', 'bool'),
        ('--meta-tags', 'meta_tags', 'strlist'),
        ('--custom-data', 'custom_data', 'json'),
    ],
    'camera': [
        ('--url', 'url', 'str'),
        ('--current-ip', 'current_IP', 'str'),
        ('--camera-name', 'camera_name', 'str'),
        ('--description', 'description', 'str'),
        ('--active', 'active', 'bool'),
        ('--lat', 'lat', 'float'),
        ('--lon', 'lon', 'float'),
        ('--hae', 'hae', 'float'),
        ('--alt-subject-uid', 'alt_subject_uid', 'str'),
        ('--custom-configuration', 'custom_configuration', 'json'),
    ],
}

_FIELD_TYPES = {'str': str, 'int': int, 'float': float, 'bool': _bool_value, 'json': _json_value}


def _update_arg_specs(resource):
    """Build argparse arg-specs for a resource's per-field update flags."""
    specs = []
    for flag, dest, kind in _UPDATE_FIELDS[resource]:
        kw = {'dest': dest, 'default': None, 'help': 'Set %s' % dest}
        if kind == 'strlist':
            kw['nargs'] = '+'
        else:
            kw['type'] = _FIELD_TYPES[kind]
        specs.append(((flag,), kw))
    return specs


def _assemble_update_body(args, resource):
    """Merge --body JSON with any per-field update flags (flags win)."""
    body = dict(_json_body(args) or {})
    for _flag, dest, _kind in _UPDATE_FIELDS[resource]:
        val = getattr(args, dest, None)
        if val is not None:
            body[dest] = val
    return body


# ---- application (extended) ----

def cmd_app_evaluation_metrics(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.evaluation_metrics(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_classify(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.classify(args.image_file), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_donate_model(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.donate_model(args.source_application_id), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_model_export(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        # --target is a required choice; today only 'meraki' is supported,
        # additional targets can be wired here as they are added.
        if args.target == 'meraki':
            result = app.export_model_to_meraki()
        else:
            error_exit("UsageError", "unsupported export target: %s" % args.target)
            return
        output(result, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_replay_status(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.replay_status(timeout=getattr(args, 'timeout', None)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_replay_start(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.replay_start(body=_json_body(args)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_replay_stop(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.replay_stop(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_detections_pending(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.detections_pending(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_event_types(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.event_types(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_events(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        results = list(app.events(start=args.start, end=args.end, limit=args.limit,
                                  cursor=args.cursor, reverse=args.reverse,
                                  event_types=args.event_types))
        output(results, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_consensus_history(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.consensus_history(start=args.start, end=args.end, limit=args.limit,
                                     subject_uid=args.subject_uid), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_performance_current(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.performance_current_validation(start=args.start, end=args.end, limit=args.limit,
                                                  reverse=args.reverse, duration=args.duration), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_performance_release(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.performance_release_validation(start=args.start, end=args.end, limit=args.limit,
                                                  reverse=args.reverse, duration=args.duration), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_performance_new_random(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.performance_new_random(limit=args.limit), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_push(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.push_notifications(device_id=args.device_id,
                                      app_bundle_id=args.app_bundle_id,
                                      event_type=args.event_type), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_push_subscribe(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.subscribe_push(device_id=args.device_id, app_bundle_id=args.app_bundle_id,
                                 event_type=args.event_type, unsubscribe=args.unsubscribe), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_consensus_releases(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.consensus_releases(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_consensus_release(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.consensus_release(args.release_id), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_consensus_release_items(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(list(app.consensus_release_items(args.release_id, limit=args.limit, cursor=args.cursor)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_consensus_release_upstream(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(list(app.consensus_release_upstream_assertions(args.release_id, limit=args.limit, cursor=args.cursor)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_consensus_detection_releases(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.consensus_detection_release(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_eval_metrics_create(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.create_evaluation_metric(_json_body(args) or {}), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_eval_metrics_register_default(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.register_default_evaluation_metric(_json_body(args)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_eval_metrics_copy(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.source_application_id)
        output(app.copy_evaluation_metrics(args.target_application_id), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- application-types ----

def cmd_app_types_list(args):
    cc = get_connection(args)
    from .app import CogniacApplication
    output(CogniacApplication.get_all_types(
        cc,
        production=True if getattr(args, 'production', False) else None,
        deprecated=True if getattr(args, 'deprecated', False) else None,
        reverse=getattr(args, 'reverse', False)), args)


def cmd_app_types_get(args):
    cc = get_connection(args)
    from .app import CogniacApplication
    try:
        output(CogniacApplication.get_type(cc, args.application_type), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- application-feedback ----

def cmd_app_feedback_list(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(list(app.feedback(limit=args.limit, cursor=getattr(args, 'cursor', None))), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_feedback_get(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.feedback_request(args.feedback_id), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_feedback_create(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.submit_feedback(_json_body(args) or {}), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_feedback_count(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.feedback_request_count(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_feedback_pending(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        # default to a full page rather than the SDK's limit=1
        limit = getattr(args, 'limit', None) or 100
        output(app.pending_feedback_requests(limit=limit), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_feedback_purge(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        app.purge_feedback()
        output({"application_id": args.application_id, "status": "purged"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_feedback_purge_requests(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.delete_feedback_requests() or {"application_id": args.application_id, "status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- application-model ----

def cmd_app_model_performance(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.model_performance(subject_uid=args.subject_uid, consensus=args.consensus,
                                    reverse=args.reverse, probability_lower=args.probability_lower,
                                    probability_upper=args.probability_upper, limit=args.limit,
                                    cursor=args.cursor, set_assignment=args.set_assignment), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- application-build ----

def cmd_build_list(args):
    cc = get_connection(args)
    from .build import CogniacBuild
    builds = CogniacBuild.get_all(cc, application_id=getattr(args, 'application_id', None))
    output([obj_to_dict(b) for b in builds], args)


def cmd_build_get(args):
    cc = get_connection(args)
    from .build import CogniacBuild
    try:
        output(obj_to_dict(CogniacBuild.get(cc, args.application_build_id)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_build_create(args):
    cc = get_connection(args)
    from .build import CogniacBuild
    try:
        output(obj_to_dict(CogniacBuild.create(cc, _json_body(args) or {})), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_build_delete(args):
    cc = get_connection(args)
    from .build import CogniacBuild
    try:
        b = CogniacBuild.get(cc, args.application_build_id)
        b.delete()
        output({"application_build_id": args.application_build_id, "status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_build_names(args):
    cc = get_connection(args)
    from .build import CogniacBuild
    output(CogniacBuild.names(cc), args)


def cmd_build_lint(args):
    cc = get_connection(args)
    from .build import CogniacBuild
    try:
        output(CogniacBuild.lint(cc, args.filename), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- application-label (labeling embedding models) ----

def cmd_app_label_image_encoder(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.labeling_image_encoder(_json_body(args) or {}), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_label_mask_decoder(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        out_path = getattr(args, 'output', None) or ("%s_mask_decoder.onnx" % args.application_id)
        with open(out_path, 'wb') as f:
            app.labeling_mask_decoder(filep=f)
        output({"application_id": args.application_id, "file": out_path,
                "size": os.path.getsize(out_path)}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_label_mask_decoder_head(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.labeling_mask_decoder_head(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- media-embeddings ----

def cmd_media_embeddings(args):
    cc = get_connection(args)
    try:
        media = cc.get_media(args.media_id)
        focus = getattr(args, 'focus', None)
        if focus is not None:
            focus = json.loads(focus)
        output(media.embeddings(model_id=getattr(args, 'model_id', None), focus=focus), args)
    except ClientError as e:
        error_exit("ClientError", str(e))
    except (ValueError, TypeError) as e:
        error_exit("BadRequest", "Invalid --focus JSON: %s" % e)


# ---- subject (extended) ----

def cmd_subjects_consensus_history(args):
    cc = get_connection(args)
    try:
        subject = cc.get_subject(args.subject_uid)
        output(subject.consensus_history(start=args.start, end=args.end, limit=args.limit), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_subjects_detections(args):
    cc = get_connection(args)
    try:
        subject = cc.get_subject(args.subject_uid)
        output(subject.detections(args.media_id), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- media (extended) ----

def cmd_media_share(args):
    cc = get_connection(args)
    try:
        media = cc.get_media(args.media_id)
        output(media.share(body=_json_body(args)) or {"media_id": args.media_id, "status": "shared"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_media_create_detection(args):
    cc = get_connection(args)
    try:
        media = cc.get_media(args.media_id)
        output(media.create_detection(body=_json_body(args)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- edgeflow (extended) ----

def cmd_edgeflows_create(args):
    cc = get_connection(args)
    try:
        from .edgeflow import CogniacEdgeFlow
        ef = CogniacEdgeFlow.create(cc, body=_json_body(args))
        output(obj_to_dict(ef), args, 'edgeflow')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_edgeflows_delete(args):
    cc = get_connection(args)
    try:
        ef = cc.get_edgeflow(args.edgeflow_id)
        ef.delete()
        output({"edgeflow_id": args.edgeflow_id, "status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_edgeflow_cert_get(args):
    cc = get_connection(args)
    try:
        ef = cc.get_edgeflow(args.edgeflow_id)
        output(ef.get_certificate(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_edgeflow_cert_set(args):
    cc = get_connection(args)
    try:
        ef = cc.get_edgeflow(args.edgeflow_id)
        output(ef.set_certificate(body=_json_body(args)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_edgeflow_cert_replace(args):
    cc = get_connection(args)
    try:
        ef = cc.get_edgeflow(args.edgeflow_id)
        output(ef.replace_certificate(body=_json_body(args)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_edgeflow_cert_delete(args):
    cc = get_connection(args)
    try:
        ef = cc.get_edgeflow(args.edgeflow_id)
        ef.delete_certificate()
        output({"edgeflow_id": args.edgeflow_id, "status": "certificate deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_edgeflow_metrics_list(args):
    cc = get_connection(args)
    from .edgeflow import CogniacEdgeFlow
    try:
        if getattr(args, 'edgeflow_id', None):
            ef = cc.get_edgeflow(args.edgeflow_id)
            output(ef.metrics(), args)
        else:
            output(CogniacEdgeFlow.all_metrics(cc), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_edgeflow_metric_names(args):
    cc = get_connection(args)
    from .edgeflow import CogniacEdgeFlow
    output(CogniacEdgeFlow.metric_names(cc), args)


# ---- camera (extended) ----

def cmd_cameras_genicam(args):
    cc = get_connection(args)
    try:
        cam = cc.get_camera(args.network_camera_id)
        print(cam.genicam())
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- deployment ----

def cmd_deployments_create(args):
    cc = get_connection(args)
    from .deployment import CogniacDeployment
    try:
        dg = CogniacDeployment.create(cc, body=_json_body(args))
        output(obj_to_dict(dg), args, 'deployment')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_deployments_delete(args):
    cc = get_connection(args)
    from .deployment import CogniacDeployment
    try:
        dg = CogniacDeployment.get(cc, args.deployment_group_id)
        dg.delete()
        output({"deployment_group_id": args.deployment_group_id, "status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_deployments_edgeflows(args):
    cc = get_connection(args)
    from .deployment import CogniacDeployment
    try:
        dg = CogniacDeployment.get(cc, args.deployment_group_id)
        output(dg.edgeflows(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_deployments_history(args):
    cc = get_connection(args)
    from .deployment import CogniacDeployment
    try:
        dg = CogniacDeployment.get(cc, args.deployment_group_id)
        output(list(dg.history(reverse=getattr(args, 'reverse', True),
                               limit=getattr(args, 'limit', None))), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_deployments_prepull_status(args):
    cc = get_connection(args)
    from .deployment import CogniacDeployment
    try:
        dg = CogniacDeployment.get(cc, args.deployment_group_id)
        output(dg.prepull_status(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_deployments_prepull_start(args):
    cc = get_connection(args)
    from .deployment import CogniacDeployment
    try:
        dg = CogniacDeployment.get(cc, args.deployment_group_id)
        output(dg.prepull_start(args.workflow_id), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_deployments_target_workflow(args):
    cc = get_connection(args)
    from .deployment import CogniacDeployment
    try:
        dg = CogniacDeployment.get(cc, args.deployment_group_id)
        output(dg.set_target_workflow(args.workflow_id), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- deployment-capacity ----

def cmd_deployment_capacity_list(args):
    cc = get_connection(args)
    from .deployment import CogniacDeploymentCapacityClass
    classes = CogniacDeploymentCapacityClass.get_all(cc)
    output([obj_to_dict(c) for c in classes], args)


def cmd_deployment_capacity_get(args):
    cc = get_connection(args)
    from .deployment import CogniacDeploymentCapacityClass
    try:
        output(obj_to_dict(CogniacDeploymentCapacityClass.get(cc, args.capacity_class_id)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- workflow ----

def cmd_workflows_list(args):
    cc = get_connection(args)
    from .workflow import CogniacWorkflow
    workflows = CogniacWorkflow.get_all(cc)
    output([obj_to_dict(w) for w in workflows], args, 'workflow')


def cmd_workflows_create(args):
    cc = get_connection(args)
    from .workflow import CogniacWorkflow
    try:
        wf = CogniacWorkflow.create(cc, body=_json_body(args))
        output(obj_to_dict(wf), args, 'workflow')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_workflows_delete(args):
    cc = get_connection(args)
    from .workflow import CogniacWorkflow
    try:
        wf = CogniacWorkflow.get(cc, args.workflow_id)
        wf.delete()
        output({"workflow_id": args.workflow_id, "status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_workflows_edgeflow_targets(args):
    cc = get_connection(args)
    from .workflow import CogniacWorkflow
    output(CogniacWorkflow.edgeflow_targets(cc, edgeflow_model=getattr(args, 'edgeflow_model', None)), args)


# ---- workflow-version ----

def cmd_workflow_version_new(args):
    cc = get_connection(args)
    from .workflow import CogniacWorkflow
    try:
        wf = CogniacWorkflow.new_version(cc, args.workflow_id, _json_body(args) or {})
        output(obj_to_dict(wf), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_workflow_version_get(args):
    cc = get_connection(args)
    from .workflow import CogniacWorkflow
    try:
        wf = CogniacWorkflow.get_version(cc, args.base_id, args.version)
        output(obj_to_dict(wf), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- users ----

def cmd_users_list(args):
    cc = get_connection(args)
    from .user import CogniacUser
    users = CogniacUser.get_all(cc,
                                user_id=getattr(args, 'user_query_id', None),
                                tenant_id=getattr(args, 'user_query_tenant_id', None))
    output([obj_to_dict(u) for u in users], args)


def cmd_users_get(args):
    cc = get_connection(args)
    from .user import CogniacUser
    try:
        output(obj_to_dict(CogniacUser.get_by_id(cc, args.user_id)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_users_delete(args):
    cc = get_connection(args)
    from .user import CogniacUser
    try:
        CogniacUser.delete_by_id(cc, args.user_id)
        output({"user_id": args.user_id, "status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_users_tenants(args):
    cc = get_connection(args)
    from .user import CogniacUser
    try:
        output(CogniacUser.tenants(cc, user_id=args.user_id), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_users_request_password_reset(args):
    cc = get_connection(args)
    from .user import CogniacUser
    output(CogniacUser.request_password_reset(cc, args.email)
           or {"email": args.email, "status": "requested"}, args)


# ---- tenant-edgeflow-certificate ----

def cmd_tenant_ef_cert_get(args):
    cc = get_connection(args)
    try:
        output(cc.tenant.get_edgeflow_certificate(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_tenant_ef_cert_set(args):
    cc = get_connection(args)
    try:
        output(cc.tenant.set_edgeflow_certificate(body=_json_body(args)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_tenant_ef_cert_delete(args):
    cc = get_connection(args)
    try:
        output(cc.tenant.delete_edgeflow_certificate() or {"status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- tenant-meraki-key ----

def cmd_tenant_meraki_key_delete(args):
    cc = get_connection(args)
    try:
        cc.tenant.delete_meraki_api_key()
        output({"status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- tenant-import ----

def cmd_tenant_import(args):
    cc = get_connection(args)
    from .tenant import CogniacTenant
    try:
        output(CogniacTenant.get_cloudcore_import(cc, cc.tenant.tenant_id, args.cloudcore_import_key), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- tenant users ----

def cmd_tenant_users_list(args):
    cc = get_connection(args)
    output(cc.tenant.users(), args)


def cmd_tenant_users_add(args):
    cc = get_connection(args)
    try:
        role = getattr(args, 'role', None) or 'tenant_user'
        cc.tenant.add_user(args.email, role=role)
        output({"email": args.email, "role": role, "status": "added"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_tenant_users_delete(args):
    cc = get_connection(args)
    try:
        cc.tenant.delete_user(args.email)
        output({"email": args.email, "status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_tenant_users_role_set(args):
    cc = get_connection(args)
    try:
        cc.tenant.set_user_role(args.email, args.role)
        output({"email": args.email, "role": args.role, "status": "role set"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- application update / model list ----

def cmd_apps_create(args):
    cc = get_connection(args)
    from .app import CogniacApplication
    try:
        # CogniacApplication.create takes name + application_type (+ optional
        # fields) as keyword arguments; --body supplies them as a JSON object.
        app = CogniacApplication.create(cc, **(_json_body(args) or {}))
        output(obj_to_dict(app), args, 'app')
    except (ClientError, TypeError) as e:
        error_exit("ClientError", str(e))


def cmd_apps_update(args):
    cc = get_connection(args)
    body = _assemble_update_body(args, 'application')
    if not body:
        error_exit("BadRequest", "no fields to update; pass per-field flags or --body")
    try:
        app = cc.get_application(args.application_id)
        output(app.update(body), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_apps_delete(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        app.delete()
        output({"application_id": args.application_id, "status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_model_list(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(list(app.models(start=args.start, end=args.end, limit=args.limit,
                               reverse=args.reverse)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_model_download(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        filename = app.download_model(model_id=getattr(args, 'model_id', None))
        output({"application_id": args.application_id, "filename": filename, "status": "downloaded"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- subject update / delete / disassociate ----

def cmd_subjects_update(args):
    cc = get_connection(args)
    body = _assemble_update_body(args, 'subject')
    if not body:
        error_exit("BadRequest", "no fields to update; pass per-field flags or --body")
    try:
        subject = cc.get_subject(args.subject_uid)
        output(subject.update(body), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_subjects_delete(args):
    cc = get_connection(args)
    try:
        subject = cc.get_subject(args.subject_uid)
        subject.delete()
        output({"subject_uid": args.subject_uid, "status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_subjects_disassociate(args):
    cc = get_connection(args)
    try:
        subject = cc.get_subject(args.subject_uid)
        subject.disassociate_media(media=args.media_id)
        output({"subject_uid": args.subject_uid, "media_id": args.media_id, "status": "disassociated"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- media update / delete / detection list ----

def cmd_media_update(args):
    cc = get_connection(args)
    body = _assemble_update_body(args, 'media')
    if not body:
        error_exit("BadRequest", "no fields to update; pass per-field flags or --body")
    try:
        media = cc.get_media(args.media_id)
        output(media.update(body), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_media_delete(args):
    cc = get_connection(args)
    try:
        media = cc.get_media(args.media_id)
        media.delete()
        output({"media_id": args.media_id, "status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_media_detections_list(args):
    cc = get_connection(args)
    try:
        media = cc.get_media(args.media_id)
        detections = media.detections()
        limit = getattr(args, 'limit', None)
        if limit:
            detections = detections[:limit]
        output(detections, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- camera create / update / delete ----

def cmd_cameras_create(args):
    cc = get_connection(args)
    from .network_camera import CogniacNetworkCamera
    try:
        # CogniacNetworkCamera.create takes name + url (+ optional device fields)
        # as keyword arguments; --body supplies them as a JSON object.
        cam = CogniacNetworkCamera.create(cc, **(_json_body(args) or {}))
        output(obj_to_dict(cam), args, 'camera')
    except (ClientError, TypeError) as e:
        error_exit("ClientError", str(e))


def cmd_cameras_update(args):
    cc = get_connection(args)
    body = _assemble_update_body(args, 'camera')
    if not body:
        error_exit("BadRequest", "no fields to update; pass per-field flags or --body")
    try:
        cam = cc.get_camera(args.network_camera_id)
        output(cam.update(body), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_cameras_delete(args):
    cc = get_connection(args)
    try:
        cam = cc.get_camera(args.network_camera_id)
        cam.delete()
        output({"network_camera_id": args.network_camera_id, "status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- edgeflow update ----

def cmd_edgeflows_update(args):
    cc = get_connection(args)
    try:
        ef = cc.get_edgeflow(args.edgeflow_id)
        output(ef.update(_json_body(args) or {}), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- edgeflow device-control events ----
#
# These POST /1/gateways/{id}/event/<name>. The SDK methods return None (the
# device acts asynchronously), so each handler reports the dispatched event.

def _ef_event_result(args, event, extra=None):
    out = {"edgeflow_id": args.edgeflow_id, "event": event, "status": "sent"}
    if extra:
        out.update(extra)
    return out


def cmd_ef_event_reboot(args):
    cc = get_connection(args)
    try:
        cc.get_edgeflow(args.edgeflow_id).reboot()
        output(_ef_event_result(args, "reboot"), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_ef_event_ping(args):
    cc = get_connection(args)
    try:
        cc.get_edgeflow(args.edgeflow_id).ping(ping_id=getattr(args, 'ping_id', None))
        output(_ef_event_result(args, "ping"), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_ef_event_upgrade(args):
    cc = get_connection(args)
    try:
        cc.get_edgeflow(args.edgeflow_id).upgrade(args.software_version)
        output(_ef_event_result(args, "upgrade", {"software_version": args.software_version}), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_ef_event_set_boot(args):
    cc = get_connection(args)
    try:
        cc.get_edgeflow(args.edgeflow_id).set_boot_software_version(args.software_version)
        output(_ef_event_result(args, "set_boot_software_version",
                                {"software_version": args.software_version}), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_ef_event_factory_reset(args):
    cc = get_connection(args)
    try:
        cc.get_edgeflow(args.edgeflow_id).factory_reset()
        output(_ef_event_result(args, "factory_reset"), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_ef_event_flush_upload_queue(args):
    cc = get_connection(args)
    try:
        cc.get_edgeflow(args.edgeflow_id).flush_upload_queue(
            start_time=getattr(args, 'start_time', None),
            end_time=getattr(args, 'end_time', None))
        output(_ef_event_result(args, "flush_upload_queue"), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_ef_event_time_bound_upload(args):
    cc = get_connection(args)
    try:
        cc.get_edgeflow(args.edgeflow_id).time_bound_media_upload(args.start_time, args.end_time)
        output(_ef_event_result(args, "time_bound_media_upload",
                                {"start_time": args.start_time, "end_time": args.end_time}), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_ef_event_trigger_capture(args):
    cc = get_connection(args)
    try:
        cc.get_edgeflow(args.edgeflow_id).trigger_camera_capture(
            args.subject_uid, trigger_domain_unit=getattr(args, 'trigger_domain_unit', None))
        output(_ef_event_result(args, "trigger_camera_capture", {"subject_uid": args.subject_uid}), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# ---- user api keys ----

def cmd_user_apikey_list(args):
    cc = get_connection(args)
    from .user import CogniacUser
    try:
        user = CogniacUser.get_by_id(cc, args.user_id)
        output(user.api_keys(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_user_apikey_get(args):
    cc = get_connection(args)
    from .user import CogniacUser
    try:
        user = CogniacUser.get_by_id(cc, args.user_id)
        output(user.api_key(args.api_key_id), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_user_apikey_create(args):
    cc = get_connection(args)
    from .user import CogniacUser
    try:
        user = CogniacUser.get_by_id(cc, args.user_id)
        output(user.create_api_key(args.description), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_user_apikey_delete(args):
    cc = get_connection(args)
    from .user import CogniacUser
    try:
        user = CogniacUser.get_by_id(cc, args.user_id)
        user.delete_api_key(args.api_key_id)
        output({"user_id": args.user_id, "api_key_id": args.api_key_id, "status": "deleted"}, args)
    except ClientError as e:
        error_exit("ClientError", str(e))


# -- Parser construction --
#
# The CLI is noun-first / verb-last and nested (max depth ~3-4). A command's
# canonical form reads `cogniac <noun> [<sub-noun> ...] <verb>`. Every current
# flat/hyphenated spelling is preserved as a HIDDEN deprecated alias that routes
# to the SAME handler — registered without a `help` description so they do not
# clutter `--help`. Synonyms / plurals / abbreviations are accepted on every
# path token via resource_aliases() / _SYNONYM_GROUPS.
#
# Verb registration is factored into _add_verb(): the nested sub-noun's
# subparsers object and its hidden flat-alias top-level subparsers object are
# each handed the same (name, handler, arg-spec) so there is exactly one handler
# per command and no argument-definition duplication.


def _add_resource(subparsers, canonical, extra_aliases=None, **kwargs):
    """Register a top-level resource subparser under its canonical name plus
    all of its generated sing/plur + abbreviation/synonym aliases.

    extra_aliases: optional iterable of additional alias spellings that the
    generator cannot derive from the token synonym groups (e.g. the
    'deployment-group' spelling for the 'deployment' resource)."""
    aliases = resource_aliases(canonical)
    if extra_aliases:
        aliases = sorted(set(aliases) | set(extra_aliases))
    return subparsers.add_parser(canonical, aliases=aliases, **kwargs)


# An argument spec is a tuple: (args_tuple, kwargs_dict) passed straight to
# add_argument(). Reused across the nested verb and its flat-alias twin.
# Deprecated positional ids (mirrors of --<resource>-id flags) carry this dest
# suffix; _resolve_positional_ids folds them into the canonical dest post-parse.
_POSID_SUFFIX = '__posid'


def _apply_args(parser, arg_specs):
    for names, opts in (arg_specs or []):
        opts = dict(opts)
        make_posid = opts.pop('_posid', False)
        required = opts.pop('_required', False)
        parser.add_argument(*names, **opts)            # the --<resource>-id flag
        if make_posid:
            dest = opts['dest']
            # deprecated positional mirror (hidden from --help); folded into
            # <dest> after parsing so existing `... get <id>` callers keep working.
            parser.add_argument(dest + _POSID_SUFFIX, nargs='?', default=None,
                                metavar=opts.get('metavar', dest.upper()),
                                help=argparse.SUPPRESS)
            if required:
                parser.set_defaults(**{'_reqid_' + dest: True})


_GLOBAL_PARENT = None


def _global_parent():
    """A parent parser carrying the global flags (`--format`, `--tenant`) so they
    are also accepted *after* the command (`cogniac application list --format table`),
    not just before it. The flags default to SUPPRESS here so a trailing flag
    never clobbers a value given before the command; the top-level parser keeps
    the real defaults."""
    global _GLOBAL_PARENT
    if _GLOBAL_PARENT is None:
        gp = argparse.ArgumentParser(add_help=False)
        gp.add_argument('--format', choices=['json', 'table', 'jsonl'],
                        default=argparse.SUPPRESS,
                        help='Output format: json (default), table, or jsonl')
        gp.add_argument('--tenant', '--tenant_id', dest='tenant',
                        default=argparse.SUPPRESS,
                        help='Tenant ID for this invocation (overrides COG_TENANT)')
        _GLOBAL_PARENT = gp
    return _GLOBAL_PARENT


def _add_verb(sub, name, handler, arg_specs=None, help='', aliases=None, hidden=False):
    """Add a verb subparser to a subparsers object and bind its handler.

    sub:        an add_subparsers() object
    name:       canonical verb name (e.g. 'get', 'list', 'release')
    handler:    cmd_* function bound via set_defaults(func=...)
    arg_specs:  list of (names_tuple, add_argument_kwargs) applied in order
    aliases:    additional verb-level alias spellings (hidden, deprecated)
    hidden:     when True, omit this verb from --help (still accepted/parsed)
    """
    # NOTE: argparse renders a literal "==SUPPRESS==" line for a subparser added
    # with help=SUPPRESS when it also has aliases. To keep deprecated forms out
    # of --help cleanly, we simply omit the `help` kwarg entirely: argparse then
    # accepts/parses the command but emits no description line for it.
    kw = {'aliases': list(aliases)} if aliases else {}
    if not hidden and help:
        kw['help'] = help
    p = sub.add_parser(name, parents=[_global_parent()], **kw)
    _apply_args(p, arg_specs)
    p.set_defaults(func=handler)
    return p


def _flat_alias(subparsers, canonical, registrar, extra_aliases=None):
    """Register a HIDDEN top-level flat-alias parser for a compound nested path
    (e.g. `application-feedback` -> `application feedback`). The flat parser's
    verbs are registered by `registrar`, which is the SAME callable used to
    populate the nested sub-noun — so both share one handler + arg-spec set.

    The flat parser is added without a `help` kwarg so it stays out of --help
    (see _add_verb for why help=SUPPRESS is avoided).

    canonical:   the hyphenated flat spelling (e.g. 'application-feedback')
    registrar:   fn(subparsers_obj, hidden=True) that adds the verbs
    """
    aliases = resource_aliases(canonical)
    if extra_aliases:
        aliases = sorted(set(aliases) | set(extra_aliases))
    p = subparsers.add_parser(canonical, aliases=aliases)
    sub = p.add_subparsers(dest=canonical.replace('-', '_') + '_command')
    registrar(sub, hidden=True)
    return p


# Common reusable argument specs ------------------------------------------------

def _body_arg(value):
    """Resolve a --body value: inline JSON is returned as-is, `@PATH` reads a
    file, and `-` reads stdin — so agents don't fight shell quoting on large
    bodies. The result is still a JSON string, parsed downstream by _json_body."""
    try:
        if value == '-':
            return sys.stdin.read()
        if value.startswith('@'):
            with open(value[1:], 'r') as f:
                return f.read()
    except OSError as e:
        raise argparse.ArgumentTypeError("could not read --body %r: %s" % (value, e))
    return value


def _timestamp(value):
    """A timestamp arg: epoch seconds (a number) or an ISO 8601 datetime
    (e.g. 2026-01-02T03:04:05Z). Returns epoch seconds as a float."""
    try:
        return float(value)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except ValueError:
        raise argparse.ArgumentTypeError(
            "expected epoch seconds or an ISO 8601 datetime, got %r" % value)


_BODY = [(('--body',), {'type': _body_arg, 'metavar': 'JSON',
                        'help': 'JSON request body; also @FILE to read a file or - for stdin'})]
_BODY_REQ = [(('--body',), {'required': True, 'type': _body_arg, 'metavar': 'JSON',
                            'help': 'JSON request body; also @FILE to read a file or - for stdin'})]


# Resource ids are passed as --<resource>-id flags (e.g. --application-id,
# --subject-uid). _id() builds that arg-spec; the dest keeps the resource name so
# handlers read args.application_id etc. unchanged. required=False for optional
# filters (e.g. an optional id on a list command).
#
# By default a deprecated optional positional mirror of the flag is also accepted
# (so `application get <id>` keeps working alongside `application get --application-id <id>`);
# _apply_args registers it and _resolve_positional_ids folds it into the same dest
# after parsing, with the flag winning when both are given. pos=False drops the
# mirror for the few verbs that already take another positional (e.g.
# `classify <image-file>`, `workflow version get <version>`), where an optional
# id-positional would be ambiguous — there the flag is required outright.
def _id(dest, help, required=True, pos=True):
    flag = '--' + dest.replace('_', '-')
    opts = {'dest': dest, 'help': help, 'metavar': dest.upper()}
    if pos:
        opts['default'] = None
        opts['_posid'] = True
        opts['_required'] = bool(required)
    elif required:
        opts['required'] = True
    else:
        opts['default'] = None
    return ((flag,), opts)


def _resolve_positional_ids(parser, args):
    """Fold deprecated positional id mirrors (``<dest>__posid``) into their
    canonical ``--<resource>-id`` dest, then enforce required ids — either the
    flag or the positional satisfies the requirement. Exits via parser.error
    (usage error, code 2) listing the canonical flag when a required id is
    absent in both forms. Removes the bookkeeping attributes so handlers see
    only the canonical dest."""
    ns = vars(args)
    for attr in list(ns):
        if attr.endswith(_POSID_SUFFIX):
            canon = attr[:-len(_POSID_SUFFIX)]
            if ns.get(canon) is None and ns[attr] is not None:
                ns[canon] = ns[attr]
            del ns[attr]
    missing = []
    for attr in list(ns):
        if attr.startswith('_reqid_'):
            canon = attr[len('_reqid_'):]
            if ns.get(canon) is None:
                missing.append('--' + canon.replace('_', '-'))
            del ns[attr]
    if missing:
        parser.error("the following arguments are required: %s "
                     "(each may instead be given as a positional argument)"
                     % ", ".join(missing))


def _command_catalog(parser, path=(), cmd_help=None):
    """Walk the parser tree and return a flat catalog of every leaf command
    (canonical names) with its args — name, positional?, required?, type,
    choices, help. One `cogniac commands` call maps the whole surface so an
    agent need not probe `--help` level by level. Global flags (--format,
    --tenant) and hidden deprecated forms are omitted."""
    out = []
    if parser.get_default('func') is not None:
        args_info = []
        for a in parser._actions:
            if isinstance(a, (argparse._HelpAction, argparse._SubParsersAction)):
                continue
            if a.help is argparse.SUPPRESS or a.dest in ('format', 'tenant'):
                continue
            positional = not a.option_strings
            # a dual-form id flag isn't argparse-required (the positional mirror
            # covers it), but it IS required — _resolve_positional_ids enforces it
            # via the _reqid_<dest> marker. Reflect that so the catalog is honest.
            required = (bool(getattr(a, 'required', False))
                        or (positional and a.nargs not in ('?', '*'))
                        or bool(parser.get_default('_reqid_' + a.dest)))
            args_info.append({
                'name': a.option_strings[0] if a.option_strings else (a.metavar or a.dest),
                'positional': positional,
                'required': required,
                'type': getattr(a.type, '__name__', None) if a.type else None,
                'choices': list(a.choices) if a.choices else None,
                'help': a.help,
            })
        out.append({'command': ' '.join(path), 'help': cmd_help, 'args': args_info})
    for spa in [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]:
        help_by_name = {ca.dest: ca.help for ca in getattr(spa, '_choices_actions', [])}
        canon = {}
        for name, sub in spa.choices.items():
            canon.setdefault(id(sub), name)
        done = set()
        for name, sub in spa.choices.items():
            if id(sub) in done:
                continue
            done.add(id(sub))
            cname = canon[id(sub)]
            out.extend(_command_catalog(sub, path + (cname,), cmd_help=help_by_name.get(cname)))
    return out


def cmd_commands(args):
    """Emit the full command catalog as JSON (one call maps the whole CLI)."""
    print(json.dumps(_command_catalog(build_parser()), indent=2, default=str))


class _CogniacParser(argparse.ArgumentParser):
    """ArgumentParser that turns an invalid-subcommand error into a concise
    message with a close-match suggestion, instead of dumping the full
    (alias-inclusive) choice list. Usage strings stay short via the <command>
    metavar set in build_parser()."""

    def error(self, message):
        m = re.match(r"argument [^:]*: invalid choice: '([^']*)'", message)
        if m:
            bad = m.group(1)
            choices = next((list(a.choices) for a in self._actions
                            if isinstance(a, argparse._SubParsersAction)), [])
            close = difflib.get_close_matches(bad, choices, n=3, cutoff=0.5)
            hint = (" - did you mean: %s?" % ", ".join(close)) if close else ""
            sys.stderr.write(self.format_usage())
            self.exit(2, "%s: error: invalid command '%s'%s "
                         "(run '%s --help' for available commands)\n"
                         % (self.prog, bad, hint, self.prog))
        super().error(message)


def build_parser():
    parser = _CogniacParser(
        prog='cogniac',
        description='Cogniac CLI - query and manage the Cogniac API (JSON or table output)',
    )
    parser.add_argument('--format', choices=['json', 'table', 'jsonl'], default='json',
                        help='Output format: json (default), table, or jsonl (one JSON object per line)')
    parser.add_argument('--tenant', '--tenant_id', default=None,
                        help='Tenant ID to use for this invocation (overrides COG_TENANT). '
                             '`--tenant_id` is an alias for ergonomics.')
    parser.add_argument('--version', action='version',
                        version=f'cogniac {__pkg_version__}',
                        help='Show installed cogniac package version and exit')
    subparsers = parser.add_subparsers(dest='command')

    # ======================================================================
    #  auth
    # ======================================================================
    auth_parser = subparsers.add_parser(
        'auth',
        help='Check credentials, or log in/out. Bare `cogniac auth` checks credentials; '
             'if --tenant/COG_TENANT is set, verifies a session can be minted')
    auth_parser.set_defaults(func=cmd_auth)
    auth_sub = auth_parser.add_subparsers(dest='auth_command')
    _add_verb(auth_sub, 'login', cmd_auth_login,
              [(('--no-browser',), {'dest': 'no_browser', 'action': 'store_true',
                                    'help': 'Do not auto-open a browser; just print the login URL'})],
              help='Log in via the browser and store a per-user API key')
    _add_verb(auth_sub, 'logout', cmd_auth_logout, help='Remove the stored login credential')

    # ======================================================================
    #  commands  (machine-readable catalog of the whole CLI surface)
    # ======================================================================
    commands_parser = subparsers.add_parser(
        'commands', aliases=resource_aliases('commands'),
        help='Print the full command catalog as JSON (noun -> verbs -> args)')
    commands_parser.add_argument('--json', action='store_true',
                                 help='Emit JSON (the default and only format for this command)')
    commands_parser.set_defaults(func=cmd_commands)

    # ======================================================================
    #  tenant
    # ======================================================================
    tenant_parser = subparsers.add_parser('tenant', help='Tenant')
    tenant_sub = tenant_parser.add_subparsers(dest='tenant_command')
    # bare `cogniac tenant` keeps the historical current-tenant behavior
    tenant_parser.set_defaults(func=cmd_tenant)
    _add_verb(tenant_sub, 'get', cmd_tenant, help='Show the current tenant')
    _add_verb(tenant_sub, 'list', cmd_tenants, help='List tenants you are authorized for')

    ten_acct_parser = tenant_sub.add_parser('accounting')
    ten_acct_sub = ten_acct_parser.add_subparsers(dest='tenant_accounting_command')
    _add_verb(ten_acct_sub, 'get', cmd_tenant_accounting_get, hidden=True)
    _add_verb(ten_acct_sub, 'set', cmd_tenant_accounting_set,
              [(('value',), {'metavar': 'VALUE'})], hidden=True)

    # Historical plural: bare `cogniac tenants` lists all authorized tenants —
    # distinct from singular `cogniac tenant` (current tenant). Registered as its
    # own top-level command (not an alias) so the old behavior is preserved; the
    # canonical nested form is `tenant list`.
    tenants_parser = subparsers.add_parser('tenants', help='List tenants you are authorized for')
    tenants_parser.set_defaults(func=cmd_tenants)

    # tenant edgeflow-certificate get/set/delete (single nested sub-noun; the
    # gateway-certificate / edgeflow-cert / ... spellings come for free via
    # resource_aliases()).
    def _reg_tenant_cert(sub, hidden=False):
        _add_verb(sub, 'get', cmd_tenant_ef_cert_get, help='Get the tenant-wide EdgeFlow certificate', hidden=hidden)
        _add_verb(sub, 'set', cmd_tenant_ef_cert_set, _BODY, help='Set the tenant-wide EdgeFlow certificate', hidden=hidden)
        _add_verb(sub, 'delete', cmd_tenant_ef_cert_delete, help='Delete the tenant-wide EdgeFlow certificate', hidden=hidden)
    ten_cert_parser = tenant_sub.add_parser('edgeflow-certificate',
                                            aliases=resource_aliases('edgeflow-certificate'),
                                            help='Tenant-wide EdgeFlow TLS certificate')
    ten_cert_sub = ten_cert_parser.add_subparsers(dest='tenant_edgeflow_certificate_command')
    _reg_tenant_cert(ten_cert_sub)

    # deprecated: the older two-token `tenant edgeflow certificate ...` form,
    # kept (hidden) so it still resolves to the same handlers.
    ten_ef_parser = tenant_sub.add_parser('edgeflow')
    ten_ef_sub = ten_ef_parser.add_subparsers(dest='tenant_edgeflow_command')
    ten_ef_cert_parser = ten_ef_sub.add_parser('certificate', aliases=resource_aliases('certificate'))
    ten_ef_cert_sub = ten_ef_cert_parser.add_subparsers(dest='tenant_edgeflow_certificate_compat_command')
    _reg_tenant_cert(ten_ef_cert_sub, hidden=True)

    # tenant meraki-api-key delete
    ten_meraki_parser = tenant_sub.add_parser('meraki-api-key', help='Tenant Meraki API key')
    ten_meraki_sub = ten_meraki_parser.add_subparsers(dest='tenant_meraki_command')
    _add_verb(ten_meraki_sub, 'delete', cmd_tenant_meraki_key_delete, help="Delete the tenant's Meraki API key")

    # tenant cloudcore-import-key get <cloudcore-import-key>
    ten_import_parser = tenant_sub.add_parser('cloudcore-import-key', help='CloudCore import payload')
    ten_import_sub = ten_import_parser.add_subparsers(dest='tenant_import_command')
    _add_verb(ten_import_sub, 'get', cmd_tenant_import,
              [(('cloudcore_import_key',), {'help': 'CloudCore import key'})],
              help='Fetch a CloudCore import payload by import key')

    # tenant user list/add/delete + tenant user role set
    ten_user_parser = tenant_sub.add_parser('user', aliases=resource_aliases('user'), help='Tenant users')
    ten_user_sub = ten_user_parser.add_subparsers(dest='tenant_user_command')
    _add_verb(ten_user_sub, 'list', cmd_tenant_users_list, help="List the tenant's users")
    _add_verb(ten_user_sub, 'add', cmd_tenant_users_add,
              [(('--email',), {'required': True, 'help': 'User email'}),
               (('--role',), {'help': 'Tenant role (default: tenant_user)'})],
              help='Add a user to the tenant')
    _add_verb(ten_user_sub, 'delete', cmd_tenant_users_delete,
              [(('--email',), {'required': True, 'help': 'User email'})],
              help='Remove a user from the tenant')
    ten_user_role_parser = ten_user_sub.add_parser('role', help='Tenant user role')
    ten_user_role_sub = ten_user_role_parser.add_subparsers(dest='tenant_user_role_command')
    _add_verb(ten_user_role_sub, 'set', cmd_tenant_users_role_set,
              [(('--email',), {'required': True, 'help': 'User email'}),
               (('--role',), {'required': True, 'help': 'Tenant role'})],
              help="Set a tenant user's role")

    # hidden flat aliases for the old tenant-* spellings
    _flat_alias(subparsers, 'tenant-edgeflow-certificate', _reg_tenant_cert)

    def _reg_tenant_meraki(sub, hidden=False):
        _add_verb(sub, 'delete', cmd_tenant_meraki_key_delete, help='Delete the tenant Meraki API key', hidden=hidden)
    _flat_alias(subparsers, 'tenant-meraki-key', _reg_tenant_meraki)

    ti_parser = _add_resource(subparsers, 'tenant-import')
    ti_parser.add_argument('cloudcore_import_key', help='CloudCore import key')
    ti_parser.set_defaults(func=cmd_tenant_import)

    # ======================================================================
    #  application
    # ======================================================================
    apps_parser = _add_resource(subparsers, 'application', help='Applications')
    apps_sub = apps_parser.add_subparsers(dest='apps_command')

    _LEADERBOARD_ARGS = [
        _id('application_id', 'Application ID'),
        (('--set-assignment',), {'dest': 'set_assignment', 'choices': ['validation', 'training'],
                                 'default': 'validation', 'help': 'Set assignment (default: validation)'}),
        (('--snapshot-type',), {'dest': 'snapshot_type', 'choices': ['regular', 'int8'],
                                'default': 'regular', 'help': 'Snapshot type (default: regular)'}),
        (('--eval-metrics',), {'dest': 'eval_metrics', 'choices': ['primary', 'all'],
                               'default': 'primary', 'help': 'Primary metric only or all (default: primary)'}),
        (('--top',), {'type': int, 'default': None, 'help': 'Show only the top N ranked models'}),
        (('--full',), {'action': 'store_true', 'help': 'Include per-subject metric breakdowns'}),
    ]
    _EVENTS_ARGS = [
        _id('application_id', 'Application ID'),
        (('--start',), {'type': _timestamp, 'metavar': 'EPOCH_OR_ISO8601', 'help': 'Filter timestamp > start (epoch seconds or ISO 8601)'}),
        (('--end',), {'type': _timestamp, 'metavar': 'EPOCH_OR_ISO8601', 'help': 'Filter timestamp < end (epoch seconds or ISO 8601)'}),
        (('--limit',), {'type': int, 'default': None, 'help': 'Max results'}),
        (('--cursor',), {'help': 'Pagination cursor'}),
        (('--reverse',), {'action': 'store_true', 'help': 'Sort high to low'}),
        (('--event-type',), {'dest': 'event_types', 'nargs': '+', 'help': 'Filter by event type name(s)'}),
    ]

    _add_verb(apps_sub, 'list', cmd_apps_list, help='List the tenant applications')
    _add_verb(apps_sub, 'get', cmd_apps_get,
              [_id('application_id', 'Application ID')], help='Show one application')
    _add_verb(apps_sub, 'create', cmd_apps_create, _BODY_REQ, help='Create an application')
    _add_verb(apps_sub, 'update', cmd_apps_update,
              [_id('application_id', 'Application ID')] + _update_arg_specs('application') + _BODY,
              help="Update an application's mutable fields (per-field flags and/or --body)")
    _add_verb(apps_sub, 'delete', cmd_apps_delete,
              [_id('application_id', 'Application ID')], help='Delete an application')
    _add_verb(apps_sub, 'leaderboard', cmd_apps_leaderboard, _LEADERBOARD_ARGS,
              help='Ranked candidate-model snapshot for the app')
    _add_verb(apps_sub, 'classify', cmd_app_classify,
              [_id('application_id', 'Application ID', pos=False),
               (('image_file',), {'help': 'Local image file path'})],
              help="Run the app's model on a local image")
    _add_verb(apps_sub, 'events', cmd_app_events, _EVENTS_ARGS, help="Stream the app's events")
    # hidden flat verb alias for the old plural 'eval-metrics' spelling lives below

    # application event types
    # NOTE: 'events' (plural) is the streaming verb above, so the event-types
    # sub-noun keeps only the singular 'event' spelling to avoid a collision.
    app_event_parser = apps_sub.add_parser('event', help='Application event types')
    app_event_sub = app_event_parser.add_subparsers(dest='app_event_command')
    _add_verb(app_event_sub, 'types', cmd_app_event_types,
              [_id('application_id', 'Application ID')], help="List the event types the app emits")

    # application detections pending
    def _reg_app_detections(sub, hidden=False):
        _add_verb(sub, 'pending', cmd_app_detections_pending,
                  [_id('application_id', 'Application ID')],
                  help='Count of pending (unreviewed) detections', hidden=hidden)
    app_det_parser = apps_sub.add_parser('detections', aliases=resource_aliases('detections'),
                                         help='Application detections')
    app_det_sub = app_det_parser.add_subparsers(dest='app_detections_command')
    _reg_app_detections(app_det_sub)

    # application replay (sibling verbs)
    def _reg_app_replay(sub, hidden=False):
        _add_verb(sub, 'status', cmd_app_replay_status,
                  [_id('application_id', 'Application ID'),
                   (('--timeout',), {'type': float, 'help': 'Client-side long-poll timeout (seconds)'})],
                  help='Show replay status (long-polls)', hidden=hidden)
        _add_verb(sub, 'start', cmd_app_replay_start,
                  [_id('application_id', 'Application ID')] + _BODY,
                  help='Start an application replay', hidden=hidden)
        _add_verb(sub, 'stop', cmd_app_replay_stop,
                  [_id('application_id', 'Application ID')],
                  help='Stop an in-progress replay', hidden=hidden)
    app_replay_parser = apps_sub.add_parser('replay', help='Application replay')
    app_replay_sub = app_replay_parser.add_subparsers(dest='app_replay_command')
    _reg_app_replay(app_replay_sub)

    # application performance (sibling verbs)
    _PERF_ARGS = [
        _id('application_id', 'Application ID'),
        (('--start',), {'type': _timestamp, 'metavar': 'EPOCH_OR_ISO8601', 'help': 'Filter timestamp > start (epoch seconds or ISO 8601)'}),
        (('--end',), {'type': _timestamp, 'metavar': 'EPOCH_OR_ISO8601', 'help': 'Filter timestamp < end (epoch seconds or ISO 8601)'}),
        (('--limit',), {'type': int, 'default': None, 'help': 'Max results'}),
        (('--reverse',), {'action': 'store_true', 'help': 'Sort high to low'}),
        (('--duration',), {'type': int, 'help': 'Window duration shorthand (start = end - duration)'}),
    ]

    def _reg_app_performance(sub, hidden=False):
        _add_verb(sub, 'current', cmd_app_performance_current, _PERF_ARGS,
                  help='Current-validation performance series', hidden=hidden)
        _add_verb(sub, 'release', cmd_app_performance_release, _PERF_ARGS,
                  help='Release-validation performance series', hidden=hidden)
        _add_verb(sub, 'new-random', cmd_app_performance_new_random,
                  [_id('application_id', 'Application ID'),
                   (('--limit',), {'type': int, 'default': None, 'help': 'Max results'})],
                  help='New-random test-set performance', hidden=hidden)
    app_perf_parser = apps_sub.add_parser('performance', aliases=resource_aliases('performance'),
                                          help='Application performance')
    app_perf_sub = app_perf_parser.add_subparsers(dest='app_performance_command')
    _reg_app_performance(app_perf_sub)

    # application push
    def _reg_app_push(sub, hidden=False):
        _add_verb(sub, 'get', cmd_app_push,
                  [_id('application_id', 'Application ID'),
                   (('--device-id',), {'dest': 'device_id', 'help': 'Device ID'}),
                   (('--app-bundle-id',), {'dest': 'app_bundle_id', 'help': 'App bundle ID'}),
                   (('--event-type',), {'dest': 'event_type', 'help': 'Event type'})],
                  help="Get a device's push-subscription status", hidden=hidden)
        _add_verb(sub, 'subscribe', cmd_app_push_subscribe,
                  [_id('application_id', 'Application ID'),
                   (('--device-id',), {'dest': 'device_id', 'help': 'Device ID'}),
                   (('--app-bundle-id',), {'dest': 'app_bundle_id', 'help': 'App bundle ID'}),
                   (('--event-type',), {'dest': 'event_type', 'help': 'Event type'}),
                   (('--unsubscribe',), {'action': 'store_true', 'help': 'Unsubscribe instead of subscribe'})],
                  help='(Un)subscribe a device to app events', hidden=hidden)
    app_push_parser = apps_sub.add_parser('push', help='Application push notifications')
    app_push_sub = app_push_parser.add_subparsers(dest='app_push_command')
    _reg_app_push(app_push_sub)

    # application feedback
    def _reg_app_feedback(sub, hidden=False):
        _add_verb(sub, 'list', cmd_app_feedback_list,
                  [_id('application_id', 'Application ID'),
                   (('--limit',), {'type': int, 'default': None, 'help': 'Max results'}),
                   (('--cursor',), {'help': 'Pagination cursor'})],
                  help="Stream the app's feedback requests", hidden=hidden)
        _add_verb(sub, 'get', cmd_app_feedback_get,
                  [_id('application_id', 'Application ID'),
                   _id('feedback_id', 'Feedback request ID')],
                  help='Show one feedback request', hidden=hidden)
        _add_verb(sub, 'create', cmd_app_feedback_create,
                  [_id('application_id', 'Application ID')] + _BODY_REQ,
                  help='Create a feedback request', hidden=hidden)
        _add_verb(sub, 'count', cmd_app_feedback_count,
                  [_id('application_id', 'Application ID')],
                  help='Count outstanding feedback requests', hidden=hidden)
        _add_verb(sub, 'pending', cmd_app_feedback_pending,
                  [_id('application_id', 'Application ID'),
                   (('--limit',), {'type': int, 'default': None, 'help': 'Max results'})],
                  help='Pending feedback requests for the caller', hidden=hidden)
        _add_verb(sub, 'purge', cmd_app_feedback_purge,
                  [_id('application_id', 'Application ID')],
                  help="Purge the app's feedback", hidden=hidden)
        _add_verb(sub, 'purge-requests', cmd_app_feedback_purge_requests,
                  [_id('application_id', 'Application ID')],
                  help='Delete all feedback requests', hidden=hidden)
    app_feedback_parser = apps_sub.add_parser('feedback', help='Application feedback')
    app_feedback_sub = app_feedback_parser.add_subparsers(dest='app_feedback_command')
    _reg_app_feedback(app_feedback_sub)
    _flat_alias(subparsers, 'application-feedback', _reg_app_feedback)

    # application model
    def _reg_app_model(sub, hidden=False):
        _add_verb(sub, 'performance', cmd_app_model_performance,
                  [_id('application_id', 'Application ID'),
                   (('--subject-uid',), {'dest': 'subject_uid', 'required': True, 'help': 'Output subject UID (required)'}),
                   (('--consensus',), {'help': 'Consensus filter'}),
                   (('--reverse',), {'action': 'store_true', 'help': 'Sort high to low'}),
                   (('--probability-lower',), {'dest': 'probability_lower', 'type': float, 'help': 'Min probability'}),
                   (('--probability-upper',), {'dest': 'probability_upper', 'type': float, 'help': 'Max probability'}),
                   (('--limit',), {'type': int, 'default': None, 'help': 'Max results'}),
                   (('--cursor',), {'help': 'Pagination cursor'}),
                   (('--set-assignment',), {'dest': 'set_assignment', 'choices': ['validation', 'training'],
                                            'default': 'validation', 'help': 'Set assignment (default: validation)'})],
                  help='Per-subject model performance (may report results-pending)', hidden=hidden)
        _add_verb(sub, 'donate', cmd_app_donate_model,
                  [_id('application_id', 'Target application ID'),
                   (('--source-application-id',), {'dest': 'source_application_id', 'required': True, 'help': 'Source application ID'})],
                  help='Donate a model from a source application into this one', hidden=hidden)
        _add_verb(sub, 'export', cmd_app_model_export,
                  [_id('application_id', 'Application ID'),
                   (('--target',), {'required': True, 'choices': ['meraki'],
                                    'help': 'Export target (currently: meraki)'})],
                  help="Export the app's model to an external target", hidden=hidden)
        _add_verb(sub, 'list', cmd_app_model_list,
                  [_id('application_id', 'Application ID'),
                   (('--start',), {'type': _timestamp, 'metavar': 'EPOCH_OR_ISO8601', 'help': 'Filter timestamp > start (epoch seconds or ISO 8601)'}),
                   (('--end',), {'type': _timestamp, 'metavar': 'EPOCH_OR_ISO8601', 'help': 'Filter timestamp < end (epoch seconds or ISO 8601)'}),
                   (('--limit',), {'type': int, 'default': None, 'help': 'Max results'}),
                   (('--reverse',), {'action': 'store_true', 'help': 'Sort high to low'})],
                  help="Stream the app's models", hidden=hidden)
        _add_verb(sub, 'download', cmd_app_model_download,
                  [_id('application_id', 'Application ID'),
                   (('--model-id',), {'dest': 'model_id', 'help': 'Specific model ID (default: active model)'})],
                  help='Download the active model package (.ccp/.ccppkg)', hidden=hidden)
    app_model_parser = apps_sub.add_parser('model', aliases=resource_aliases('model'), help='Application model')
    app_model_sub = app_model_parser.add_subparsers(dest='app_model_command')
    _reg_app_model(app_model_sub)
    _flat_alias(subparsers, 'application-model', _reg_app_model)

    # application consensus
    def _reg_consensus_release(sub, hidden=False):
        _add_verb(sub, 'list', cmd_app_consensus_releases,
                  [_id('application_id', 'Application ID')],
                  help="List the app's consensus releases", hidden=hidden)
        _add_verb(sub, 'get', cmd_app_consensus_release,
                  [_id('application_id', 'Application ID'),
                   _id('release_id', 'Consensus release ID')],
                  help='Show one consensus release', hidden=hidden)
        _add_verb(sub, 'items', cmd_app_consensus_release_items,
                  [_id('application_id', 'Application ID'),
                   _id('release_id', 'Consensus release ID'),
                   (('--limit',), {'type': int, 'default': None, 'help': 'Max results'}),
                   (('--cursor',), {'help': 'Pagination cursor'})],
                  help="Stream a release's consensus items", hidden=hidden)
        _add_verb(sub, 'upstream', cmd_app_consensus_release_upstream,
                  [_id('application_id', 'Application ID'),
                   _id('release_id', 'Consensus release ID'),
                   (('--limit',), {'type': int, 'default': None, 'help': 'Max results'}),
                   (('--cursor',), {'help': 'Pagination cursor'})],
                  help="Stream a release's upstream assertions", hidden=hidden)
        _add_verb(sub, 'detections', cmd_app_consensus_detection_releases,
                  [_id('application_id', 'Application ID')],
                  help='Combined consensus detections for output subjects', hidden=hidden)

    _CONSENSUS_HISTORY_ARGS = [
        _id('application_id', 'Application ID'),
        (('--start',), {'type': _timestamp, 'metavar': 'EPOCH_OR_ISO8601', 'help': 'Filter timestamp > start (epoch seconds or ISO 8601)'}),
        (('--end',), {'type': _timestamp, 'metavar': 'EPOCH_OR_ISO8601', 'help': 'Filter timestamp < end (epoch seconds or ISO 8601)'}),
        (('--limit',), {'type': int, 'default': None, 'help': 'Max history points'}),
        (('--subject-uid',), {'dest': 'subject_uid', 'help': 'Restrict to a single subject'}),
    ]
    app_consensus_parser = apps_sub.add_parser('consensus', help='Application consensus')
    app_consensus_sub = app_consensus_parser.add_subparsers(dest='app_consensus_command')
    _add_verb(app_consensus_sub, 'history', cmd_app_consensus_history, _CONSENSUS_HISTORY_ARGS,
              help='Consensus-change history for the app')
    app_cons_rel_parser = app_consensus_sub.add_parser('release', help='Consensus releases')
    app_cons_rel_sub = app_cons_rel_parser.add_subparsers(dest='app_consensus_release_command')
    _reg_consensus_release(app_cons_rel_sub)

    # hidden flat aliases for the historical `application consensus-*` verbs
    _add_verb(apps_sub, 'consensus-history', cmd_app_consensus_history, _CONSENSUS_HISTORY_ARGS, hidden=True)
    _add_verb(apps_sub, 'consensus-releases', cmd_app_consensus_releases,
              [_id('application_id', 'Application ID')], hidden=True)
    _add_verb(apps_sub, 'consensus-release', cmd_app_consensus_release,
              [_id('application_id', 'Application ID'),
               _id('release_id', 'Consensus release ID')], hidden=True)
    _add_verb(apps_sub, 'consensus-release-items', cmd_app_consensus_release_items,
              [_id('application_id', 'Application ID'),
               _id('release_id', 'Consensus release ID'),
               (('--limit',), {'type': int, 'default': None}), (('--cursor',), {})], hidden=True)
    _add_verb(apps_sub, 'consensus-release-upstream', cmd_app_consensus_release_upstream,
              [_id('application_id', 'Application ID'),
               _id('release_id', 'Consensus release ID'),
               (('--limit',), {'type': int, 'default': None}), (('--cursor',), {})], hidden=True)
    _add_verb(apps_sub, 'consensus-detection-releases', cmd_app_consensus_detection_releases,
              [_id('application_id', 'Application ID')], hidden=True)

    # hidden flat-verb aliases for the historical `application <verb>` spellings
    _APP_ID = [_id('application_id', 'Application ID')]
    _add_verb(apps_sub, 'eval-metrics', cmd_app_evaluation_metrics, _APP_ID, hidden=True)
    _add_verb(apps_sub, 'evaluation-metrics', cmd_app_evaluation_metrics, _APP_ID, hidden=True)
    _add_verb(apps_sub, 'evaluation-metrics-create', cmd_app_eval_metrics_create, _APP_ID + _BODY, hidden=True)
    _add_verb(apps_sub, 'evaluation-metrics-register-default', cmd_app_eval_metrics_register_default,
              _APP_ID + _BODY, hidden=True)
    _add_verb(apps_sub, 'evaluation-metrics-copy', cmd_app_eval_metrics_copy,
              [_id('source_application_id', 'Source application ID'),
               _id('target_application_id', 'Target application ID')], hidden=True)
    _add_verb(apps_sub, 'donate-model', cmd_app_donate_model,
              [_id('application_id', 'Target application ID'),
               _id('source_application_id', 'Source application ID')], hidden=True)
    # bare `replay` / `push` are superseded by `replay status` / `push get`
    # (those tokens are now sub-nouns); the hyphenated variants below have no clash.
    _add_verb(apps_sub, 'replay-start', cmd_app_replay_start, _APP_ID + _BODY, hidden=True)
    _add_verb(apps_sub, 'replay-stop', cmd_app_replay_stop, _APP_ID, hidden=True)
    _add_verb(apps_sub, 'detections-pending', cmd_app_detections_pending, _APP_ID, hidden=True)
    _add_verb(apps_sub, 'event-types', cmd_app_event_types, _APP_ID, hidden=True)
    _add_verb(apps_sub, 'performance-current', cmd_app_performance_current, _PERF_ARGS, hidden=True)
    _add_verb(apps_sub, 'performance-release', cmd_app_performance_release, _PERF_ARGS, hidden=True)
    _add_verb(apps_sub, 'performance-new-random', cmd_app_performance_new_random,
              _APP_ID + [(('--limit',), {'type': int, 'default': None})], hidden=True)
    _add_verb(apps_sub, 'push-subscribe', cmd_app_push_subscribe,
              _APP_ID + [(('--device-id',), {'dest': 'device_id'}),
                         (('--app-bundle-id',), {'dest': 'app_bundle_id'}),
                         (('--event-type',), {'dest': 'event_type'}),
                         (('--unsubscribe',), {'action': 'store_true'})], hidden=True)

    # application evaluation metrics
    def _reg_eval_metrics(sub, hidden=False):
        _add_verb(sub, 'get', cmd_app_evaluation_metrics,
                  [_id('application_id', 'Application ID')],
                  help="Show the app's active evaluation metrics", hidden=hidden)
        _add_verb(sub, 'create', cmd_app_eval_metrics_create,
                  [_id('application_id', 'Application ID')] + _BODY_REQ,
                  help='Create an evaluation metric', hidden=hidden)
        _add_verb(sub, 'register-default', cmd_app_eval_metrics_register_default,
                  [_id('application_id', 'Application ID')] + _BODY,
                  help='Register the default evaluation metric', hidden=hidden)
        _add_verb(sub, 'copy', cmd_app_eval_metrics_copy,
                  [(('--source-application-id',), {'dest': 'source_application_id', 'required': True, 'help': 'Source application ID'}),
                   (('--target-application-id',), {'dest': 'target_application_id', 'required': True, 'help': 'Target application ID'})],
                  help='Copy evaluation metrics between apps', hidden=hidden)
    app_eval_parser = apps_sub.add_parser('evaluation', aliases=resource_aliases('evaluation'),
                                          help='Application evaluation metrics')
    app_eval_sub = app_eval_parser.add_subparsers(dest='app_evaluation_command')
    app_eval_metrics_parser = app_eval_sub.add_parser('metrics', aliases=resource_aliases('metrics'),
                                                      help='Evaluation metrics')
    app_eval_metrics_sub = app_eval_metrics_parser.add_subparsers(dest='app_evaluation_metrics_command')
    _reg_eval_metrics(app_eval_metrics_sub)

    # application labeling models (atomic terminal nouns)
    app_lie_parser = apps_sub.add_parser('label-image-encoder-model', help='Labeling image-encoder model')
    app_lie_sub = app_lie_parser.add_subparsers(dest='app_label_image_encoder_command')
    _add_verb(app_lie_sub, 'download', cmd_app_label_image_encoder,
              [_id('application_id', 'Application ID')] + _BODY,
              help='Download the labeling image-encoder model')
    app_lmd_parser = apps_sub.add_parser('label-mask-decoder-model', help='Labeling mask-decoder model')
    app_lmd_sub = app_lmd_parser.add_subparsers(dest='app_label_mask_decoder_command')
    _add_verb(app_lmd_sub, 'download', cmd_app_label_mask_decoder,
              [_id('application_id', 'Application ID'),
               (('--output', '-o'), {'help': 'Output file path'})],
              help='Download the labeling mask-decoder model')

    # application type
    def _reg_app_type(sub, hidden=False):
        _add_verb(sub, 'list', cmd_app_types_list,
                  [(('--production',), {'action': 'store_true', 'help': 'Only production types'}),
                   (('--deprecated',), {'action': 'store_true', 'help': 'Only deprecated types'}),
                   (('--reverse',), {'action': 'store_true', 'help': 'Reverse sort order'})],
                  help='List available application types', hidden=hidden)
        _add_verb(sub, 'get', cmd_app_types_get,
                  [(('application_type',), {'help': 'Application type name'})],
                  help='Show one application type', hidden=hidden)
    app_type_parser = apps_sub.add_parser('type', aliases=resource_aliases('type'), help='Application types')
    app_type_sub = app_type_parser.add_subparsers(dest='app_type_command')
    _reg_app_type(app_type_sub)
    _flat_alias(subparsers, 'application-type', _reg_app_type)

    # application build (nested noun)
    def _reg_app_build(sub, hidden=False):
        _add_verb(sub, 'list', cmd_build_list,
                  [(('--application-id',), {'dest': 'application_id', 'help': 'Filter to one application ID'})],
                  help='List builds (optionally for one app)', hidden=hidden)
        _add_verb(sub, 'get', cmd_build_get,
                  [_id('application_build_id', 'Build ID')], help='Show one build', hidden=hidden)
        _add_verb(sub, 'create', cmd_build_create, _BODY_REQ, help='Create a build', hidden=hidden)
        _add_verb(sub, 'delete', cmd_build_delete,
                  [_id('application_build_id', 'Build ID')], help='Delete a build', hidden=hidden)
        _add_verb(sub, 'lint', cmd_build_lint,
                  [(('filename',), {'help': 'Local build definition file to lint'})],
                  help='Lint a build definition file', hidden=hidden)
        names_parser = (sub.add_parser('names') if hidden
                        else sub.add_parser('names', help='Build names'))
        names_sub = names_parser.add_subparsers(dest='app_build_names_command')
        _add_verb(names_sub, 'list', cmd_build_names, help='List build names', hidden=hidden)
    app_build_parser = apps_sub.add_parser('build', aliases=resource_aliases('build'), help='Application builds')
    app_build_sub = app_build_parser.add_subparsers(dest='app_build_command')
    _reg_app_build(app_build_sub)
    _flat_alias(subparsers, 'application-build', _reg_app_build)

    # hidden flat aliases for the historical application-* top-level spellings.
    # (application-types is already reachable via the application-type plural alias.)
    _flat_alias(subparsers, 'application-evaluation-metrics', _reg_eval_metrics)

    # historical `application-label` flat noun: image-encoder / mask-decoder verbs
    def _reg_app_label_flat(sub, hidden=False):
        _add_verb(sub, 'image-encoder', cmd_app_label_image_encoder,
                  [_id('application_id', 'Application ID')] + _BODY, hidden=True)
        _add_verb(sub, 'mask-decoder', cmd_app_label_mask_decoder,
                  [_id('application_id', 'Application ID'),
                   (('--output', '-o'), {})], hidden=True)
    _flat_alias(subparsers, 'application-label', _reg_app_label_flat)

    # ======================================================================
    #  subject
    # ======================================================================
    subjects_parser = _add_resource(subparsers, 'subject', help='Subjects')
    subjects_sub = subjects_parser.add_subparsers(dest='subjects_command')
    _add_verb(subjects_sub, 'list', cmd_subjects_list, help='List the tenant subjects')
    _add_verb(subjects_sub, 'get', cmd_subjects_get,
              [_id('subject_uid', 'Subject UID')], help='Show one subject')
    _add_verb(subjects_sub, 'create', cmd_subjects_create,
              [(('name',), {'help': 'Subject name'}),
               (('--description',), {'help': 'Subject description'}),
               (('--external-id',), {'dest': 'external_id', 'help': 'External ID'})],
              help='Create a subject')
    _add_verb(subjects_sub, 'update', cmd_subjects_update,
              [_id('subject_uid', 'Subject UID')] + _update_arg_specs('subject') + _BODY,
              help="Update a subject's mutable fields (per-field flags and/or --body)")
    _add_verb(subjects_sub, 'delete', cmd_subjects_delete,
              [_id('subject_uid', 'Subject UID')], help='Delete a subject')
    _add_verb(subjects_sub, 'search', cmd_subjects_search,
              [(('--prefix',), {'help': 'Subject name prefix'}),
               (('--similar',), {'help': 'Semantically similar text'}),
               (('--name',), {'help': 'Exact subject name'}),
               (('--ids',), {'nargs': '+', 'help': 'Subject UIDs to retrieve'}),
               (('--limit',), {'type': int, 'default': 10, 'help': 'Max results (default: 10)'})],
              help='Search subjects by prefix/similarity/name/ids')
    _add_verb(subjects_sub, 'media', cmd_subjects_media,
              [_id('subject_uid', 'Subject UID'),
               (('--limit',), {'type': int, 'default': 100,
                               'help': 'Max media associations (default: 100; pass a larger --limit '
                                       'to widen). Bounds unbounded reads on large subjects.'}),
               (('--consensus',), {'choices': ['True', 'False', 'Sidelined'], 'help': 'Filter by consensus'}),
               (('--probability-lower',), {'dest': 'probability_lower', 'type': float, 'help': 'Min probability'}),
               (('--probability-upper',), {'dest': 'probability_upper', 'type': float, 'help': 'Max probability'}),
               (('--reverse',), {'action': argparse.BooleanOptionalAction, 'default': True,
                                 'help': 'Sort high to low (use --no-reverse for ascending)'}),
               (('--full-media',), {'dest': 'full_media', 'action': 'store_true',
                                    'help': 'Return full media records (domain_unit, sequence_ix, '
                                            'media_timestamp, created_at, ...) instead of just media_id'})],
              help="Stream a subject's media associations")
    _add_verb(subjects_sub, 'associate', cmd_subjects_associate,
              [_id('subject_uid', 'Subject UID'),
               _id('media_id', 'Media ID to associate'),
               (('--consensus',), {'default': 'None', 'choices': ['True', 'False', 'Sidelined', 'None'],
                                   'help': 'Consensus label (default: None)'})],
              help='Associate a media item with a subject')
    _add_verb(subjects_sub, 'disassociate', cmd_subjects_disassociate,
              [_id('subject_uid', 'Subject UID'),
               _id('media_id', 'Media ID to disassociate')],
              help='Remove a media association from a subject')
    _add_verb(subjects_sub, 'detections', cmd_subjects_detections,
              [_id('subject_uid', 'Subject UID'),
               (('--media-id',), {'dest': 'media_id', 'required': True, 'help': 'Media ID (required by the API)'})],
              help='Assertions for the subject on a given media item')
    # subject consensus history
    subj_cons_parser = subjects_sub.add_parser('consensus', help='Subject consensus')
    subj_cons_sub = subj_cons_parser.add_subparsers(dest='subject_consensus_command')
    _add_verb(subj_cons_sub, 'history', cmd_subjects_consensus_history,
              [_id('subject_uid', 'Subject UID'),
               (('--start',), {'type': _timestamp, 'metavar': 'EPOCH_OR_ISO8601', 'help': 'Filter timestamp > start (epoch seconds or ISO 8601)'}),
               (('--end',), {'type': _timestamp, 'metavar': 'EPOCH_OR_ISO8601', 'help': 'Filter timestamp < end (epoch seconds or ISO 8601)'}),
               (('--limit',), {'type': int, 'default': None, 'help': 'Max history points'})],
              help='Consensus-change history for the subject')

    # ======================================================================
    #  media
    # ======================================================================
    media_parser = _add_resource(subparsers, 'media', help='Media')
    media_sub = media_parser.add_subparsers(dest='media_command')
    _add_verb(media_sub, 'get', cmd_media_get,
              [_id('media_id', 'Media ID'),
               (('--download', '-d'), {'nargs': '?', 'const': True, 'default': False, 'metavar': 'FILE',
                                       'help': 'Download media file (optionally specify output path)'})],
              help='Show media metadata (optionally download)')
    _add_verb(media_sub, 'upload', cmd_media_upload,
              [(('filename',), {'help': 'Local file path or URL'}),
               (('--subject-uid',), {'dest': 'subject_uid', 'help': 'Subject UID to associate after upload'}),
               (('--external-media-id',), {'dest': 'external_media_id', 'help': 'External media ID'}),
               (('--domain-unit',), {'dest': 'domain_unit', 'help': 'Domain unit'}),
               (('--meta-tags',), {'dest': 'meta_tags', 'nargs': '+', 'help': 'Metadata tags'})],
              help='Upload a media file')
    _add_verb(media_sub, 'update', cmd_media_update,
              [_id('media_id', 'Media ID')] + _update_arg_specs('media') + _BODY,
              help="Update a media item's mutable fields (per-field flags and/or --body)")
    _add_verb(media_sub, 'delete', cmd_media_delete,
              [_id('media_id', 'Media ID')], help='Delete a media item')
    _add_verb(media_sub, 'download', cmd_media_download,
              [_id('media_id', 'Media ID'),
               (('--output', '-o'), {'help': 'Output file path (default: <media_id>.<ext>)'})],
              help='Download the media file')
    _add_verb(media_sub, 'search', cmd_media_search,
              [(('--md5',), {'help': 'MD5 hash'}),
               (('--filename',), {'help': 'Filename'}),
               (('--external-media-id',), {'dest': 'external_media_id', 'help': 'External media ID'}),
               (('--domain-unit',), {'dest': 'domain_unit', 'help': 'Domain unit'}),
               (('--limit',), {'type': int, 'default': None, 'help': 'Max results'})],
              help='Search media by md5/filename/external-id/domain-unit')
    _add_verb(media_sub, 'share', cmd_media_share,
              [_id('media_id', 'Media ID')] + _BODY, help='Share a media item')
    # media embeddings get
    media_emb_parser = media_sub.add_parser('embeddings', help='Media embeddings')
    media_emb_sub = media_emb_parser.add_subparsers(dest='media_embeddings_command')
    _add_verb(media_emb_sub, 'get', cmd_media_embeddings,
              [_id('media_id', 'Media ID'),
               (('--model-id',), {'dest': 'model_id', 'help': 'Model ID'}),
               (('--focus',), {'help': 'Focus context (JSON)'})],
              help='Get media embeddings')
    # media detection list/create
    def _reg_media_detection(sub, hidden=False):
        _add_verb(sub, 'list', cmd_media_detections_list,
                  [_id('media_id', 'Media ID'),
                   (('--limit',), {'type': int, 'default': None, 'help': 'Max results'})],
                  help='List detections (assertions) on the media', hidden=hidden)
        _add_verb(sub, 'create', cmd_media_create_detection,
                  [_id('media_id', 'Media ID')] + _BODY,
                  help='Create a detection (assertion) on the media', hidden=hidden)
    media_det_parser = media_sub.add_parser('detection', aliases=resource_aliases('detection'),
                                            help='Media detections')
    media_det_sub = media_det_parser.add_subparsers(dest='media_detection_command')
    _reg_media_detection(media_det_sub)
    # hidden flat alias for the old media-embeddings spelling
    me_parser = _add_resource(subparsers, 'media-embeddings')
    me_parser.add_argument('media_id', help='Media ID')
    me_parser.add_argument('--model-id', dest='model_id', help='Model ID')
    me_parser.add_argument('--focus', help='Focus context (JSON)')
    me_parser.set_defaults(func=cmd_media_embeddings)

    # ======================================================================
    #  edgeflow
    # ======================================================================
    ef_parser = _add_resource(subparsers, 'edgeflow', help='EdgeFlow devices')
    ef_sub = ef_parser.add_subparsers(dest='edgeflows_command')
    _add_verb(ef_sub, 'list', cmd_edgeflows_list, help='List the tenant EdgeFlows')
    _add_verb(ef_sub, 'get', cmd_edgeflows_get,
              [_id('edgeflow_id', 'EdgeFlow ID (gateway_id)')], help='Show one EdgeFlow')
    _add_verb(ef_sub, 'create', cmd_edgeflows_create, _BODY, help='Create an EdgeFlow')
    _add_verb(ef_sub, 'update', cmd_edgeflows_update,
              [_id('edgeflow_id', 'EdgeFlow ID (gateway_id)')] + _BODY_REQ, help="Update an EdgeFlow's fields")
    _add_verb(ef_sub, 'delete', cmd_edgeflows_delete,
              [_id('edgeflow_id', 'EdgeFlow ID (gateway_id)')], help='Delete an EdgeFlow')
    _add_verb(ef_sub, 'status', cmd_edgeflows_status,
              [_id('edgeflow_id', 'EdgeFlow ID (gateway_id)'),
               (('--subsystem',), {'help': 'Filter by subsystem'}),
               (('--limit',), {'type': int, 'default': 10,
                               'help': 'Max status events (default: 10; pass a larger --limit '
                                       'to widen). Bounds the walk over device history.'}),
               (('--list-subsystems',), {'dest': 'list_subsystems', 'action': 'store_true',
                                         'help': 'Discovery mode: instead of listing events, scan device '
                                                 'history and emit the distinct subsystems reported, each '
                                                 'with {subsystem, last_seen, count}. Surfaces low-frequency '
                                                 'subsystems that the default --limit hides. Bound the scan '
                                                 'with --scan-limit.'}),
               (('--scan-limit',), {'dest': 'scan_limit', 'type': int, 'default': 2000,
                                    'help': 'Max events scanned by --list-subsystems (default: 2000). '
                                            'If the scan hits this cap a notice is written to stderr.'})],
              help='EdgeFlow status events')

    # edgeflow certificate
    def _reg_ef_cert(sub, hidden=False):
        _add_verb(sub, 'get', cmd_edgeflow_cert_get,
                  [_id('edgeflow_id', 'EdgeFlow ID (gateway_id)')],
                  help='Get the EdgeFlow client certificate', hidden=hidden)
        _add_verb(sub, 'set', cmd_edgeflow_cert_set,
                  [_id('edgeflow_id', 'EdgeFlow ID (gateway_id)')] + _BODY,
                  help='Set the EdgeFlow certificate', hidden=hidden)
        _add_verb(sub, 'replace', cmd_edgeflow_cert_replace,
                  [_id('edgeflow_id', 'EdgeFlow ID (gateway_id)')] + _BODY,
                  help='Replace the EdgeFlow certificate', hidden=hidden)
        _add_verb(sub, 'delete', cmd_edgeflow_cert_delete,
                  [_id('edgeflow_id', 'EdgeFlow ID (gateway_id)')],
                  help='Delete the EdgeFlow certificate', hidden=hidden)
    ef_cert_parser = ef_sub.add_parser('certificate', aliases=resource_aliases('certificate'),
                                       help='EdgeFlow TLS certificate')
    ef_cert_sub = ef_cert_parser.add_subparsers(dest='edgeflow_certificate_command')
    _reg_ef_cert(ef_cert_sub)
    _flat_alias(subparsers, 'edgeflow-certificate', _reg_ef_cert)

    # edgeflow event (device control). The 'gateway event ...' spelling resolves
    # via the edgeflow<->gateway synonym group on the parent noun.
    def _reg_ef_event(sub, hidden=False):
        eid = [_id('edgeflow_id', 'EdgeFlow ID (gateway_id)')]
        _add_verb(sub, 'reboot', cmd_ef_event_reboot, eid, help='Reboot the EdgeFlow', hidden=hidden)
        _add_verb(sub, 'ping', cmd_ef_event_ping,
                  eid + [(('--ping-id',), {'dest': 'ping_id', 'help': 'Optional ping correlation ID'})],
                  help='Ping the EdgeFlow', hidden=hidden)
        _add_verb(sub, 'upgrade', cmd_ef_event_upgrade,
                  eid + [(('--software-version',), {'dest': 'software_version', 'required': True,
                                                    'help': 'Target software version'})],
                  help='Upgrade to a software version', hidden=hidden)
        _add_verb(sub, 'set-boot-software-version', cmd_ef_event_set_boot,
                  eid + [(('--software-version',), {'dest': 'software_version', 'required': True,
                                                    'help': 'Boot software version'})],
                  help='Set the boot software version', hidden=hidden)
        _add_verb(sub, 'factory-reset', cmd_ef_event_factory_reset, eid,
                  help='Factory-reset the EdgeFlow', hidden=hidden)
        _add_verb(sub, 'flush-upload-queue', cmd_ef_event_flush_upload_queue,
                  eid + [(('--start-time',), {'dest': 'start_time', 'type': float, 'help': 'Window start (epoch seconds)'}),
                         (('--end-time',), {'dest': 'end_time', 'type': float, 'help': 'Window end (epoch seconds)'})],
                  help='Flush the media upload queue', hidden=hidden)
        _add_verb(sub, 'time-bound-media-upload', cmd_ef_event_time_bound_upload,
                  eid + [(('--start-time',), {'dest': 'start_time', 'type': float, 'required': True,
                                              'help': 'Window start (epoch seconds)'}),
                         (('--end-time',), {'dest': 'end_time', 'type': float, 'required': True,
                                            'help': 'Window end (epoch seconds)'})],
                  help='Upload media within a time window', hidden=hidden)
        _add_verb(sub, 'trigger-camera-capture', cmd_ef_event_trigger_capture,
                  eid + [(('--subject-uid',), {'dest': 'subject_uid', 'required': True, 'help': 'Trigger subject UID'}),
                         (('--trigger-domain-unit',), {'dest': 'trigger_domain_unit',
                                                       'help': 'Optional trigger domain unit'})],
                  help='Trigger a camera capture', hidden=hidden)
    ef_event_parser = ef_sub.add_parser('event', aliases=resource_aliases('event'),
                                        help='EdgeFlow device-control events')
    ef_event_sub = ef_event_parser.add_subparsers(dest='edgeflow_event_command')
    _reg_ef_event(ef_event_sub)

    # edgeflow metrics list/names
    def _reg_ef_metrics(sub, hidden=False):
        _add_verb(sub, 'list', cmd_edgeflow_metrics_list,
                  [_id('edgeflow_id', 'Optional EdgeFlow ID to filter to', required=False)],
                  help='List metrics (all, or for one EdgeFlow)', hidden=hidden)
        _add_verb(sub, 'names', cmd_edgeflow_metric_names, help='List metric names', hidden=hidden)
    ef_metrics_parser = ef_sub.add_parser('metrics', aliases=resource_aliases('metrics'), help='EdgeFlow metrics')
    ef_metrics_sub = ef_metrics_parser.add_subparsers(dest='edgeflow_metrics_command')
    _reg_ef_metrics(ef_metrics_sub)
    _flat_alias(subparsers, 'edgeflow-metrics', _reg_ef_metrics)

    # hidden flat alias for the old edgeflow-metric-names spelling
    efmn_parser = _add_resource(subparsers, 'edgeflow-metric-names')
    efmn_parser.set_defaults(func=cmd_edgeflow_metric_names)

    # ======================================================================
    #  camera
    # ======================================================================
    cam_parser = _add_resource(subparsers, 'camera', extra_aliases=['network-camera', 'network-cameras'],
                               help='Network cameras')
    cam_sub = cam_parser.add_subparsers(dest='cameras_command')
    _add_verb(cam_sub, 'list', cmd_cameras_list, help='List the tenant network cameras')
    _add_verb(cam_sub, 'get', cmd_cameras_get,
              [_id('network_camera_id', 'Network camera ID')], help='Show one network camera')
    _add_verb(cam_sub, 'create', cmd_cameras_create, _BODY_REQ, help='Create a network camera')
    _add_verb(cam_sub, 'update', cmd_cameras_update,
              [_id('network_camera_id', 'Network camera ID')] + _update_arg_specs('camera') + _BODY,
              help="Update a network camera's mutable fields (per-field flags and/or --body)")
    _add_verb(cam_sub, 'delete', cmd_cameras_delete,
              [_id('network_camera_id', 'Network camera ID')], help='Delete a network camera')
    _add_verb(cam_sub, 'genicam', cmd_cameras_genicam,
              [_id('network_camera_id', 'Network camera ID')], help="Get the camera's GenICam XML")

    # ======================================================================
    #  deployment
    # ======================================================================
    dep_parser = _add_resource(subparsers, 'deployment', help='Deployment groups',
                               extra_aliases=['deployment-group', 'deployment-groups'])
    dep_sub = dep_parser.add_subparsers(dest='deployments_command')
    _add_verb(dep_sub, 'list', cmd_deployments_list, help='List deployment groups')
    _add_verb(dep_sub, 'get', cmd_deployments_get,
              [_id('deployment_group_id', 'Deployment group ID')], help='Show one deployment group')
    _add_verb(dep_sub, 'create', cmd_deployments_create, _BODY, help='Create a deployment group')
    _add_verb(dep_sub, 'delete', cmd_deployments_delete,
              [_id('deployment_group_id', 'Deployment group ID')], help='Delete a deployment group')
    _add_verb(dep_sub, 'edgeflows', cmd_deployments_edgeflows,
              [_id('deployment_group_id', 'Deployment group ID')], help="List the group's EdgeFlows")
    _add_verb(dep_sub, 'history', cmd_deployments_history,
              [_id('deployment_group_id', 'Deployment group ID'),
               (('--limit',), {'type': int, 'default': None, 'help': 'Max records'}),
               (('--reverse',), {'action': argparse.BooleanOptionalAction, 'default': True,
                                 'help': 'Sort high to low (use --no-reverse for ascending)'})],
              help='Deployment-group change history')
    # deployment prepull status/start
    dep_prepull_parser = dep_sub.add_parser('prepull', help='Deployment image prepull')
    dep_prepull_sub = dep_prepull_parser.add_subparsers(dest='deployment_prepull_command')
    _add_verb(dep_prepull_sub, 'status', cmd_deployments_prepull_status,
              [_id('deployment_group_id', 'Deployment group ID')], help='Show image-prepull status')
    _add_verb(dep_prepull_sub, 'start', cmd_deployments_prepull_start,
              [_id('deployment_group_id', 'Deployment group ID'),
               (('--workflow-id',), {'dest': 'workflow_id', 'required': True, 'help': 'Workflow ID'})],
              help="Start prepull of a workflow's images")
    # deployment target workflow set
    dep_target_parser = dep_sub.add_parser('target', help='Deployment target')
    dep_target_sub = dep_target_parser.add_subparsers(dest='deployment_target_command')
    dep_target_wf_parser = dep_target_sub.add_parser('workflow', aliases=resource_aliases('workflow'),
                                                     help='Deployment target workflow')
    dep_target_wf_sub = dep_target_wf_parser.add_subparsers(dest='deployment_target_workflow_command')
    _add_verb(dep_target_wf_sub, 'set', cmd_deployments_target_workflow,
              [_id('deployment_group_id', 'Deployment group ID'),
               (('--workflow-id',), {'dest': 'workflow_id', 'required': True, 'help': 'Workflow ID'})],
              help="Set the group's target workflow")
    # deployment capacity list/get
    def _reg_dep_capacity(sub, hidden=False):
        _add_verb(sub, 'list', cmd_deployment_capacity_list, help='List deployment capacity classes', hidden=hidden)
        _add_verb(sub, 'get', cmd_deployment_capacity_get,
                  [_id('capacity_class_id', 'Capacity class ID')],
                  help='Show one capacity class', hidden=hidden)
    dep_cap_parser = dep_sub.add_parser('capacity', aliases=resource_aliases('capacity'),
                                        help='Deployment capacity classes')
    dep_cap_sub = dep_cap_parser.add_subparsers(dest='deployment_capacity_command')
    _reg_dep_capacity(dep_cap_sub)
    _flat_alias(subparsers, 'deployment-capacity', _reg_dep_capacity)

    # ======================================================================
    #  workflow
    # ======================================================================
    wf_parser = _add_resource(subparsers, 'workflow', help='Workflows')
    wf_sub = wf_parser.add_subparsers(dest='workflows_command')
    _add_verb(wf_sub, 'list', cmd_workflows_list, help='List the tenant workflows')
    _add_verb(wf_sub, 'get', cmd_workflows_get,
              [_id('workflow_id', 'Workflow ID')], help='Show one workflow')
    _add_verb(wf_sub, 'create', cmd_workflows_create, _BODY, help='Create a workflow')
    _add_verb(wf_sub, 'delete', cmd_workflows_delete,
              [_id('workflow_id', 'Workflow ID')], help='Delete a workflow')
    # workflow edgeflow deployment-targets list
    wf_ef_parser = wf_sub.add_parser('edgeflow', aliases=resource_aliases('edgeflow'),
                                     help='Workflow EdgeFlow deployment targets')
    wf_ef_sub = wf_ef_parser.add_subparsers(dest='workflow_edgeflow_command')
    wf_ef_dt_parser = wf_ef_sub.add_parser('deployment-targets', aliases=['deployment-target'],
                                           help='EdgeFlow deployment targets')
    wf_ef_dt_sub = wf_ef_dt_parser.add_subparsers(dest='workflow_edgeflow_deployment_targets_command')
    _add_verb(wf_ef_dt_sub, 'list', cmd_workflows_edgeflow_targets,
              [(('--edgeflow-model',), {'dest': 'edgeflow_model', 'help': 'Optional EdgeFlow model for detailed target info'})],
              help='List valid EdgeFlow deployment targets')
    # workflow version new/get
    def _reg_wf_version(sub, hidden=False):
        _add_verb(sub, 'new', cmd_workflow_version_new,
                  [_id('workflow_id', 'Base workflow ID')] + _BODY_REQ,
                  help='Create a new workflow version', hidden=hidden)
        _add_verb(sub, 'get', cmd_workflow_version_get,
                  [_id('base_id', 'Base workflow ID', pos=False),
                   (('version',), {'help': 'Version'})],
                  help='Show a specific workflow version', hidden=hidden)
    wf_version_parser = wf_sub.add_parser('version', aliases=resource_aliases('version'), help='Workflow versions')
    wf_version_sub = wf_version_parser.add_subparsers(dest='workflow_version_command')
    _reg_wf_version(wf_version_sub)
    _flat_alias(subparsers, 'workflow-version', _reg_wf_version)

    # ======================================================================
    #  user
    # ======================================================================
    user_parser = _add_resource(subparsers, 'user', help='Users')
    user_sub = user_parser.add_subparsers(dest='users_command')
    _add_verb(user_sub, 'list', cmd_users_list,
              [(('--user-id',), {'dest': 'user_query_id', 'help': 'Filter by user ID'}),
               (('--tenant-id',), {'dest': 'user_query_tenant_id', 'help': 'Filter by tenant ID'})],
              help='Query users (by id)')
    _add_verb(user_sub, 'get', cmd_users_get,
              [_id('user_id', 'User ID')], help='Show one user')
    _add_verb(user_sub, 'delete', cmd_users_delete,
              [_id('user_id', 'User ID')], help='Delete a user')
    _add_verb(user_sub, 'tenants', cmd_users_tenants,
              [_id('user_id', 'User ID (or "current")')], help="List a user's tenants")
    # user password reset <email>
    user_pw_parser = user_sub.add_parser('password', help='User password')
    user_pw_sub = user_pw_parser.add_subparsers(dest='user_password_command')
    _add_verb(user_pw_sub, 'reset', cmd_users_request_password_reset,
              [(('email',), {'help': 'Email or user ID'})], help='Trigger a password-reset email')

    # user api-key list/get/create/delete
    def _reg_user_apikey(sub, hidden=False):
        uid = [_id('user_id', 'User ID (or "current")')]
        _add_verb(sub, 'list', cmd_user_apikey_list, uid, help="List a user's API keys", hidden=hidden)
        _add_verb(sub, 'get', cmd_user_apikey_get,
                  uid + [_id('api_key_id', 'API key ID')], help='Show one API key', hidden=hidden)
        _add_verb(sub, 'create', cmd_user_apikey_create,
                  uid + [(('--description',), {'required': True, 'help': 'Key description'})],
                  help='Create an API key', hidden=hidden)
        _add_verb(sub, 'delete', cmd_user_apikey_delete,
                  uid + [_id('api_key_id', 'API key ID')], help='Delete an API key', hidden=hidden)
    user_apikey_parser = user_sub.add_parser('api-key', aliases=resource_aliases('api-key'), help='User API keys')
    user_apikey_sub = user_apikey_parser.add_subparsers(dest='user_apikey_command')
    _reg_user_apikey(user_apikey_sub)

    # 'cogniac user' with no subcommand keeps the historical current-user behavior
    user_parser.set_defaults(func=cmd_user)

    # Collapse the long, alias-inclusive subcommand list in usage strings to a
    # single <command> placeholder (the full list stays in --help). Without this
    # every usage error dumps ~140 alias spellings, twice.
    def _short_metavar(p):
        for a in p._actions:
            if isinstance(a, argparse._SubParsersAction):
                if a.metavar is None:
                    a.metavar = '<command>'
                for sub in set(a.choices.values()):
                    _short_metavar(sub)
    _short_metavar(parser)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    _resolve_positional_ids(parser, args)

    if not hasattr(args, 'func'):
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except (CredentialError, ServerError, ClientError) as e:
        error_exit(type(e).__name__, str(e))
    except Exception as e:
        error_exit("Error", str(e))


if __name__ == '__main__':
    main()
