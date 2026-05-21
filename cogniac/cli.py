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

from .cogniac import CogniacConnection

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
    url_prefix = os.environ.get('COG_URL_PREFIX', 'https://api.cogniac.io/')
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
    try:
        resp = cc.session.get(f"{cc.url_prefix}/1/tenants/{cc.tenant.tenant_id}/deploymentGroups", timeout=30)
        resp.raise_for_status()
        groups = json.loads(resp.text).get('data', [])
        output(groups, args, 'deployment')
    except Exception as e:
        error_exit("Error", str(e))


def cmd_deployments_get(args):
    cc = get_connection(args)
    try:
        resp = cc.session.get(f"{cc.url_prefix}/1/tenants/{cc.tenant.tenant_id}/deploymentGroups", timeout=30)
        resp.raise_for_status()
        groups = json.loads(resp.text).get('data', [])
        match = [g for g in groups if g.get('deployment_group_id') == args.deployment_group_id]
        if not match:
            error_exit("NotFound", f"Deployment group {args.deployment_group_id} not found")
        output(match[0], args, 'deployment')
    except Exception as e:
        error_exit("Error", str(e))


def cmd_workflows_get(args):
    cc = get_connection(args)
    try:
        resp = cc.session.get(f"{cc.url_prefix}/1/workflows/{args.workflow_id}", timeout=30)
        resp.raise_for_status()
        output(json.loads(resp.text), args, 'workflow')
    except Exception as e:
        error_exit("Error", str(e))


def cmd_version(args):
    cc = get_connection(args)
    output(cc.get_version(), args)


def cmd_auth(args):
    """Check credentials. If a tenant is specified (via --tenant or COG_TENANT),
    also verify that a real session can be minted against it via /1/token."""
    has_api_key = 'COG_API_KEY' in os.environ
    has_user_pass = 'COG_USER' in os.environ and 'COG_PASS' in os.environ
    flag_tenant = getattr(args, 'tenant', None)
    env_tenant = os.environ.get('COG_TENANT')
    effective_tenant = flag_tenant or env_tenant

    if not has_api_key and not has_user_pass:
        error_exit("AuthError", "No credentials found. Set COG_API_KEY or COG_USER+COG_PASS environment variables.")

    result = {
        "auth_method": "api_key" if has_api_key else "user_pass",
        "tenant_set": effective_tenant is not None,
    }

    if effective_tenant:
        result["tenant_id"] = effective_tenant
        result["tenant_source"] = "flag" if flag_tenant else "env"

    url_prefix = os.environ.get('COG_URL_PREFIX', 'https://api.cogniac.io/')
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


# -- Parser construction --

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

    # cogniac apps
    apps_parser = subparsers.add_parser('apps', help='Applications')
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

    p = apps_sub.add_parser('eval-metrics',
                            help='List active evaluation metrics for an application')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_apps_eval_metrics_list)

    # cogniac subjects
    subjects_parser = subparsers.add_parser('subjects', help='Subjects')
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

    # cogniac media
    media_parser = subparsers.add_parser('media', help='Media')
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

    # cogniac edgeflows
    ef_parser = subparsers.add_parser('edgeflows', help='EdgeFlow devices')
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

    # cogniac cameras
    cam_parser = subparsers.add_parser('cameras', help='Network cameras')
    cam_sub = cam_parser.add_subparsers(dest='cameras_command')

    p = cam_sub.add_parser('list', help='List all cameras')
    p.set_defaults(func=cmd_cameras_list)

    p = cam_sub.add_parser('get', help='Get a specific camera')
    p.add_argument('network_camera_id', help='Network camera ID')
    p.set_defaults(func=cmd_cameras_get)

    # cogniac deployments
    dep_parser = subparsers.add_parser('deployments', help='Deployment groups')
    dep_sub = dep_parser.add_subparsers(dest='deployments_command')

    p = dep_sub.add_parser('list', help='List all deployment groups')
    p.set_defaults(func=cmd_deployments_list)

    p = dep_sub.add_parser('get', help='Get a specific deployment group')
    p.add_argument('deployment_group_id', help='Deployment group ID')
    p.set_defaults(func=cmd_deployments_get)

    # cogniac workflows
    wf_parser = subparsers.add_parser('workflows', help='Workflows')
    wf_sub = wf_parser.add_subparsers(dest='workflows_command')

    p = wf_sub.add_parser('get', help='Get a specific workflow')
    p.add_argument('workflow_id', help='Workflow ID')
    p.set_defaults(func=cmd_workflows_get)

    # cogniac auth
    p = subparsers.add_parser('auth', help='Check credentials; if --tenant/COG_TENANT is set, verify a session can be minted')
    p.set_defaults(func=cmd_auth)

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
