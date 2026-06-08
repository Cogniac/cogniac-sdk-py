"""
On-disk credential store for the Cogniac CLI/SDK.

`cogniac auth login` writes a tenant-less, per-user API key here so that
subsequent CLI/SDK invocations authenticate with no environment setup. The
store lives at ``$XDG_CONFIG_HOME/cogniac/credentials`` (default
``~/.config/cogniac/credentials``) and is written 0600.

This file is consumed as the lowest-precedence credential source: explicit
constructor arguments and the ``COG_*`` environment variables always win, so a
user can override the stored login at any time without logging out.

Copyright (C) 2016 Cogniac Corporation.
"""

import json
import os
import stat

DEFAULT_COG_URL_PREFIX = "https://api.cogniac.io/"


def config_dir():
    """Return the cogniac config directory path (honoring XDG_CONFIG_HOME)."""
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, 'cogniac')


def credentials_path():
    """Return the path to the on-disk credentials file."""
    return os.path.join(config_dir(), 'credentials')


def load_credentials():
    """Return the stored credentials dict, or None if no (readable) store exists."""
    path = credentials_path()
    try:
        with open(path, 'r') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get('api_key'):
        return None
    return data


def stored_api_key():
    """Return the stored API key, or None if there is no stored credential."""
    creds = load_credentials()
    return creds.get('api_key') if creds else None


def stored_url_prefix():
    """Return the url_prefix associated with the stored credential, or None."""
    creds = load_credentials()
    return creds.get('url_prefix') if creds else None


def save_credentials(api_key, url_prefix=None, **extra):
    """Persist an API key (0600) and return the file path.

    Extra keyword fields (e.g. label, created_at, hostname) are stored
    alongside for diagnostics/management.
    """
    d = config_dir()
    os.makedirs(d, mode=0o700, exist_ok=True)
    path = credentials_path()
    data = {"api_key": api_key}
    if url_prefix:
        data["url_prefix"] = url_prefix
    data.update(extra)

    # Write to a temp file then rename so we never expose a partial/world-readable file.
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
            f.write("\n")
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    os.replace(tmp, path)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return path


def delete_credentials():
    """Remove the stored credential file. Returns True if a file was removed."""
    path = credentials_path()
    try:
        os.unlink(path)
        return True
    except FileNotFoundError:
        return False
