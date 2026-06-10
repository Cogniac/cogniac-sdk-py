"""
CogniacBuild Object Client (integration build service)

Copyright (C) 2024 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


##
#  CogniacBuild
##
class CogniacBuild(object):
    """
    CogniacBuild

    Builds, lints, and stores Cogniac integration artifacts for in-app code.

    Get an existing build with CogniacBuild.get(); list builds with
    CogniacBuild.get_all().
    """

    ##
    #  get_all
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get_all(cls, connection, application_id=None):
        """
        Return builds, optionally filtered to a single application.

        application_id (str):  optionally restrict to builds for one application

        See GET /1/builds and GET /1/builds/application/{app_id}.
        """
        if application_id is not None:
            resp = connection._get("/1/builds/application/%s" % application_id)
        else:
            resp = connection._get("/1/builds")
        data = resp.json()
        items = data.get('data', data) if isinstance(data, dict) else data
        return [CogniacBuild(connection, b) for b in items]

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def get(cls, connection, build_id):
        """
        Return a single build by build_id.

        See GET /1/builds/{build_id}.
        """
        resp = connection._get("/1/builds/%s" % build_id)
        return CogniacBuild(connection, resp.json())

    ##
    #  create
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def create(cls, connection, body):
        """
        Create (request) a new build.

        body (dict):  build request body

        See POST /1/builds.
        """
        resp = connection._post("/1/builds", json=body)
        return CogniacBuild(connection, resp.json())

    ##
    #  names
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def names(cls, connection):
        """
        Return the list of known build names.

        See GET /1/builds/names.
        """
        resp = connection._get("/1/builds/names")
        return resp.json()

    ##
    #  lint
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def lint(cls, connection, filename):
        """
        Lint (flake8) a local source file via the build service.

        filename (str):  path to a local file to lint

        See POST /1/builds/lint/flake8.
        """
        with open(filename, 'rb') as f:
            resp = connection._post("/1/builds/lint/flake8", files={'file': f})
        return resp.json()

    def __init__(self, connection, build_dict):
        self._cc = connection
        self._build_keys = build_dict.keys()
        for k, v in build_dict.items():
            super(CogniacBuild, self).__setattr__(k, v)

    def __str__(self):
        return "%s" % getattr(self, 'build_id', '?')

    def __repr__(self):
        return self.__str__()

    ##
    #  delete
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    def delete(self):
        """
        Delete this build.

        See DELETE /1/builds/{build_id}.
        """
        self._cc._delete("/1/builds/%s" % self.build_id)
