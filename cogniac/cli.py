"""
Cogniac CLI - Agent-friendly command-line interface to the Cogniac API.

Outputs JSON (default) or table format. Errors are JSON on stderr.

Read commands:
    cog tenant
    cog tenants
    cog apps list
    cog apps get <application_id>
    cog subjects list
    cog subjects get <subject_uid>
    cog subjects search [--prefix P] [--name N] [--similar S] [--ids ID ...] [--limit L]
    cog subjects media <subject_uid> [--limit L] [--consensus C] [--probability-lower P] [--probability-upper P]
    cog media get <media_id>
    cog media search [--md5 M] [--filename F] [--external-media-id E] [--domain-unit D] [--limit L]
    cog edgeflows list
    cog edgeflows get <edgeflow_id>
    cog edgeflows status <edgeflow_id> [--subsystem S] [--limit L]
    cog cameras list
    cog cameras get <network_camera_id>
    cog deployments list
    cog deployments get <deployment_group_id>
    cog workflows get <workflow_id>
    cog version
    cog auth

Write commands:
    cog subjects create <name> [--description D] [--external-id E]
    cog subjects associate <subject_uid> <media_id> [--consensus C]
    cog media upload <filename> [--subject-uid S] [--external-media-id E] [--domain-unit D] [--meta-tags T ...]

Global options:
    --format json|table  (default: json)

Copyright (C) 2016 Cogniac Corporation.
"""

import argparse
import json
import sys
import os

from tabulate import tabulate

import requests

from .cogniac import CogniacConnection
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


def get_connection():
    """Create an authenticated CogniacConnection, or exit with JSON error."""
    try:
        return CogniacConnection()
    except CredentialError as e:
        error_exit("CredentialError", str(e))
    except Exception as e:
        error_exit("ConnectionError", str(e))


# -- Read command handlers --

def cmd_tenant(args):
    cc = get_connection()
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
    cc = get_connection()
    apps = cc.get_all_applications()
    output([obj_to_dict(a) for a in apps], args, 'app')


def cmd_apps_get(args):
    cc = get_connection()
    try:
        app = cc.get_application(args.application_id)
        output(obj_to_dict(app), args, 'app')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_subjects_list(args):
    cc = get_connection()
    subjects = cc.get_all_subjects()
    output([obj_to_dict(s) for s in subjects], args, 'subject')


def cmd_subjects_get(args):
    cc = get_connection()
    try:
        subject = cc.get_subject(args.subject_uid)
        output(obj_to_dict(subject), args, 'subject')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_subjects_search(args):
    cc = get_connection()
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
    cc = get_connection()
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
    cc = get_connection()
    try:
        media = cc.get_media(args.media_id)
        output(obj_to_dict(media), args, 'media')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_media_search(args):
    cc = get_connection()
    results = cc.search_media(
        md5=args.md5,
        filename=args.filename,
        external_media_id=args.external_media_id,
        domain_unit=args.domain_unit,
        limit=args.limit,
    )
    output([obj_to_dict(m) for m in results], args, 'media')


def cmd_edgeflows_list(args):
    cc = get_connection()
    edgeflows = cc.get_all_edgeflows()
    output([obj_to_dict(e) for e in edgeflows], args, 'edgeflow')


def cmd_edgeflows_get(args):
    cc = get_connection()
    try:
        edgeflow = cc.get_edgeflow(args.edgeflow_id)
        output(obj_to_dict(edgeflow), args, 'edgeflow')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_edgeflows_status(args):
    cc = get_connection()
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
    cc = get_connection()
    cameras = cc.get_all_cameras()
    output([obj_to_dict(c) for c in cameras], args, 'camera')


def cmd_cameras_get(args):
    cc = get_connection()
    try:
        camera = cc.get_camera(args.network_camera_id)
        output(obj_to_dict(camera), args, 'camera')
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_deployments_list(args):
    cc = get_connection()
    try:
        resp = cc.session.get(f"{cc.url_prefix}/1/tenants/{cc.tenant.tenant_id}/deploymentGroups", timeout=30)
        resp.raise_for_status()
        groups = json.loads(resp.text).get('data', [])
        output(groups, args, 'deployment')
    except Exception as e:
        error_exit("Error", str(e))


def cmd_deployments_get(args):
    cc = get_connection()
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
    cc = get_connection()
    try:
        resp = cc.session.get(f"{cc.url_prefix}/1/workflows/{args.workflow_id}", timeout=30)
        resp.raise_for_status()
        output(json.loads(resp.text), args, 'workflow')
    except Exception as e:
        error_exit("Error", str(e))


def cmd_version(args):
    cc = get_connection()
    output(cc.get_version(), args)


def cmd_auth(args):
    """Check that credentials are valid without making a full connection."""
    has_api_key = 'COG_API_KEY' in os.environ
    has_user_pass = 'COG_USER' in os.environ and 'COG_PASS' in os.environ
    has_tenant = 'COG_TENANT' in os.environ

    if not has_api_key and not has_user_pass:
        error_exit("AuthError", "No credentials found. Set COG_API_KEY or COG_USER+COG_PASS environment variables.")

    result = {
        "auth_method": "api_key" if has_api_key else "user_pass",
        "tenant_set": has_tenant,
    }

    if has_tenant:
        result["tenant_id"] = os.environ['COG_TENANT']

    url_prefix = os.environ.get('COG_URL_PREFIX', 'https://api.cogniac.io/')
    try:
        tenants = CogniacConnection.get_all_authorized_tenants(url_prefix=url_prefix)
        result["valid"] = True
        result["tenant_count"] = len(tenants.get('tenants', []))
        result["url_prefix"] = url_prefix
    except Exception as e:
        result["valid"] = False
        result["detail"] = str(e)

    output(result, args)


def cmd_user(args):
    """Show current user info including system roles."""
    # /1/users/current requires a tenant-scoped Bearer token.
    # If COG_TENANT is not set, pick the first available tenant.
    if 'COG_TENANT' not in os.environ:
        url_prefix = os.environ.get('COG_URL_PREFIX', 'https://api.cogniac.io/')
        try:
            result = CogniacConnection.get_all_authorized_tenants(url_prefix=url_prefix)
            tenants = result.get('tenants', [])
            if not tenants:
                error_exit("AuthError", "No authorized tenants found.")
                return
            os.environ['COG_TENANT'] = tenants[0]['tenant_id']
        except Exception as e:
            error_exit("AuthError", str(e))
            return
    cc = get_connection()
    resp = cc.session.get(cc.url_prefix + '/1/users/current')
    resp.raise_for_status()
    output(resp.json(), args, 'user')


# -- Write command handlers --

def cmd_subjects_create(args):
    cc = get_connection()
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
    cc = get_connection()
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
    cc = get_connection()
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
        prog='cog',
        description='Cogniac CLI - query and manage the Cogniac API (JSON or table output)',
    )
    parser.add_argument('--format', choices=['json', 'table'], default='json',
                        help='Output format (default: json)')
    subparsers = parser.add_subparsers(dest='command')

    # cog tenant
    p = subparsers.add_parser('tenant', help='Show current tenant info')
    p.set_defaults(func=cmd_tenant)

    # cog tenants
    p = subparsers.add_parser('tenants', help='List all authorized tenants')
    p.set_defaults(func=cmd_tenants)

    # cog version
    p = subparsers.add_parser('version', help='Show API version info')
    p.set_defaults(func=cmd_version)

    # cog apps
    apps_parser = subparsers.add_parser('apps', help='Applications')
    apps_sub = apps_parser.add_subparsers(dest='apps_command')

    p = apps_sub.add_parser('list', help='List all applications')
    p.set_defaults(func=cmd_apps_list)

    p = apps_sub.add_parser('get', help='Get a specific application')
    p.add_argument('application_id', help='Application ID')
    p.set_defaults(func=cmd_apps_get)

    # cog subjects
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

    # cog media
    media_parser = subparsers.add_parser('media', help='Media')
    media_sub = media_parser.add_subparsers(dest='media_command')

    p = media_sub.add_parser('get', help='Get a specific media item')
    p.add_argument('media_id', help='Media ID')
    p.set_defaults(func=cmd_media_get)

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

    # cog edgeflows
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

    # cog cameras
    cam_parser = subparsers.add_parser('cameras', help='Network cameras')
    cam_sub = cam_parser.add_subparsers(dest='cameras_command')

    p = cam_sub.add_parser('list', help='List all cameras')
    p.set_defaults(func=cmd_cameras_list)

    p = cam_sub.add_parser('get', help='Get a specific camera')
    p.add_argument('network_camera_id', help='Network camera ID')
    p.set_defaults(func=cmd_cameras_get)

    # cog deployments
    dep_parser = subparsers.add_parser('deployments', help='Deployment groups')
    dep_sub = dep_parser.add_subparsers(dest='deployments_command')

    p = dep_sub.add_parser('list', help='List all deployment groups')
    p.set_defaults(func=cmd_deployments_list)

    p = dep_sub.add_parser('get', help='Get a specific deployment group')
    p.add_argument('deployment_group_id', help='Deployment group ID')
    p.set_defaults(func=cmd_deployments_get)

    # cog workflows
    wf_parser = subparsers.add_parser('workflows', help='Workflows')
    wf_sub = wf_parser.add_subparsers(dest='workflows_command')

    p = wf_sub.add_parser('get', help='Get a specific workflow')
    p.add_argument('workflow_id', help='Workflow ID')
    p.set_defaults(func=cmd_workflows_get)

    # cog auth
    p = subparsers.add_parser('auth', help='Check credentials and connectivity')
    p.set_defaults(func=cmd_auth)

    # cog user
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
