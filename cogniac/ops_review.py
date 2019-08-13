"""
CogniacOpsReview Object Client

Copyright (C) 2016 Cogniac Corporation
"""

from retrying import retry
import sys
from common import server_error


##
#  Cogniac Ops Review
##
class CogniacOpsReview(object):
    """
    CogniacOpsReview

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
               review_items,
               review_unit=None):
        """
        Create a CogniacOpsReview

        connnection (CogniacConnection): Authenticated CogniacConnection object
        result_type (String):            User defined name for the results, e.g. 'operator_ok_ng'
        result (String):                 User defined json string for the result, e.g. result='ok' or result='ng'
        media_id(String):                Media_id associated with the result if inspection is done on per media basis
        domain_unit(String):             Domain_unit associated with the result if inspection is done on per part basis
        """
        data = {}
        if review_unit:
            data['review_unit'] = review_unit
        if review_items:
            data['review_items'] = review_items

        resp = connection._post("/ops/review", json=data)
        return CogniacOpsReview(connection, resp.json())

    ##
    #  get
    ##
    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get(cls,
            connection):
        """
        return an existing CogniacOpsReview

        connnection (CogniacConnection): Authenticated CogniacConnection object
        """
        resp = connection._get("/ops/review")
        return CogniacOpsReview(connection, resp.json())

    ##
    #  get pending
    ##
    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def get_pending(cls,
                    connection):
        """
        return an existing CogniacOpsReview

        connnection (CogniacConnection): Authenticated CogniacConnection object
        """
        resp = connection._get("/ops/review/pending")
        return resp.json()['pending']

    ##
    #  update with result
    ##
    @classmethod
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def create_result(cls,
                      connection,
                      review_id,
                      result):
        """
        return an existing CogniacOpsReview

        connnection (CogniacConnection): Authenticated CogniacConnection object
        """
        data = dict(review_id=review_id, result=result)
        resp = connection._post("/ops/results", json=data)
        return CogniacOpsReview(connection, resp.json())

    ##
    #  search
    ##
    @classmethod
    def search(cls,
               connection,
               review_unit=None,
               media_id=None,
               result=None,
               start=None,
               end=None,
               reverse=True,
               limit=None):
        """
        search CogniacOpsReviewResults in 3 ways:
        by media_id, domain_unit or time period, exactly one way should be specified.

        connnection (CogniacConnection): Authenticated CogniacConnection object

        media_id (String):               media_id to be looked up
        domain_unit(String):             domain_unit to be looked up

        start(Float):                    start time of the search period
        end(Float):                      end time of the search period
        reverse(Bool):                   order of returning results based on timestamp
        limit (int):                     max number of results to return

        """

        # build the search args
        # perform only one search at a time
        args = []
        if start is not None:
            args.append("start=%f" % start)
        if end is not None:
            args.append("end=%f" % end)

        if reverse:
            args.append('reverse=True')
        if limit:
            assert(limit > 0)
            args.append('limit=%d' % min(limit, 100))  # api support max limit of 100

        if media_id is not None:
            args.append("media_id=%s" % media_id)
        if review_unit is not None:
            args.append("review_unit=%s" % review_unit)
        if result is not None:
            args.append("result=%s" % result)
        url = "/ops/results?"
        url += "&".join(args)

        @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
        def get_next(url):
            resp = connection._get(url)
            return resp.json()

        count = 0
        while url:
            resp = get_next(url)
            for det in resp['data']:
                yield det
                count += 1
                if limit and count == limit:
                    return
            url = resp['paging'].get('next')

    ##
    #  __init__
    ##
    def __init__(self, connection, review_dict):
        """
        create a CogniacOpsReview

        This is not normally called directly by users, instead use:
        CogniacOpsReview.create()
        """
        self._cc = connection
        self._sub_keys = review_dict.keys()
        for k, v in review_dict.items():
            super(CogniacOpsReview, self).__setattr__(k, v)

    ##
    #  delete
    ##
    @retry(stop_max_attempt_number=8, wait_exponential_multiplier=500, retry_on_exception=server_error)
    def delete(self):
        """
        Delete the external result.
        """
        resp = self._cc._delete("/ops/review/%s" % self.review_id)

        for k in self._sub_keys:
            delattr(self, k)
        self._sub_keys = None
        self.connection = None

    def __setattr__(self, name, value):
        super(CogniacOpsReview, self).__setattr__(name, value)

    def __str__(self):
        s = "%s" % (self.review_id)
        return s.encode(sys.stdout.encoding)

    def __repr__(self):
        s = "%s" % (self.review_id)
        return s.encode(sys.stdout.encoding)
