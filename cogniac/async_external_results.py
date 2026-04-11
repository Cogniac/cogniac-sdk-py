"""
Async CogniacExternalResult Object Client

Copyright (C) 2016 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


class AsyncCogniacExternalResult(object):
    """
    AsyncCogniacExternalResult
    Async version of CogniacExternalResult.

    Record results of external inspections happening outside the Cogniac system.
    Serves as a system of record and a point of comparison against results within the system.
    """

    ##
    #  create
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def create(cls,
                     connection,
                     result_type,
                     result,
                     media_id=None,
                     domain_unit=None):
        """
        Create an AsyncCogniacExternalResult.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        result_type (String):                User defined name for the results, e.g. 'operator_ok_ng'
        result (String):                     User defined json string for the result, e.g. 'ok' or 'ng'
        media_id (String):                   Media_id associated with the result
        domain_unit (String):                Domain_unit associated with the result
        """
        data = dict(result_type=result_type, result=result)
        if media_id:
            data['media_id'] = media_id
        if domain_unit:
            data['domain_unit'] = domain_unit

        resp = await connection._post("/1/externalResults", json=data)
        return AsyncCogniacExternalResult(connection, resp.json())

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get(cls, connection, external_result_id):
        """
        Return an existing AsyncCogniacExternalResult.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        external_result_id (String):         The id of the external result to return
        """
        resp = await connection._get("/1/externalResults/%s" % external_result_id)
        return AsyncCogniacExternalResult(connection, resp.json())

    ##
    #  search
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def search(cls, connection, media_id=None, domain_unit=None,
                     time_start=None, time_end=None, reverse=True, limit=None):
        """
        Search AsyncCogniacExternalResults by media_id, domain_unit, or time period.
        Exactly one search method should be specified.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        media_id (String):                   media_id to look up
        domain_unit (String):                domain_unit to look up
        time_start (Float):                  start time of the search period
        time_end (Float):                    end time of the search period
        reverse (Bool):                      order of returning results based on timestamp
        limit (int):                         max number of results to return

        Returns list of AsyncCogniacExternalResult objects.
        """
        data = {}
        if media_id:
            data['media_id'] = media_id
        elif domain_unit:
            data['domain_unit'] = domain_unit
        else:
            data['reverse'] = reverse
            if time_start:
                data['time_start'] = time_start
            if time_end:
                data['time_end'] = time_end
            if limit:
                data['limit'] = limit

        resp = await connection._get("/1/externalResults", params=data)
        subs = resp.json()['data']
        return [AsyncCogniacExternalResult(connection, s) for s in subs]

    ##
    #  __init__
    ##
    def __init__(self, connection, external_result_dict):
        """
        Create an AsyncCogniacExternalResult.

        This is not normally called directly by users, instead use:
        AsyncCogniacExternalResult.create()
        """
        self._cc = connection
        self._sub_keys = external_result_dict.keys()
        for k, v in external_result_dict.items():
            super(AsyncCogniacExternalResult, self).__setattr__(k, v)

    ##
    #  delete
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete(self):
        """
        Delete the external result.
        """
        await self._cc._delete("/1/externalResults/%s" % self.external_result_id)

        for k in self._sub_keys:
            delattr(self, k)
        self._sub_keys = None
        self._cc = None

    def __setattr__(self, name, value):
        super(AsyncCogniacExternalResult, self).__setattr__(name, value)

    def __str__(self):
        return "%s" % (self.external_result_id)

    def __repr__(self):
        return self.__str__()
