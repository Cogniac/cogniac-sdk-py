"""
Async CogniacOpsReview Object Client

Copyright (C) 2016 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


class AsyncCogniacOpsReview(object):
    """
    AsyncCogniacOpsReview
    Async version of CogniacOpsReview.

    Record results of user judgement using the Cogniac view tool.
    Serves as a system of record and a point of comparison against results within the system.
    """

    ##
    #  create
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def create(cls, connection, review_items, review_unit=None):
        """
        Add an item to the operations review queue.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        review_items: list of dicts:
            media_id:       required
            detection_ids:  optional list of processing records
            detections:     optional list of detections to highlight:
                subject_uid, probability, app_data_type, app_data

        review_unit (str): optional user specified identifier for searching
        """
        data = {'review_items': review_items}
        if review_unit:
            data['review_unit'] = review_unit

        resp = await connection._post("/1/ops/review", json=data)
        return AsyncCogniacOpsReview(connection, resp.json())

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get(cls, connection):
        """
        Get a single item from the operations review queue.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object

        Returns: review_id, review_items, review_unit (if any)
        """
        resp = await connection._get("/1/ops/review")
        return AsyncCogniacOpsReview(connection, resp.json())

    ##
    #  get_pending
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_pending(cls, connection):
        """
        Return the number of pending items in the operations review queue.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        """
        resp = await connection._get("/1/ops/review/pending")
        return resp.json()['pending']

    ##
    #  create_result
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def create_result(cls, connection, review_id, result, comment=None):
        """
        Report user judgement as result back to the Cogniac system for the given review_id.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        review_id (str):                     cogniac supplied unique ID
        result (str):                        user input, 'OK' or 'NG'
        comment (str):                       optional comment
        """
        data = dict(review_id=review_id, result=result)
        if comment:
            data['comment'] = comment
        resp = await connection._post("/1/ops/results", json=data)
        return AsyncCogniacOpsReview(connection, resp.json())

    ##
    #  search
    ##
    @classmethod
    async def search(cls,
                     connection,
                     review_unit=None,
                     media_id=None,
                     external_media_id=None,
                     result=None,
                     start=None,
                     end=None,
                     reverse=True,
                     limit=None):
        """
        Async generator searching CogniacOpsReviewResults by time period,
        filtered by media_id, review_unit, or result.

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        start (Float):                       start time of the search period
        end (Float):                         end time of the search period
        reverse (Bool):                      order of returning results based on timestamp
        limit (int):                         max number of results to return
        media_id (String):                   filter by media_id
        external_media_id (String):          filter by external_media_id
        review_unit (String):                filter by review_unit
        result (String):                     filter by result ('OK' or 'NG')
        """
        args = []
        if start is not None:
            args.append("start=%f" % start)
        if end is not None:
            args.append("end=%f" % end)
        if reverse:
            args.append('reverse=True')
        if limit:
            assert(limit > 0)
            args.append('limit=%d' % min(limit, 100))
        if media_id is not None:
            args.append("media_id=%s" % media_id)
        if external_media_id is not None:
            args.append("external_media_id=%s" % external_media_id)
        if review_unit is not None:
            args.append("review_unit=%s" % review_unit)
        if result is not None:
            args.append("result=%s" % result)

        url = "/1/ops/results?"
        url += "&".join(args)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def get_next(url):
            resp = await connection._get(url)
            rjson = resp.json()
            return [AsyncCogniacOpsReview(connection, s) for s in rjson['data']], rjson.get('paging', {})

        count = 0
        while url:
            reviews, paging = await get_next(url)
            for review in reviews:
                yield review
                count += 1
                if limit and count == limit:
                    return
            url = paging.get('next')

    ##
    #  __init__
    ##
    def __init__(self, connection, review_dict):
        """
        Create an AsyncCogniacOpsReview.

        This is not normally called directly by users, instead use:
        AsyncCogniacOpsReview.create()
        """
        self._cc = connection
        self._sub_keys = review_dict.keys()
        for k, v in review_dict.items():
            super(AsyncCogniacOpsReview, self).__setattr__(k, v)

    ##
    #  delete
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete(self):
        """
        Delete the ops review result.
        """
        await self._cc._delete("/1/ops/review/%s" % self.review_id)

        for k in self._sub_keys:
            delattr(self, k)
        self._sub_keys = None
        self._cc = None

    def __setattr__(self, name, value):
        super(AsyncCogniacOpsReview, self).__setattr__(name, value)

    def __str__(self):
        return "%s" % (self.review_id)

    def __repr__(self):
        return self.__str__()
