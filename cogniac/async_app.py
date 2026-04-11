"""
Async CogniacApplication Object Client

Copyright (C) 2016 Cogniac Corporation
"""

from .common import retry, stop_after_attempt, wait_exponential, retry_if_exception, server_error


class AsyncCogniacApplication(object):
    """
    AsyncCogniacApplication
    Async version of CogniacApplication.

    Applications are the main locus of activity within the Cogniac System.

    Create a new application with AsyncCogniacApplication.create()
    Get an existing application with AsyncCogniacApplication.get()
    Get all tenant's applications with AsyncCogniacApplication.get_all()

    Use the async set() method to update mutable attributes.
    """

    mutable_keys = [
        'name', 'description', 'active', 'input_subjects', 'output_subjects',
        'app_managers', 'detection_post_urls', 'detection_thresholds',
        'subject_weights', 'custom_fields', 'app_type_config',
        'edgeflow_upload_policies', 'override_upstream_detection_filter',
        'feedback_resample_ratio', 'reviewers', 'inference_execution_policies',
        'primary_release_metric', 'secondary_evaluation_metrics'
    ]

    immutable_keys = ['application_id', 'created_at', 'created_by', 'modified_at', 'modified_by']

    ##
    #  create
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def create(cls,
                     connection,
                     name,
                     application_type,
                     description=None,
                     active=True,
                     input_subjects=None,
                     output_subjects=None,
                     app_managers=None,
                     app_type_config=None):
        """
        Create a new AsyncCogniacApplication

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        name (String):                       Name of new application
        application_type (String):           Cogniac Application Type name
        description (String):                Optional description
        active (Boolean):                    Application operational state
        input_subjects ([subjects]):         List of input subjects (UIDs or objects)
        output_subjects ([subjects]):        List of output subjects (UIDs or objects)
        app_managers ([String]):             List of email addresses for app managers
        app_type_config ({String: Any}):     Application-type-specific parameters
        """
        data = dict(name=name, active=active, type=application_type)

        if description:
            data['description'] = description
        if input_subjects:
            if type(input_subjects[0]) == str:
                data['input_subjects'] = input_subjects
            else:
                data['input_subjects'] = [s.subject_uid for s in input_subjects]
        if output_subjects:
            if type(output_subjects[0]) == str:
                data['output_subjects'] = output_subjects
            else:
                data['output_subjects'] = [s.subject_uid for s in output_subjects]

        if app_managers is not None:
            data['app_managers'] = app_managers

        if app_type_config is not None:
            data['app_type_config'] = app_type_config

        resp = await connection._post("/1/applications", json=data)
        return AsyncCogniacApplication(connection, resp.json())

    ##
    #  get
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get(cls, connection, application_id):
        """
        Return an existing AsyncCogniacApplication

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        application_id (String):             The application_id to return
        """
        resp = await connection._get("/1/applications/%s" % application_id)
        return AsyncCogniacApplication(connection, resp.json())

    ##
    #  get_all
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_all(cls, connection):
        """
        Return AsyncCogniacApplications for all applications belonging to the authenticated tenant

        connection (AsyncCogniacConnection): Authenticated AsyncCogniacConnection object
        """
        resp = await connection._get('/1/tenants/%s/applications' % connection.tenant_id)
        apps = resp.json()['data']
        return [AsyncCogniacApplication(connection, appd) for appd in apps]

    ##
    #  __init__
    ##
    def __init__(self, connection, application_dict):
        """
        Create a AsyncCogniacApplication

        This is not normally called directly by users, instead use:
        AsyncCogniacApplication.create() or AsyncCogniacApplication.get()
        """
        self._cc = connection
        self._app_keys = application_dict.keys()
        for k, v in application_dict.items():
            super(AsyncCogniacApplication, self).__setattr__(k, v)

    ##
    #  delete
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete(self):
        """
        Delete the application.
        This will delete existing models but will not delete associated subjects or media.
        """
        await self._cc._delete("/1/applications/%s" % self.application_id)

        for k in self._app_keys:
            delattr(self, k)
        self._app_keys = None
        self._cc = None

    ##
    #  set
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def set(self, **kwargs):
        """
        Update mutable application attributes via a single POST call.

        Accepted keys: name, description, active, input_subjects, output_subjects,
            app_managers, detection_post_urls, detection_thresholds, subject_weights,
            custom_fields, app_type_config, edgeflow_upload_policies,
            override_upstream_detection_filter, feedback_resample_ratio, reviewers,
            inference_execution_policies, primary_release_metric,
            secondary_evaluation_metrics

        Example:
            await app.set(name="new name", active=False)
        """
        for key in kwargs:
            if key in self.immutable_keys:
                raise AttributeError("%s is immutable" % key)
            if key not in self.mutable_keys:
                raise AttributeError("%s is not a recognized mutable attribute" % key)

        resp = await self._cc._post("/1/applications/%s" % self.application_id, json=kwargs)
        for k, v in resp.json().items():
            super(AsyncCogniacApplication, self).__setattr__(k, v)

    def __setattr__(self, name, value):
        if name in self.immutable_keys:
            raise AttributeError("%s is immutable" % name)
        super(AsyncCogniacApplication, self).__setattr__(name, value)

    def __str__(self):
        return "%s (%s)" % (self.name, self.application_id)

    def __repr__(self):
        return self.__str__()

    ##
    #  pending_feedback
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def pending_feedback(self):
        """
        Return the integer number of feedback requests pending for this application.
        """
        resp = await self._cc._get("/1/applications/%s/feedback/pending" % self.application_id)
        return resp.json()['pending']

    ##
    #  get_feedback
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_feedback(self, limit=10):
        """
        Returns a list of up to {limit} feedback request messages for the application.

        limit (Int):   Maximum number of feedback request messages to return
        """
        resp = await self._cc._get("/1/applications/%s/feedback?limit=%d" % (self.application_id, limit))
        return resp.json()

    ##
    #  post_feedback
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def post_feedback(self, media_id, subjects):
        """
        Provide feedback to the application for a given subject-media association.

        media_id (String):        Media ID to provide feedback on
        subjects (list of dicts): Subject-media association dictionaries:
            subject_uid:          Subject UID
            result (str):         One of 'True', 'False', 'Sidelined'
            app_data_type (str):  (Optional) type of extra app-specific data
            app_data (Object):    (Optional) additional app-specific data
        """
        for s in subjects:
            s['media_id'] = media_id

        feedback_response = {'media_id': media_id,
                             'subjects': subjects}

        await self._cc._post("/21/applications/%s/feedback" % self.application_id, json=feedback_response)

    ##
    #  models
    ##
    async def models(self, start=None, end=None, limit=None, reverse=True):
        """
        Async generator yielding model records for this application.

        start (float)   filter by timestamp > start
        end (float)     filter by timestamp < end
        limit (int)     max number of model_ids to yield
        reverse (bool)  sort high to low
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

        url = "/1/applications/%s/models?" % self.application_id
        url += "&".join(args)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def get_next(url):
            resp = await self._cc._get(url)
            return resp.json()

        model_ids = set()
        previous_model_id = None
        while url:
            resp = await get_next(url)
            for det in resp['data']:
                model_id = det['model_id']
                model_ids.add(model_id)
                yield det

                if limit and len(model_ids) >= limit:
                    if previous_model_id is not None and model_id != previous_model_id:
                        return
                previous_model_id = model_id
            url = resp['paging'].get('next')

    ##
    #  detections
    ##
    async def detections(self, start=None, end=None, reverse=True,
                         probability_lower=None, probability_upper=None,
                         limit=None, consensus_none=False, only_user=False,
                         only_model=False, abridged_media=True):
        """
        Async generator yielding application output assertions (model predictions and/or user feedback).

        start (float)          filter by timestamp > start (seconds since epoch)
        end (float)            filter by timestamp < end   (seconds since epoch)
        reverse (bool)         reverse the sorting order
        probability_lower:     filter by probability > probability_lower
        probability_upper:     filter by probability < probability_upper
        limit (int)            yield maximum of limit results
        consensus_none (bool): only return items without consensus
        only_user (bool):      only user feedback assertions
        only_model (bool):     only model prediction assertions
        abridged_media (bool)  return abridged media items if True
        """
        args = []
        if start is not None:
            args.append("start=%f" % start)
        if end is not None:
            args.append("end=%f" % end)
        if probability_lower is not None:
            args.append("probability_lower=%f" % probability_lower)
        if probability_upper is not None:
            args.append("probability_upper=%f" % probability_upper)
        if reverse:
            args.append('reverse=True')
        if limit:
            assert(limit > 0)
            args.append('limit=%d' % min(limit, 100))
        if consensus_none:
            args.append("consensus_none=True")
        if only_user:
            args.append("only_user=True")
        if only_model:
            args.append("only_model=True")
        if abridged_media:
            args.append('abridged_media=True')

        url = "/1/applications/%s/detections?" % self.application_id
        url += "&".join(args)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def get_next(url):
            resp = await self._cc._get(url)
            return resp.json()

        count = 0
        while url:
            resp = await get_next(url)
            for det in resp['data']:
                yield det
                count += 1
                if limit and count == limit:
                    return
            url = resp['paging'].get('next')

    ##
    #  usage
    ##
    async def usage(self, start, end):
        """
        Async generator yielding sparse app usage records between start and end epoch times.
        """
        url = "/1/usage/app/%s?start=%d&end=%d" % (self.application_id, start, end)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.005), retry=retry_if_exception(server_error))
        async def get_next(url):
            resp = await self._cc._get(url)
            return resp.json()

        while url:
            resp = await get_next(url)
            for record in resp['data']:
                yield record
            url = resp['paging'].get('next')

    ##
    #  accumulate_usage
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def accumulate_usage(self, start, end):
        """
        Return single cumulative app usage record for start to end epoch times.
        """
        url = "/1/usage/app/%s?start=%d&end=%d&accumulate=True" % (self.application_id, start, end)
        resp = await self._cc._get(url)
        data = resp.json()['data']
        return data[0] if len(data) else None
