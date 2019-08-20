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

    Record results of user judgement using cogniac view tool
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
        Add an item to operations review queue:

        connnection (CogniacConnection): Authenticated CogniacConnection object
        review_items: list of
            media_id: required
            detection_ids: optional list of processing records leading to this review
            detections: optional list of detections to highlight for user
                            subject_uid
                            probability
                            app_data_type
                            app_data

        review_unit: optional str, user specified identifier associated with the review of this
        media or group of media.  Often a “domain_unit” would be a
        natural choice	for this id but it is not required to be a domain
        unit. The only use for this field is for subsequent searching.
        """
        data = {'review_items': review_items}
        if review_unit:
            data['review_unit'] = review_unit

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
        get single item from operations review queue
        connnection (CogniacConnection): Authenticated CogniacConnection object

        return:
            review_id, cogniac supplied unique ID,
            review_items
            review_unit if any
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
        return number of pending items in operations review queue
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
        Report user judgement as result back to cogniac system for the given review_id

        connnection (CogniacConnection): Authenticated CogniacConnection object
        review_id (str): cogniac supplied unique ID, required.
        result (str): required user input, 'OK' or 'NG'
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
               time_start=None,
               time_end=None,
               reverse=True,
               limit=None):
        """
        search CogniacOpsReviewResults by time period
        filtered by media_id, review_unit, result

        connnection (CogniacConnection): Authenticated CogniacConnection object

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
        elif review_unit:
            data['review_unit'] = review_unit
        elif result:
            data['result'] = result
        else:
            data['reverse'] = reverse
            if time_start:
                data['start'] = time_start
            if time_end:
                data['end'] = time_end
            if limit:
                data['limit'] = limit

        resp = connection._get("/ops/results", json=data)
        print resp.json()
        subs = resp.json()['data']
        return [CogniacOpsReview(connection, s) for s in subs]

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
        Delete the op review result.
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
