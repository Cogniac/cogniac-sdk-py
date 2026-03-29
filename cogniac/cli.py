"""
Cogniac CLI - Agent-friendly command-line interface to the Cogniac API.

Outputs JSON to stdout. Errors are JSON on stderr.

Usage:
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
    cog cameras list
    cog cameras get <network_camera_id>
    cog edgeflows status <edgeflow_id> [--subsystem S] [--limit L]
    cog version
    cog auth

Copyright (C) 2016 Cogniac Corporation.
"""

import argparse
import json
import sys
import os

from .cogniac import CogniacConnection
from .common import CredentialError, ServerError, ClientError

# Attributes set by SDK internals, not from the API response
_INTERNAL_ATTRS = frozenset([
    'session', 'timeout', 'url_prefix', 'ip_address',
])


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


def output_json(data):
    """Print JSON to stdout."""
    print(json.dumps(data, indent=2, default=str))


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


# -- Command handlers --

def cmd_tenant(args):
    cc = get_connection()
    output_json(obj_to_dict(cc.tenant))


def cmd_tenants(args):
    url_prefix = os.environ.get('COG_URL_PREFIX', 'https://api.cogniac.io/')
    try:
        result = CogniacConnection.get_all_authorized_tenants(url_prefix=url_prefix)
        output_json(result)
    except CredentialError as e:
        error_exit("CredentialError", str(e))
    except Exception as e:
        error_exit("Error", str(e))


def cmd_apps_list(args):
    cc = get_connection()
    apps = cc.get_all_applications()
    output_json([obj_to_dict(a) for a in apps])


def cmd_apps_get(args):
    cc = get_connection()
    try:
        app = cc.get_application(args.application_id)
        output_json(obj_to_dict(app))
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_subjects_list(args):
    cc = get_connection()
    subjects = cc.get_all_subjects()
    output_json([obj_to_dict(s) for s in subjects])


def cmd_subjects_get(args):
    cc = get_connection()
    try:
        subject = cc.get_subject(args.subject_uid)
        output_json(obj_to_dict(subject))
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
    output_json([obj_to_dict(s) for s in subjects])


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
        output_json([a for a in associations])
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_media_get(args):
    cc = get_connection()
    try:
        media = cc.get_media(args.media_id)
        output_json(obj_to_dict(media))
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
    output_json([obj_to_dict(m) for m in results])


def cmd_edgeflows_list(args):
    cc = get_connection()
    edgeflows = cc.get_all_edgeflows()
    output_json([obj_to_dict(e) for e in edgeflows])


def cmd_edgeflows_get(args):
    cc = get_connection()
    try:
        edgeflow = cc.get_edgeflow(args.edgeflow_id)
        output_json(obj_to_dict(edgeflow))
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_cameras_list(args):
    cc = get_connection()
    cameras = cc.get_all_cameras()
    output_json([obj_to_dict(c) for c in cameras])


def cmd_cameras_get(args):
    cc = get_connection()
    try:
        camera = cc.get_camera(args.network_camera_id)
        output_json(obj_to_dict(camera))
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
        output_json([e for e in events])
    except ClientError as e:
        error_exit("ClientError", str(e))


def cmd_version(args):
    cc = get_connection()
    output_json(cc.get_version())


def cmd_auth(args):
    """Check that credentials are valid without making a full connection."""
    # Check env vars first
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

    # Validate credentials by listing tenants
    url_prefix = os.environ.get('COG_URL_PREFIX', 'https://api.cogniac.io/')
    try:
        tenants = CogniacConnection.get_all_authorized_tenants(url_prefix=url_prefix)
        result["valid"] = True
        result["tenant_count"] = len(tenants.get('tenants', []))
        result["url_prefix"] = url_prefix
    except Exception as e:
        result["valid"] = False
        result["detail"] = str(e)

    output_json(result)


# -- Parser construction --

def build_parser():
    parser = argparse.ArgumentParser(
        prog='cog',
        description='Cogniac CLI - query the Cogniac API (JSON output)',
    )
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

    # cog auth
    p = subparsers.add_parser('auth', help='Check credentials and connectivity')
    p.set_defaults(func=cmd_auth)

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
