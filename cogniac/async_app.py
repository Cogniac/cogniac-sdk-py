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
    #  application types
    ##
    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_all_types(cls, connection, production=None, deprecated=None, reverse=False):
        """
        Return the list of application types available to the authenticated tenant.

        See GET /1/applications/all/types.
        """
        params = {}
        if production is not None:
            params['production'] = production
        if deprecated is not None:
            params['deprecated'] = deprecated
        if reverse:
            params['reverse'] = True
        resp = await connection._get("/1/applications/all/types", params=params)
        return resp.json()

    @classmethod
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def get_type(cls, connection, application_type):
        """
        Return a single application type.

        See GET /1/applications/all/types/{application_type}.
        """
        resp = await connection._get("/1/applications/all/types/%s" % application_type)
        return resp.json()

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
        if name in self.mutable_keys:
            raise AttributeError("Use 'await app.set(%s=...)' to update server-managed attributes" % name)
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
    async def post_feedback(self, media_id, subjects, focus=None):
        """
        Provide feedback to the application for a given subject-media association.

        media_id (String):        Media ID to provide feedback on
        subjects (list of dicts): Subject-media association dictionaries:
            subject_uid:          Subject UID
            result (str):         One of 'True', 'False', 'Sidelined'
            app_data_type (str):  (Optional) type of extra app-specific data
            app_data (Object):    (Optional) additional app-specific data

        focus (dict, optional):   Focus within the media this feedback applies to. Required when
                                  the output subject's labels carry per-ROI focus (e.g. box_detection
                                  apps or focus-aware classifiers). Shape:
                                  {'box': {'x0': int, 'x1': int, 'y0': int, 'y1': int}}
                                  (and/or 'frame' for video). Note: a 'focus' key placed inside a
                                  subject dict is NOT read by the server — it must be passed here.
        """
        for s in subjects:
            s['media_id'] = media_id

        feedback_response = {'media_id': media_id,
                             'subjects': subjects}
        if focus is not None:
            feedback_response['focus'] = focus

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
            url = resp.get('paging', {}).get('next')

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
            url = resp.get('paging', {}).get('next')

    ##
    #  leaderboard
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def leaderboard(self,
                          set_assignment='validation',
                          snapshot_type='regular',
                          eval_metrics='primary'):
        """
        Return the most recent ranked snapshot of candidate models for this application,
        evaluated under the application's active evaluation metrics.

        set_assignment (str):  'validation' (default) or 'training'
        snapshot_type (str):   'regular' (default) or 'int8'
        eval_metrics (str):    'primary' (default) for the primary metric only, or 'all'
                               for results across all active metrics
        """
        for arg, val, choices in [
                ('set_assignment', set_assignment, ('validation', 'training')),
                ('snapshot_type', snapshot_type, ('regular', 'int8')),
                ('eval_metrics', eval_metrics, ('primary', 'all'))]:
            if val not in choices:
                raise ValueError("%s must be one of %s" % (arg, choices))

        url = "/22/applications/%s/leaderboard/recent_consensus_snapshot" % self.application_id
        params = {
            'set_assignment': set_assignment,
            'snapshot_type': snapshot_type,
            'eval_metrics': eval_metrics,
        }
        resp = await self._cc._get(url, params=params)
        return resp.json()

    ##
    #  evaluation_metrics
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def evaluation_metrics(self):
        """
        Return the list of active evaluation metrics for this application.
        """
        resp = await self._cc._get("/22/applications/%s/evaluation_metrics" % self.application_id)
        return resp.json()

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
            url = resp.get('paging', {}).get('next')

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

    ##
    #  classify
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def classify(self, image_file):
        """
        Run inference/classification on a single uploaded image.

        See POST /1/applications/{app_id}/classify.
        """
        with open(image_file, 'rb') as f:
            resp = await self._cc._post("/1/applications/%s/classify" % self.application_id,
                                       files={'file': f})
        return resp.json()

    ##
    #  donate_model
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def donate_model(self, source_application_id):
        """
        Donate the active model of source_application_id into this (target) application.

        See POST /1/applications/{app_id}/donateModel (this application is the target).
        """
        resp = await self._cc._post("/1/applications/%s/donateModel" % self.application_id,
                                   json={'source_application_id': source_application_id})
        return resp.json()

    ##
    #  export_model_to_meraki
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def export_model_to_meraki(self):
        """
        Export this application's active model to the tenant's Meraki organization.

        See POST /1/applications/{app_id}/exportModelToMeraki.
        """
        resp = await self._cc._post("/1/applications/%s/exportModelToMeraki" % self.application_id)
        return resp.json()

    ##
    #  replay
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def replay_status(self):
        """
        Return the current replay status for this application.

        See GET /1/applications/{app_id}/replay.
        """
        resp = await self._cc._get("/1/applications/%s/replay" % self.application_id)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def replay_start(self, body=None):
        """
        Start an application replay.

        See POST /1/applications/{app_id}/replay.
        """
        resp = await self._cc._post("/1/applications/%s/replay" % self.application_id,
                                   json=body if body is not None else {})
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def replay_stop(self):
        """
        Stop an in-progress application replay.

        See POST /1/applications/{app_id}/replay (with a stop request body).
        """
        resp = await self._cc._post("/1/applications/%s/replay" % self.application_id,
                                   json={'replay': False})
        return resp.json()

    ##
    #  detections_pending
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def detections_pending(self):
        """
        Return the count of pending (unreviewed) detections for this application.

        See GET /1/applications/{app_id}/detections/pending.
        """
        resp = await self._cc._get("/1/applications/%s/detections/pending" % self.application_id)
        return resp.json()

    ##
    #  event_types
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def event_types(self):
        """
        Return the list of available event types for this application.

        See GET /1/applications/{app_id}/eventTypes.
        """
        resp = await self._cc._get("/1/applications/%s/eventTypes" % self.application_id)
        return resp.json()

    ##
    #  events
    ##
    async def events(self, start=None, end=None, limit=None, cursor=None, reverse=False, event_types=None):
        """
        Async generator yielding application events sorted by timestamp.

        See GET /1/applications/{app_id}/events.
        """
        params = []
        if start is not None:
            params.append("start=%f" % start)
        if end is not None:
            params.append("end=%f" % end)
        if limit:
            assert(limit > 0)
            params.append('limit=%d' % limit)
        if cursor is not None:
            params.append("cursor=%s" % cursor)
        if reverse:
            params.append('reverse=True')
        if event_types:
            for et in event_types:
                params.append("event_types=%s" % et)

        url = "/1/applications/%s/events?" % self.application_id
        url += "&".join(params)

        @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
        async def get_next(url):
            resp = await self._cc._get(url)
            return resp.json()

        count = 0
        while url:
            resp = await get_next(url)
            for item in resp['data']:
                yield item
                count += 1
                if limit and count == limit:
                    return
            url = resp.get('paging', {}).get('next')

    ##
    #  consensus_history
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def consensus_history(self, start=None, end=None, limit=None, subject_uid=None):
        """
        Return consensus-history counts for this application's output subjects.

        See GET /1/applications/{app_id}/consensusHistory.
        """
        params = {}
        if start is not None:
            params['start'] = start
        if end is not None:
            params['end'] = end
        if limit is not None:
            params['limit'] = limit
        if subject_uid is not None:
            params['subject_uid'] = subject_uid
        resp = await self._cc._get("/1/applications/%s/consensusHistory" % self.application_id, params=params)
        return resp.json()

    async def _performance(self, kind, start=None, end=None, limit=None, reverse=False, duration=None):
        """Shared helper for the performance/* endpoints."""
        params = {}
        if start is not None:
            params['start'] = start
        if end is not None:
            params['end'] = end
        if limit is not None:
            params['limit'] = limit
        if reverse:
            params['reverse'] = True
        if duration is not None:
            params['duration'] = duration
        resp = await self._cc._get("/1/applications/%s/performance/%s" % (self.application_id, kind), params=params)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def performance_current_validation(self, start=None, end=None, limit=None, reverse=False, duration=None):
        """
        Return the current-validation performance series for this application.

        See GET /1/applications/{app_id}/performance/currentValidation.
        """
        return await self._performance('currentValidation', start=start, end=end, limit=limit,
                                       reverse=reverse, duration=duration)

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def performance_release_validation(self, start=None, end=None, limit=None, reverse=False, duration=None):
        """
        Return the release-validation performance series for this application.

        See GET /1/applications/{app_id}/performance/releaseValidation.
        """
        return await self._performance('releaseValidation', start=start, end=end, limit=limit,
                                       reverse=reverse, duration=duration)

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def performance_new_random(self, limit=None):
        """
        Return the new-random test-set performance for this application.

        See GET /1/applications/{app_id}/performance/newRandom.
        """
        params = {}
        if limit is not None:
            params['limit'] = limit
        resp = await self._cc._get("/1/applications/%s/performance/newRandom" % self.application_id, params=params)
        return resp.json()

    ##
    #  model_performance
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def model_performance(self, subject_uid, consensus=None, reverse=False,
                                probability_lower=None, probability_upper=None,
                                limit=None, cursor=None, set_assignment='validation'):
        """
        Return model performance data for a given subject of this application.

        See GET /1/applications/{app_id}/modelPerformance.
        """
        params = {'subject_uid': subject_uid, 'set_assignment': set_assignment}
        if consensus is not None:
            params['consensus'] = consensus
        if reverse:
            params['reverse'] = True
        if probability_lower is not None:
            params['probability_lower'] = probability_lower
        if probability_upper is not None:
            params['probability_upper'] = probability_upper
        if limit is not None:
            params['limit'] = limit
        if cursor is not None:
            params['cursor'] = cursor
        resp = await self._cc._get("/1/applications/%s/modelPerformance" % self.application_id, params=params)
        return resp.json()

    ##
    #  push notifications
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def push_notifications(self):
        """
        Return the push-notification subscriptions for this application.

        See GET /1/applications/{app_id}/pushNotifications.
        """
        resp = await self._cc._get("/1/applications/%s/pushNotifications" % self.application_id)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def subscribe_push(self, device_id=None, app_bundle_id=None, event_type=None, unsubscribe=False):
        """
        Subscribe (or unsubscribe) a device to this application's event topic.

        See POST /1/applications/{app_id}/pushNotifications.
        """
        data = {}
        if device_id is not None:
            data['device_id'] = device_id
        if app_bundle_id is not None:
            data['app_bundle_id'] = app_bundle_id
        if event_type is not None:
            data['event_type'] = event_type
        if unsubscribe:
            data['unsubscribe'] = True
        resp = await self._cc._post("/1/applications/%s/pushNotifications" % self.application_id, json=data)
        return resp.json()

    ##
    #  feedback
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def feedback(self, limit=10):
        """
        Return up to {limit} feedback items for this application.

        See GET /21/applications/{app_id}/feedback.
        """
        resp = await self._cc._get("/21/applications/%s/feedback?limit=%d" % (self.application_id, limit))
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def feedback_request(self, feedback_id):
        """
        Return a single feedback request for this application.

        See GET /21/applications/{app_id}/feedbackRequests/{feedback_id}.
        """
        resp = await self._cc._get("/21/applications/%s/feedbackRequests/%s" % (self.application_id, feedback_id))
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def submit_feedback(self, body):
        """
        Submit feedback for a feedback request.

        See POST /21/applications/{app_id}/feedback.
        """
        resp = await self._cc._post("/21/applications/%s/feedback" % self.application_id, json=body)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def feedback_request_count(self):
        """
        Return the count of feedback requests pending for the requesting user.

        See GET /21/applications/{app_id}/feedbackRequests/count.
        """
        resp = await self._cc._get("/21/applications/%s/feedbackRequests/count" % self.application_id)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def pending_feedback_requests(self, limit=1):
        """
        Return pending (unsatisfied) feedback requests for the caller.

        See GET /21/applications/{app_id}/feedbackRequests/pending.
        """
        resp = await self._cc._get("/21/applications/%s/feedbackRequests/pending?limit=%d" % (self.application_id, limit))
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def purge_feedback(self):
        """
        Purge feedback requests for this application.

        See POST /1/applications/{app_id}/feedback/purge.
        """
        await self._cc._post("/1/applications/%s/feedback/purge" % self.application_id)

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def delete_feedback_requests(self):
        """
        Delete all feedback requests for this application.

        See DELETE /21/applications/{app_id}/feedbackRequests.
        """
        resp = await self._cc._delete("/21/applications/%s/feedbackRequests" % self.application_id)
        try:
            return resp.json()
        except Exception:
            return None

    ##
    #  evaluation metrics (configuration; versioned /22/)
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def create_evaluation_metric(self, body):
        """
        Create an evaluation metric for this application.

        See POST /22/applications/{application_id}/evaluation_metrics.
        """
        resp = await self._cc._post("/22/applications/%s/evaluation_metrics" % self.application_id, json=body)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def register_default_evaluation_metric(self, body=None):
        """
        Register the default evaluation metric for a newly-created application.

        See POST /22/applications/{application_id}/evaluation_metrics/register_new_app_default.
        """
        resp = await self._cc._post(
            "/22/applications/%s/evaluation_metrics/register_new_app_default" % self.application_id,
            json=body if body is not None else {})
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def copy_evaluation_metrics(self, target_application_id, body=None):
        """
        Copy this application's evaluation metrics into a target application.

        This application is the *source*; see
        POST /22/applications/{source_application_id}/evaluation_metrics/copy.
        """
        data = dict(body) if body else {}
        data.setdefault('target_application_id', target_application_id)
        resp = await self._cc._post("/22/applications/%s/evaluation_metrics/copy" % self.application_id, json=data)
        return resp.json()

    ##
    #  consensus releases (versioned /22/)
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def consensus_releases(self):
        """
        List consensus releases for this application.

        See GET /22/applications/{app_id}/consensus_release.
        """
        resp = await self._cc._get("/22/applications/%s/consensus_release" % self.application_id)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def consensus_release(self, consensus_release_id):
        """
        Return metadata/statistics for a single consensus release.

        See GET /22/applications/{app_id}/consensus_release/{consensus_release_id}.
        """
        resp = await self._cc._get("/22/applications/%s/consensus_release/%s" % (self.application_id, consensus_release_id))
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def consensus_release_items(self, consensus_release_id, limit=None, cursor=None):
        """
        Download the consensus items for a consensus release.

        See GET /22/applications/{app_id}/consensus_release/{consensus_release_id}/consensus_items.
        """
        params = {}
        if limit is not None:
            params['limit'] = limit
        if cursor is not None:
            params['cursor'] = cursor
        resp = await self._cc._get(
            "/22/applications/%s/consensus_release/%s/consensus_items" % (self.application_id, consensus_release_id),
            params=params)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def consensus_release_upstream_assertions(self, consensus_release_id, limit=None, cursor=None):
        """
        Return the upstream assertions for a consensus release.

        See GET /22/applications/{app_id}/consensus_release/{consensus_release_id}/upstream_assertions.
        """
        params = {}
        if limit is not None:
            params['limit'] = limit
        if cursor is not None:
            params['cursor'] = cursor
        resp = await self._cc._get(
            "/22/applications/%s/consensus_release/%s/upstream_assertions" % (self.application_id, consensus_release_id),
            params=params)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def consensus_detection_release(self):
        """
        Return combined consensus detections for this application's output subjects.

        See GET /22/applications/{app_id}/consensus_detection_release.
        """
        resp = await self._cc._get("/22/applications/%s/consensus_detection_release" % self.application_id)
        return resp.json()

    ##
    #  labeling embedding model helpers (media-embedding; versioned /22/)
    ##
    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def labeling_image_encoder(self, body):
        """
        Get an image embedding from this application's labeling image-encoder model.

        See POST /22/applications/{app_id}/labelingImageEncoderModel.
        """
        resp = await self._cc._post("/22/applications/%s/labelingImageEncoderModel" % self.application_id, json=body)
        return resp.json()

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def labeling_mask_decoder(self, filep=None):
        """
        Retrieve this application's labeling mask-decoder model (ONNX).

        filep:  open file object (wb) to write the model into; if None the raw
                bytes are returned.

        See GET /22/applications/{application_id}/labelingMaskDecoderModel.
        """
        resp = await self._cc._get("/22/applications/%s/labelingMaskDecoderModel" % self.application_id)
        if filep is None:
            return resp.content
        filep.write(resp.content)

    @retry(stop=stop_after_attempt(8), wait=wait_exponential(multiplier=0.5), retry=retry_if_exception(server_error))
    async def labeling_mask_decoder_head(self):
        """
        Return the response headers for this application's labeling mask-decoder
        model without downloading the body (HEAD request).

        See HEAD /22/applications/{application_id}/labelingMaskDecoderModel.
        """
        resp = await self._cc._head("/22/applications/%s/labelingMaskDecoderModel" % self.application_id)
        return dict(resp.headers)
