"""
CogniacExternalResult Object Client

Copyright (C) 2016 Cogniac Corporation
"""

from retrying import retry
import six
import sys
from .common import server_error


##
#  Cogniac External Result
##
@six.python_2_unicode_compatible
class CogniacExternalResult(object):
    """
    CogniacExternalResult

    Record results of any external inspections that are happening outside the system.
    Serves as a system of record for those results as well as a point of comparison against results within the Cogniac system.
    """

    ##
    #  create
    ##
    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def create(cls,
               connection,
               result_type,
               result,
               media_id=None,
               domain_unit=None):
        """
        Create a CogniacExternalResult

        connnection (CogniacConnection): Authenticated CogniacConnection object
        result_type (String):            User defined name for the results, e.g. 'operator_ok_ng'
        result (String):                 User defined json string for the result, e.g. result='ok' or result='ng'
        media_id(String):                Media_id associated with the result if inspection is done on per media basis
        domain_unit(String):             Domain_unit associated with the result if inspection is done on per part basis
        """

        data = dict(result_type=result_type, result=result)
        if media_id:
            data['media_id'] = media_id
        if domain_unit:
            data['domain_unit'] = domain_unit

        resp = connection._post("/1/externalResults", json=data)
        return CogniacExternalResult(connection, resp.json())

    ##
    #  get
    ##
    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get(cls,
            connection,
            external_result_id):
        """
        return an existing CogniacExternalResult

        connnection (CogniacConnection): Authenticated CogniacConnection object
        external_result_id (String):     The id of the Cogniac External Result to return
        """
        resp = connection._get("/1/externalResults/%s" % external_result_id)
        return CogniacExternalResult(connection, resp.json())

    ##
    #  search
    ##
    @classmethod
    def search(cls, connection, media_id=None, domain_unit=None, time_start=None, time_end=None, reverse=True, limit=None):
        """
        search CogniacExternalResults in 3 ways: by media_id, domain_unit or time period, exactly one way should be specified.

        connnection (CogniacConnection): Authenticated CogniacConnection object

        media_id (String):               media_id to be looked up
        domain_unit(String):             domain_unit to be looked up

        time_start(Float):               start time of the search period
        time_end(Float):                 end time of the search period
        reverse(Bool):                   order of returning results based on timestamp
        limit (int):                      max number of results to return

        """

        # build the search args
        # perform only one search at a time
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

        resp = connection._get("/1/externalResults", json=data)
        print(resp.json())
        subs = resp.json()['data']
        return [CogniacExternalResult(connection, s) for s in subs]

    ##
    #  __init__
    ##
    def __init__(self, connection, external_result_dict):
        """
        create a CogniacExternalResult

        This is not normally called directly by users, instead use:
        CogniacExternalResult.create()
        """
        self._cc = connection
        self._sub_keys = external_result_dict.keys()
        for k, v in external_result_dict.items():
            super(CogniacExternalResult, self).__setattr__(k, v)

    ##
    #  delete
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def delete(self):
        """
        Delete the external result.
        """
        resp = self._cc._delete("/1/externalResults/%s" % self.external_result_id)

        for k in self._sub_keys:
            delattr(self, k)
        self._sub_keys = None
        self.connection = None

    def __setattr__(self, name, value):
        super(CogniacExternalResult, self).__setattr__(name, value)

    def __str__(self):
        return "%s" % (self.external_result_id)

    def __repr__(self):
        return self.__str__()
