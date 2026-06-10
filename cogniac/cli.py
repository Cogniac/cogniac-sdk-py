"""
Cogniac CLI - Agent-friendly command-line interface to the Cogniac API.

Outputs JSON (default) or table format. Errors are JSON on stderr.

Read commands:
    cogniac tenant
    cogniac tenants
    cogniac apps list
    cogniac apps get <application_id>
    cogniac apps leaderboard <application_id> [--set-assignment validation|training] [--snapshot-type regular|int8] [--eval-metrics primary|all] [--top N] [--full]
    cogniac apps eval-metrics <application_id>
    cogniac subjects list
    cogniac subjects get <subject_uid>
    cogniac subjects search [--prefix P] [--name N] [--similar S] [--ids ID ...] [--limit L]
    cogniac subjects media <subject_uid> [--limit L] [--consensus C] [--probability-lower P] [--probability-upper P]
    cogniac media get <media_id>
    cogniac media download <media_id> [--output O]
    cogniac media search [--md5 M] [--filename F] [--external-media-id E] [--domain-unit D] [--limit L]
    cogniac edgeflows list
    cogniac edgeflows get <edgeflow_id>
    cogniac edgeflows status <edgeflow_id> [--subsystem S] [--limit L]
    cogniac cameras list
    cogniac cameras get <network_camera_id>
    cogniac deployments list
    cogniac deployments get <deployment_group_id>
    cogniac workflows get <workflow_id>
    cogniac version
    cogniac auth

Auth commands:
    cogniac auth                    # check credentials (env vars or stored login)
    cogniac auth login [--no-browser]   # browser login; stores per-user API key at ~/.config/cogniac/credentials
    cogniac auth logout             # remove the stored login credential

Write commands:
    cogniac subjects create <name> [--description D] [--external-id E]
    cogniac subjects associate <subject_uid> <media_id> [--consensus C]
    cogniac media upload <filename> [--subject-uid S] [--external-media-id E] [--domain-unit D] [--meta-tags T ...]

Global options:
    --format json|table  (default: json)

Copyright (C) 2016 Cogniac Corporation.
"""

import argparse
import json
import sys
import os
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
    """Output data as JSON or table based on --format flag."""
    fmt = getattr(args, 'format', 'json')
    if fmt == 'table' and table_type:
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


def error_exit(error_type, detail, exit_code=1):
    """Print JSON error to stderr and exit."""
    sys.stderr.write(json.dumps({"error": error_type, "detail": detail}) + "\n")
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
            limit=args.limit,
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
        events = edgeflow.status(
            subsystem_name=args.subsystem,
            limit=args.limit,
        )
        output([e for e in events], args)
    except ClientError as e:
        error_exit("ClientError", str(e))


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


def cmd_version(args):
    cc = get_connection(args)
    output(cc.get_version(), args)


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


def cmd_app_export_meraki(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.export_model_to_meraki(), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_replay_status(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.replay_status(), args)
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
        output(app.consensus_release_items(args.release_id, limit=args.limit, cursor=args.cursor), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_app_consensus_release_upstream(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        output(app.consensus_release_upstream_assertions(args.release_id, limit=args.limit, cursor=args.cursor), args)
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
        output(app.register_default_evaluation_metric(), args)
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
    output(CogniacApplication.get_all_types(cc), args)


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
        output(app.feedback(limit=args.limit), args)
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
        output(app.pending_feedback_requests(), args)
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
    builds = CogniacBuild.get_all(cc, application_id=getattr(args, 'app', None))
    output([obj_to_dict(b) for b in builds], args)


def cmd_build_get(args):
    cc = get_connection(args)
    from .build import CogniacBuild
    try:
        output(obj_to_dict(CogniacBuild.get(cc, args.build_id)), args)
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
        b = CogniacBuild.get(cc, args.build_id)
        b.delete()
        output({"build_id": args.build_id, "status": "deleted"}, args)
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
        output(CogniacBuild.lint(cc, args.file), args)
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


def cmd_app_label_image_encoder_upload(args):
    cc = get_connection(args)
    try:
        app = cc.get_application(args.application_id)
        # the encoder request body references the media to encode
        body = _json_body(args) or {'file': args.file}
        output(app.labeling_image_encoder(body), args)
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
        output(media.embeddings(model_id=getattr(args, 'model_id', None)), args)
    except ClientError as e:
        error_exit("ClientError", str(e))


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
        output(dg.history(), args)
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
    output(CogniacUser.get_all(cc), args)


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


# -- Parser construction --

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


def build_parser():
    parser = argparse.ArgumentParser(
        prog='cogniac',
        description='Cogniac CLI - query and manage the Cogniac API (JSON or table output)',
    )
    parser.add_argument('--format', choices=['json', 'table'], default='json',
                        help='Output format (default: json)')
    parser.add_argument('--tenant', '--tenant_id', default=None,
                        help='Tenant ID to use for this invocation (overrides COG_TENANT). '
                             '`--tenant_id` is an alias for ergonomics.')
    parser.add_argument('--version', action='version',
                        version=f'cogniac {__pkg_version__}',
                        help='Show installed cogniac package version and exit')
    subparsers = parser.add_subparsers(dest='command')

    # cogniac tenant
    p = subparsers.add_parser('tenant', help='Show current tenant info')
    p.set_defaults(func=cmd_tenant)

    # cogniac tenants
    p = subparsers.add_parser('tenants', help='List all authorized tenants')
    p.set_defaults(func=cmd_tenants)

    # cogniac version
    p = subparsers.add_parser('version', help='Show API version info')
    p.set_defaults(func=cmd_version)

    # cogniac application (aliases: apps, applications, app)
    apps_parser = _add_resource(subparsers, 'application', help='Applications')
    apps_sub = apps_parser.add_subparsers(dest='apps_command')

    p = apps_sub.add_parser('list', help='List all applications')
    p.set_defaults(func=cmd_apps_list)

    p = apps_sub.add_parser('get', help='Get a specific application')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_apps_get)

    p = apps_sub.add_parser('leaderboard',
                            help='Show the most recent ranked candidate-model snapshot for an application')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--set-assignment', dest='set_assignment',
                   choices=['validation', 'training'], default='validation',
                   help='Set assignment to evaluate against (default: validation)')
    p.add_argument('--snapshot-type', dest='snapshot_type',
                   choices=['regular', 'int8'], default='regular',
                   help='Snapshot type (default: regular)')
    p.add_argument('--eval-metrics', dest='eval_metrics',
                   choices=['primary', 'all'], default='primary',
                   help='Return primary metric only or all active metrics (default: primary)')
    p.add_argument('--top', type=int, default=None,
                   help='Show only the top N ranked models (default: all returned)')
    p.add_argument('--full', action='store_true',
                   help='Include per-subject metric breakdowns in JSON output (omitted by default)')
    p.set_defaults(func=cmd_apps_leaderboard)

    # NOTE: 'eval-metrics' kept for backward compatibility; 'evaluation-metrics' is the documented name.
    p = apps_sub.add_parser('eval-metrics',
                            help='List active evaluation metrics for an application')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_apps_eval_metrics_list)

    p = apps_sub.add_parser('evaluation-metrics',
                            help='List active evaluation metrics for an application')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_evaluation_metrics)

    p = apps_sub.add_parser('classify', help='Run inference on an uploaded image')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('image_file', help='Local image file path')
    p.set_defaults(func=cmd_app_classify)

    p = apps_sub.add_parser('donate-model', help='Donate a model from a source application into this one')
    p.add_argument('application_id', help='Target application ID')
    p.add_argument('source_application_id', help='Source application ID')
    p.set_defaults(func=cmd_app_donate_model)

    p = apps_sub.add_parser('export-meraki', help="Export the application's active model to Meraki")
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_export_meraki)

    p = apps_sub.add_parser('replay', help='Show replay status for an application')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_replay_status)

    p = apps_sub.add_parser('replay-start', help='Start an application replay')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--body', help='JSON replay request body')
    p.set_defaults(func=cmd_app_replay_start)

    p = apps_sub.add_parser('replay-stop', help='Stop an in-progress application replay')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_replay_stop)

    p = apps_sub.add_parser('detections-pending', help='Get count of pending detections')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_detections_pending)

    p = apps_sub.add_parser('event-types', help='List available event types for an application')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_event_types)

    p = apps_sub.add_parser('events', help='Query application events')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--start', type=float, help='Filter timestamp > start')
    p.add_argument('--end', type=float, help='Filter timestamp < end')
    p.add_argument('--limit', type=int, default=None, help='Max results')
    p.add_argument('--cursor', help='Pagination cursor')
    p.add_argument('--reverse', action='store_true', help='Sort high to low')
    p.add_argument('--event-types', dest='event_types', nargs='+', help='Filter by event type name(s)')
    p.set_defaults(func=cmd_app_events)

    p = apps_sub.add_parser('consensus-history', help='Consensus history for output subjects')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--start', type=float, help='Filter timestamp > start')
    p.add_argument('--end', type=float, help='Filter timestamp < end')
    p.add_argument('--limit', type=int, default=None, help='Max history points')
    p.add_argument('--subject-uid', dest='subject_uid', help='Restrict to a single subject')
    p.set_defaults(func=cmd_app_consensus_history)

    p = apps_sub.add_parser('performance-current', help='Current-validation performance series')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--start', type=float, help='Filter timestamp > start')
    p.add_argument('--end', type=float, help='Filter timestamp < end')
    p.add_argument('--limit', type=int, default=None, help='Max results')
    p.add_argument('--reverse', action='store_true', help='Sort high to low')
    p.add_argument('--duration', type=int, help='Window duration shorthand (start = end - duration)')
    p.set_defaults(func=cmd_app_performance_current)

    p = apps_sub.add_parser('performance-release', help='Release-validation performance series')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--start', type=float, help='Filter timestamp > start')
    p.add_argument('--end', type=float, help='Filter timestamp < end')
    p.add_argument('--limit', type=int, default=None, help='Max results')
    p.add_argument('--reverse', action='store_true', help='Sort high to low')
    p.add_argument('--duration', type=int, help='Window duration shorthand (start = end - duration)')
    p.set_defaults(func=cmd_app_performance_release)

    p = apps_sub.add_parser('performance-new-random', help='New-random test-set performance')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--limit', type=int, default=None, help='Max results')
    p.set_defaults(func=cmd_app_performance_new_random)

    p = apps_sub.add_parser('push', help='Push-notification subscription status for a device')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--device-id', dest='device_id', help='Device ID')
    p.add_argument('--app-bundle-id', dest='app_bundle_id', help='App bundle ID')
    p.add_argument('--event-type', dest='event_type', help='Event type')
    p.set_defaults(func=cmd_app_push)

    p = apps_sub.add_parser('push-subscribe', help='Subscribe/unsubscribe a device to app events')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--device-id', dest='device_id', help='Device ID')
    p.add_argument('--app-bundle-id', dest='app_bundle_id', help='iOS app bundle ID')
    p.add_argument('--event-type', dest='event_type', help='Event type')
    p.add_argument('--unsubscribe', action='store_true', help='Unsubscribe instead of subscribe')
    p.set_defaults(func=cmd_app_push_subscribe)

    p = apps_sub.add_parser('consensus-releases', help='List consensus releases')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_consensus_releases)

    p = apps_sub.add_parser('consensus-release', help='Get one consensus release')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('release_id', help='Consensus release ID')
    p.set_defaults(func=cmd_app_consensus_release)

    p = apps_sub.add_parser('consensus-release-items', help='Download consensus release items')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('release_id', help='Consensus release ID')
    p.add_argument('--limit', type=int, default=None, help='Max results')
    p.add_argument('--cursor', help='Pagination cursor')
    p.set_defaults(func=cmd_app_consensus_release_items)

    p = apps_sub.add_parser('consensus-release-upstream', help='Consensus release upstream assertions')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('release_id', help='Consensus release ID')
    p.add_argument('--limit', type=int, default=None, help='Max results')
    p.add_argument('--cursor', help='Pagination cursor')
    p.set_defaults(func=cmd_app_consensus_release_upstream)

    p = apps_sub.add_parser('consensus-detection-releases', help='Combined consensus detections')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_consensus_detection_releases)

    p = apps_sub.add_parser('evaluation-metrics-create', help='Create an evaluation metric')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--body', help='JSON evaluation-metric body')
    p.set_defaults(func=cmd_app_eval_metrics_create)

    p = apps_sub.add_parser('evaluation-metrics-register-default', help='Register default evaluation metric')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_eval_metrics_register_default)

    p = apps_sub.add_parser('evaluation-metrics-copy', help='Copy evaluation metrics to a target app')
    p.add_argument('source_application_id', help='Source application ID')
    p.add_argument('target_application_id', help='Target application ID')
    p.set_defaults(func=cmd_app_eval_metrics_copy)

    # cogniac application-types
    at_parser = _add_resource(subparsers, 'application-types', help='Application types')
    at_sub = at_parser.add_subparsers(dest='application_types_command')
    p = at_sub.add_parser('list', help='List application types')
    p.set_defaults(func=cmd_app_types_list)
    p = at_sub.add_parser('get', help='Get a specific application type')
    p.add_argument('application_type', help='Application type name')
    p.set_defaults(func=cmd_app_types_get)

    # cogniac application-feedback
    af_parser = _add_resource(subparsers, 'application-feedback', help='Application feedback')
    af_sub = af_parser.add_subparsers(dest='application_feedback_command')
    p = af_sub.add_parser('list', help='List feedback items')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--limit', type=int, default=10, help='Max results (default: 10)')
    p.add_argument('--cursor', help='Pagination cursor')
    p.set_defaults(func=cmd_app_feedback_list)
    p = af_sub.add_parser('get', help='Get a feedback request')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('feedback_id', help='Feedback request ID')
    p.set_defaults(func=cmd_app_feedback_get)
    p = af_sub.add_parser('create', help='Submit feedback')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--body', help='JSON feedback body')
    p.set_defaults(func=cmd_app_feedback_create)
    p = af_sub.add_parser('count', help='Count feedback requests pending for the user')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_feedback_count)
    p = af_sub.add_parser('pending', help='List pending feedback requests')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_feedback_pending)
    p = af_sub.add_parser('purge', help='Purge feedback requests')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_feedback_purge)
    p = af_sub.add_parser('purge-requests', help='Delete all feedback requests')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_feedback_purge_requests)

    # cogniac application-model
    am_parser = _add_resource(subparsers, 'application-model', help='Application model performance')
    am_sub = am_parser.add_subparsers(dest='application_model_command')
    p = am_sub.add_parser('performance', help='Per-subject model performance')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--subject-uid', dest='subject_uid', required=True, help='Output subject UID (required)')
    p.add_argument('--consensus', help='Consensus filter')
    p.add_argument('--reverse', action='store_true', help='Sort high to low')
    p.add_argument('--probability-lower', dest='probability_lower', type=float, help='Min probability')
    p.add_argument('--probability-upper', dest='probability_upper', type=float, help='Max probability')
    p.add_argument('--limit', type=int, default=None, help='Max results')
    p.add_argument('--cursor', help='Pagination cursor')
    p.add_argument('--set-assignment', dest='set_assignment', choices=['validation', 'training'],
                   default='validation', help='Set assignment (default: validation)')
    p.set_defaults(func=cmd_app_model_performance)

    # cogniac application-build
    ab_parser = _add_resource(subparsers, 'application-build', help='Integration builds')
    ab_sub = ab_parser.add_subparsers(dest='application_build_command')
    p = ab_sub.add_parser('list', help='List builds')
    p.add_argument('--app', help='Filter to one application ID')
    p.set_defaults(func=cmd_build_list)
    p = ab_sub.add_parser('get', help='Get a build')
    p.add_argument('build_id', help='Build ID')
    p.set_defaults(func=cmd_build_get)
    p = ab_sub.add_parser('create', help='Create a build')
    p.add_argument('--body', help='JSON build request body')
    p.set_defaults(func=cmd_build_create)
    p = ab_sub.add_parser('delete', help='Delete a build')
    p.add_argument('build_id', help='Build ID')
    p.set_defaults(func=cmd_build_delete)
    p = ab_sub.add_parser('names', help='List build names')
    p.set_defaults(func=cmd_build_names)
    p = ab_sub.add_parser('lint', help='Lint (flake8) a local file')
    p.add_argument('file', help='Local file to lint')
    p.set_defaults(func=cmd_build_lint)

    # cogniac application-label
    al_parser = _add_resource(subparsers, 'application-label', help='Labeling embedding models')
    al_sub = al_parser.add_subparsers(dest='application_label_command')
    p = al_sub.add_parser('image-encoder', help='Get an image embedding from the encoder model')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--body', help='JSON embedding request body')
    p.set_defaults(func=cmd_app_label_image_encoder)
    p = al_sub.add_parser('image-encoder-upload', help='Get an embedding for an uploaded image reference')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('file', help='File reference')
    p.add_argument('--body', help='JSON embedding request body (overrides file)')
    p.set_defaults(func=cmd_app_label_image_encoder_upload)
    p = al_sub.add_parser('mask-decoder', help='Download the mask decoder model (ONNX)')
    p.add_argument('application_id', help='Application ID')
    p.add_argument('--output', '-o', help='Output file path')
    p.set_defaults(func=cmd_app_label_mask_decoder)
    p = al_sub.add_parser('mask-decoder-head', help='Mask decoder model metadata (HEAD)')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_app_label_mask_decoder_head)

    # cogniac media-embeddings <media_id>
    me_parser = _add_resource(subparsers, 'media-embeddings', help='Media embeddings')
    me_parser.add_argument('media_id', help='Media ID')
    me_parser.add_argument('--model-id', dest='model_id', help='Model ID')
    me_parser.set_defaults(func=cmd_media_embeddings)

    # cogniac subject (aliases: subjects)
    subjects_parser = _add_resource(subparsers, 'subject', help='Subjects')
    subjects_sub = subjects_parser.add_subparsers(dest='subjects_command')

    p = subjects_sub.add_parser('list', help='List all subjects')
    p.set_defaults(func=cmd_subjects_list)

    p = subjects_sub.add_parser('get', help='Get a specific subject')
    p.add_argument('subject_uid', help='Subject UID')
    p.set_defaults(func=cmd_subjects_get)

    p = subjects_sub.add_parser('media', help='List media associations for a subject')
    p.add_argument('subject_uid', help='Subject UID')
    p.add_argument('--limit', type=int, default=100, help='Max results (default: 100)')
    p.add_argument('--consensus', choices=['True', 'False', 'Sidelined'], help='Filter by consensus')
    p.add_argument('--probability-lower', dest='probability_lower', type=float, help='Min probability')
    p.add_argument('--probability-upper', dest='probability_upper', type=float, help='Max probability')
    p.set_defaults(func=cmd_subjects_media)

    p = subjects_sub.add_parser('search', help='Search subjects')
    p.add_argument('--prefix', help='Subject name prefix')
    p.add_argument('--similar', help='Semantically similar text')
    p.add_argument('--name', help='Exact subject name')
    p.add_argument('--ids', nargs='+', help='Subject UIDs to retrieve')
    p.add_argument('--limit', type=int, default=10, help='Max results (default: 10)')
    p.set_defaults(func=cmd_subjects_search)

    p = subjects_sub.add_parser('create', help='Create a new subject')
    p.add_argument('name', help='Subject name')
    p.add_argument('--description', help='Subject description')
    p.add_argument('--external-id', dest='external_id', help='External ID')
    p.set_defaults(func=cmd_subjects_create)

    p = subjects_sub.add_parser('associate', help='Associate media with a subject')
    p.add_argument('subject_uid', help='Subject UID')
    p.add_argument('media_id', help='Media ID to associate')
    p.add_argument('--consensus', default='None',
                   choices=['True', 'False', 'Sidelined', 'None'],
                   help='Consensus label (default: None)')
    p.set_defaults(func=cmd_subjects_associate)

    p = subjects_sub.add_parser('consensus-history', help='Consensus history for a subject')
    p.add_argument('subject_uid', help='Subject UID')
    p.add_argument('--start', type=float, help='Filter timestamp > start')
    p.add_argument('--end', type=float, help='Filter timestamp < end')
    p.add_argument('--limit', type=int, default=None, help='Max history points')
    p.set_defaults(func=cmd_subjects_consensus_history)

    p = subjects_sub.add_parser('detections', help='Subject detections for a given media item')
    p.add_argument('subject_uid', help='Subject UID')
    p.add_argument('media_id', help='Media ID (required by the API)')
    p.set_defaults(func=cmd_subjects_detections)

    # cogniac media
    media_parser = _add_resource(subparsers, 'media', help='Media')
    media_sub = media_parser.add_subparsers(dest='media_command')

    p = media_sub.add_parser('get', help='Get a specific media item')
    p.add_argument('media_id', help='Media ID')
    p.add_argument('--download', '-d', nargs='?', const=True, default=False,
                   metavar='FILE', help='Download media file (optionally specify output path)')
    p.set_defaults(func=cmd_media_get)

    p = media_sub.add_parser('download', help='Download media file to disk')
    p.add_argument('media_id', help='Media ID')
    p.add_argument('--output', '-o', help='Output file path (default: <media_id>.<ext>)')
    p.set_defaults(func=cmd_media_download)

    p = media_sub.add_parser('search', help='Search media')
    p.add_argument('--md5', help='MD5 hash')
    p.add_argument('--filename', help='Filename')
    p.add_argument('--external-media-id', dest='external_media_id', help='External media ID')
    p.add_argument('--domain-unit', dest='domain_unit', help='Domain unit')
    p.add_argument('--limit', type=int, default=None, help='Max results')
    p.set_defaults(func=cmd_media_search)

    p = media_sub.add_parser('upload', help='Upload a media file')
    p.add_argument('filename', help='Local file path or URL')
    p.add_argument('--subject-uid', dest='subject_uid', help='Subject UID to associate after upload')
    p.add_argument('--external-media-id', dest='external_media_id', help='External media ID')
    p.add_argument('--domain-unit', dest='domain_unit', help='Domain unit')
    p.add_argument('--meta-tags', dest='meta_tags', nargs='+', help='Metadata tags')
    p.set_defaults(func=cmd_media_upload)

    p = media_sub.add_parser('share', help='Share a media item')
    p.add_argument('media_id', help='Media ID')
    p.add_argument('--body', help='JSON share request body')
    p.set_defaults(func=cmd_media_share)

    p = media_sub.add_parser('create-detection', help='Submit detection(s) for a media item')
    p.add_argument('media_id', help='Media ID')
    p.add_argument('--body', help='JSON detections request body')
    p.set_defaults(func=cmd_media_create_detection)

    # cogniac edgeflow (aliases: edgeflows, gateway, gateways)
    ef_parser = _add_resource(subparsers, 'edgeflow', help='EdgeFlow devices')
    ef_sub = ef_parser.add_subparsers(dest='edgeflows_command')

    p = ef_sub.add_parser('list', help='List all EdgeFlows')
    p.set_defaults(func=cmd_edgeflows_list)

    p = ef_sub.add_parser('get', help='Get a specific EdgeFlow')
    p.add_argument('edgeflow_id', help='EdgeFlow ID (gateway_id)')
    p.set_defaults(func=cmd_edgeflows_get)

    p = ef_sub.add_parser('status', help='Get EdgeFlow status events')
    p.add_argument('edgeflow_id', help='EdgeFlow ID (gateway_id)')
    p.add_argument('--subsystem', help='Filter by subsystem (e.g. model_detections, ifconfig, ping)')
    p.add_argument('--limit', type=int, default=10, help='Max results (default: 10)')
    p.set_defaults(func=cmd_edgeflows_status)

    p = ef_sub.add_parser('create', help='Create a new EdgeFlow')
    p.add_argument('--body', help='JSON gateway request body')
    p.set_defaults(func=cmd_edgeflows_create)

    p = ef_sub.add_parser('delete', help='Delete an EdgeFlow')
    p.add_argument('edgeflow_id', help='EdgeFlow ID (gateway_id)')
    p.set_defaults(func=cmd_edgeflows_delete)

    # cogniac edgeflow-certificate
    efc_parser = _add_resource(subparsers, 'edgeflow-certificate', help='EdgeFlow TLS certificate')
    efc_sub = efc_parser.add_subparsers(dest='edgeflow_certificate_command')
    p = efc_sub.add_parser('get', help='Get an EdgeFlow TLS certificate')
    p.add_argument('edgeflow_id', help='EdgeFlow ID (gateway_id)')
    p.set_defaults(func=cmd_edgeflow_cert_get)
    p = efc_sub.add_parser('set', help='Set an EdgeFlow TLS certificate')
    p.add_argument('edgeflow_id', help='EdgeFlow ID (gateway_id)')
    p.add_argument('--body', help='JSON certificate/key body')
    p.set_defaults(func=cmd_edgeflow_cert_set)
    p = efc_sub.add_parser('replace', help='Replace an EdgeFlow TLS certificate (PUT)')
    p.add_argument('edgeflow_id', help='EdgeFlow ID (gateway_id)')
    p.add_argument('--body', help='JSON certificate/key body')
    p.set_defaults(func=cmd_edgeflow_cert_replace)
    p = efc_sub.add_parser('delete', help='Delete an EdgeFlow TLS certificate')
    p.add_argument('edgeflow_id', help='EdgeFlow ID (gateway_id)')
    p.set_defaults(func=cmd_edgeflow_cert_delete)

    # cogniac edgeflow-metrics
    efm_parser = _add_resource(subparsers, 'edgeflow-metrics', help='EdgeFlow metrics')
    efm_sub = efm_parser.add_subparsers(dest='edgeflow_metrics_command')
    p = efm_sub.add_parser('list', help='List metrics (all, or for one EdgeFlow)')
    p.add_argument('edgeflow_id', nargs='?', help='Optional EdgeFlow ID to filter to')
    p.set_defaults(func=cmd_edgeflow_metrics_list)

    # cogniac edgeflow-metric-names
    efmn_parser = _add_resource(subparsers, 'edgeflow-metric-names', help='EdgeFlow metric names')
    efmn_parser.set_defaults(func=cmd_edgeflow_metric_names)

    # cogniac camera (aliases: cameras)
    cam_parser = _add_resource(subparsers, 'camera', help='Network cameras')
    cam_sub = cam_parser.add_subparsers(dest='cameras_command')

    p = cam_sub.add_parser('list', help='List all cameras')
    p.set_defaults(func=cmd_cameras_list)

    p = cam_sub.add_parser('get', help='Get a specific camera')
    p.add_argument('network_camera_id', help='Network camera ID')
    p.set_defaults(func=cmd_cameras_get)

    p = cam_sub.add_parser('genicam', help='Get the GenICam XML for a camera')
    p.add_argument('network_camera_id', help='Network camera ID')
    p.set_defaults(func=cmd_cameras_genicam)

    # cogniac deployment (aliases: deployments, deployment-group, deployment-groups)
    dep_parser = _add_resource(subparsers, 'deployment', help='Deployment groups',
                               extra_aliases=['deployment-group', 'deployment-groups'])
    dep_sub = dep_parser.add_subparsers(dest='deployments_command')

    p = dep_sub.add_parser('list', help='List all deployment groups')
    p.set_defaults(func=cmd_deployments_list)

    p = dep_sub.add_parser('get', help='Get a specific deployment group')
    p.add_argument('deployment_group_id', help='Deployment group ID')
    p.set_defaults(func=cmd_deployments_get)

    p = dep_sub.add_parser('create', help='Create a deployment group')
    p.add_argument('--body', help='JSON deployment-group body')
    p.set_defaults(func=cmd_deployments_create)

    p = dep_sub.add_parser('delete', help='Delete a deployment group')
    p.add_argument('deployment_group_id', help='Deployment group ID')
    p.set_defaults(func=cmd_deployments_delete)

    p = dep_sub.add_parser('edgeflows', help='List EdgeFlows assigned to a deployment group')
    p.add_argument('deployment_group_id', help='Deployment group ID')
    p.set_defaults(func=cmd_deployments_edgeflows)

    p = dep_sub.add_parser('history', help='Deployment history for a group')
    p.add_argument('deployment_group_id', help='Deployment group ID')
    p.set_defaults(func=cmd_deployments_history)

    p = dep_sub.add_parser('prepull', help='Prepull status for a deployment group')
    p.add_argument('deployment_group_id', help='Deployment group ID')
    p.set_defaults(func=cmd_deployments_prepull_status)

    p = dep_sub.add_parser('prepull-start', help='Start prepull of a workflow on a deployment group')
    p.add_argument('deployment_group_id', help='Deployment group ID')
    p.add_argument('workflow_id', help='Workflow ID')
    p.set_defaults(func=cmd_deployments_prepull_start)

    p = dep_sub.add_parser('target-workflow', help='Set the target workflow on a deployment group')
    p.add_argument('deployment_group_id', help='Deployment group ID')
    p.add_argument('workflow_id', help='Workflow ID')
    p.set_defaults(func=cmd_deployments_target_workflow)

    # cogniac deployment-capacity
    dc_parser = _add_resource(subparsers, 'deployment-capacity', help='Deployment capacity classes')
    dc_sub = dc_parser.add_subparsers(dest='deployment_capacity_command')
    p = dc_sub.add_parser('list', help='List deployment capacity classes')
    p.set_defaults(func=cmd_deployment_capacity_list)
    p = dc_sub.add_parser('get', help='Get a deployment capacity class')
    p.add_argument('capacity_class_id', help='Capacity class ID')
    p.set_defaults(func=cmd_deployment_capacity_get)

    # cogniac workflow (aliases: workflows)
    wf_parser = _add_resource(subparsers, 'workflow', help='Workflows')
    wf_sub = wf_parser.add_subparsers(dest='workflows_command')

    p = wf_sub.add_parser('list', help='List all workflows')
    p.set_defaults(func=cmd_workflows_list)

    p = wf_sub.add_parser('get', help='Get a specific workflow')
    p.add_argument('workflow_id', help='Workflow ID')
    p.set_defaults(func=cmd_workflows_get)

    p = wf_sub.add_parser('create', help='Create a workflow')
    p.add_argument('--body', help='JSON workflow body')
    p.set_defaults(func=cmd_workflows_create)

    p = wf_sub.add_parser('delete', help='Delete a workflow')
    p.add_argument('workflow_id', help='Workflow ID')
    p.set_defaults(func=cmd_workflows_delete)

    p = wf_sub.add_parser('edgeflow-targets', help='Supported EdgeFlow model targets')
    p.add_argument('edgeflow_model', nargs='?', help='Optional EdgeFlow model for detailed target info')
    p.set_defaults(func=cmd_workflows_edgeflow_targets)

    # cogniac workflow-version
    wv_parser = _add_resource(subparsers, 'workflow-version', help='Workflow versions')
    wv_sub = wv_parser.add_subparsers(dest='workflow_version_command')
    p = wv_sub.add_parser('new', help='Create a new workflow version')
    p.add_argument('workflow_id', help='Base workflow ID')
    p.add_argument('--body', required=True, help='JSON workflow-version body')
    p.set_defaults(func=cmd_workflow_version_new)
    p = wv_sub.add_parser('get', help='Get a specific workflow version')
    p.add_argument('base_id', help='Base workflow ID')
    p.add_argument('version', help='Version')
    p.set_defaults(func=cmd_workflow_version_get)

    # cogniac users (no singular alias — 'user' is the existing leaf)
    users_parser = subparsers.add_parser('users', help='Users')
    users_sub = users_parser.add_subparsers(dest='users_command')
    p = users_sub.add_parser('list', help='List/query users')
    p.set_defaults(func=cmd_users_list)
    p = users_sub.add_parser('get', help='Get a specific user')
    p.add_argument('user_id', help='User ID')
    p.set_defaults(func=cmd_users_get)
    p = users_sub.add_parser('delete', help='Delete a user')
    p.add_argument('user_id', help='User ID')
    p.set_defaults(func=cmd_users_delete)
    p = users_sub.add_parser('tenants', help='List the tenants a user belongs to')
    p.add_argument('user_id', help='User ID (or "current")')
    p.set_defaults(func=cmd_users_tenants)
    p = users_sub.add_parser('request-password-reset', help='Request a password-reset email')
    p.add_argument('email', help='Email or user ID')
    p.set_defaults(func=cmd_users_request_password_reset)

    # cogniac tenant-edgeflow-certificate
    tec_parser = _add_resource(subparsers, 'tenant-edgeflow-certificate',
                               help='Tenant-wide EdgeFlow TLS certificate')
    tec_sub = tec_parser.add_subparsers(dest='tenant_edgeflow_certificate_command')
    p = tec_sub.add_parser('get', help='Get the tenant EdgeFlow certificate')
    p.set_defaults(func=cmd_tenant_ef_cert_get)
    p = tec_sub.add_parser('set', help='Set the tenant EdgeFlow certificate')
    p.add_argument('--body', help='JSON certificate/key body')
    p.set_defaults(func=cmd_tenant_ef_cert_set)
    p = tec_sub.add_parser('delete', help='Delete the tenant EdgeFlow certificate')
    p.set_defaults(func=cmd_tenant_ef_cert_delete)

    # cogniac tenant-meraki-key
    tmk_parser = _add_resource(subparsers, 'tenant-meraki-key', help='Tenant Meraki API key')
    tmk_sub = tmk_parser.add_subparsers(dest='tenant_meraki_key_command')
    p = tmk_sub.add_parser('delete', help='Delete the tenant Meraki API key')
    p.set_defaults(func=cmd_tenant_meraki_key_delete)

    # cogniac tenant-import <cloudcore_import_key>
    ti_parser = _add_resource(subparsers, 'tenant-import', help='CloudCore import payload')
    ti_parser.add_argument('cloudcore_import_key', help='CloudCore import key')
    ti_parser.set_defaults(func=cmd_tenant_import)

    # cogniac auth [login|logout]
    auth_parser = subparsers.add_parser(
        'auth',
        help='Check credentials, or log in/out. Bare `cogniac auth` checks credentials; '
             'if --tenant/COG_TENANT is set, verifies a session can be minted')
    # bare `cogniac auth` (no subcommand) keeps the existing credential-check behavior
    auth_parser.set_defaults(func=cmd_auth)
    auth_sub = auth_parser.add_subparsers(dest='auth_command')

    p = auth_sub.add_parser('login',
                            help='Log in via the browser and store a per-user API key (~/.config/cogniac/credentials)')
    p.add_argument('--no-browser', dest='no_browser', action='store_true',
                   help='Do not auto-open a browser; just print the login URL')
    p.set_defaults(func=cmd_auth_login)

    p = auth_sub.add_parser('logout', help='Remove the stored login credential')
    p.set_defaults(func=cmd_auth_logout)

    # cogniac user
    p = subparsers.add_parser('user', help='Show current user info and system roles')
    p.set_defaults(func=cmd_user)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

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
