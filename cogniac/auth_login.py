"""
Browser-loopback CLI login for the Cogniac SDK (`cogniac auth login`).

Implements the RFC 8252 "loopback redirect" pattern used by `gh auth login`,
`gcloud auth login`, and `aws sso login`:

    1. bind 127.0.0.1:<random ephemeral port>
    2. generate a `state` CSRF token
    3. open the browser at <web>/app/cli-auth?port=<port>&state=<state>
    4. the web consent page authenticates the existing web session
       (password OR SAML SSO), mints a tenant-less per-user API key via
       POST /1/users/<uid>/apiKeys, then redirects the browser to
       http://127.0.0.1:<port>/cb?code=<api_key>&state=<state>
    5. this loopback listener catches the redirect, verifies `state`, and
       hands the API key back to the caller.

This is the Phase 1 (MVP) flow from CloudCore-Product#1026: key-in-query with a
`state` CSRF guard, no backend changes. Phase 2 adds PKCE + a one-time-code
exchange.

Copyright (C) 2016 Cogniac Corporation.
"""

import html
import http.server
import secrets
import sys
import threading
import urllib.parse
import webbrowser

DEFAULT_COG_URL_PREFIX = "https://api.cogniac.io/"

# The consent page is served at the identical path in both the Ember and React
# frontends; the cog_app cookie routes the browser to whichever one the user is
# pinned to. The CLI is frontend-agnostic.
CLI_AUTH_PATH = "/app/cli-auth"

_SUCCESS_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Cogniac CLI login</title></head>
<body style="font-family:system-ui,sans-serif;text-align:center;margin-top:4rem">
<h2>You're logged in to the Cogniac CLI.</h2>
<p>You can close this tab and return to your terminal.</p>
</body></html>"""


def _failure_html(reason):
    return ("""<!doctype html><html><head><meta charset="utf-8">
<title>Cogniac CLI login</title></head>
<body style="font-family:system-ui,sans-serif;text-align:center;margin-top:4rem">
<h2>Cogniac CLI login failed.</h2>
<p>%s</p>
<p>Return to your terminal and try again.</p>
</body></html>""" % html.escape(reason or "unknown error"))


def web_base_url(api_url_prefix):
    """Derive the web-app origin (scheme://host[:port]) from the API url_prefix.

    Production splits the API onto an `api.` subdomain (api.cogniac.io) while the
    web app is served from the bare host (cogniac.io). On-prem / staging serve
    both from the same host, so only an explicit `api.` prefix is stripped.
    """
    p = urllib.parse.urlparse(api_url_prefix)
    netloc = p.netloc or p.path  # tolerate a bare host with no scheme
    scheme = p.scheme or "https"
    if netloc.startswith("api."):
        netloc = netloc[len("api."):]
    return "%s://%s" % (scheme, netloc)


def login(url_prefix=None, open_browser=True, timeout=300, out=sys.stderr):
    """Run the browser-loopback login flow and return (api_key, url_prefix).

    Raises Exception on timeout, state mismatch, or an error reported by the
    consent page. `out` receives human-readable progress (default stderr so it
    never pollutes CLI JSON on stdout).
    """
    if url_prefix is None:
        import os
        url_prefix = os.environ.get('COG_URL_PREFIX', DEFAULT_COG_URL_PREFIX)

    web_base = web_base_url(url_prefix)
    state = secrets.token_urlsafe(32)

    done = threading.Event()
    result = {}

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != "/cb":
                # ignore favicon.ico and any stray probes; keep listening
                self.send_response(404)
                self.end_headers()
                return
            params = {k: v[0] for k, v in urllib.parse.parse_qs(parsed.query).items()}
            err = params.get('error')
            recv_state = params.get('state')
            code = params.get('code')
            if err:
                result['error'] = "consent page reported: %s" % err
            elif not secrets.compare_digest(recv_state or "", state):
                result['error'] = "state mismatch (possible CSRF); login rejected"
            elif not code:
                result['error'] = "no credential returned by consent page"
            else:
                result['api_key'] = code

            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            body = _SUCCESS_HTML if 'api_key' in result else _failure_html(result.get('error'))
            self.wfile.write(body.encode('utf-8'))
            done.set()

        def log_message(self, *args):  # silence default request logging
            pass

    server = http.server.HTTPServer(('127.0.0.1', 0), _Handler)
    port = server.server_address[1]
    auth_url = "%s%s?%s" % (
        web_base, CLI_AUTH_PATH,
        urllib.parse.urlencode({"port": port, "state": state}),
    )

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    opened = open_browser and webbrowser.open(auth_url)
    if opened:
        out.write("Opened your browser to log in to Cogniac.\n")
    else:
        out.write("Open the following URL in your browser to log in to Cogniac:\n")
    out.write("\n    %s\n\n" % auth_url)
    out.write("Waiting for authentication (Ctrl-C to cancel)...\n")
    out.flush()

    try:
        finished = done.wait(timeout)
    finally:
        server.shutdown()

    if not finished:
        raise Exception("Timed out after %d seconds waiting for browser login." % timeout)
    if 'api_key' not in result:
        raise Exception(result.get('error', 'login failed'))

    return result['api_key'], url_prefix
