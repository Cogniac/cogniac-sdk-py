from IPython.core.magic import (register_line_magic, register_cell_magic,
                                register_line_cell_magic)

import cogniac
from tabulate import tabulate
from datetime import datetime
import os
import time_range
from sys import argv

__builtins__['cc'] = None
__builtins__['S'] = None


def print_tenants(tenants):
    tenants.sort(key=lambda x: x['name'])
    data = [['tenant_id', 'name']]
    for tenant in tenants:
        data.append([tenant['tenant_id'], tenant['name']])
    print tabulate(data, headers='firstrow')


@register_line_magic
def tenants(line):
    tenants = cogniac.CogniacConnection.get_all_authorized_tenants(username, password)['tenants']
    print_tenants(tenants)

print "added ipython magic %tenants"


class Subjects(object):
    def __init__(self):
        count = 0
        for subject in cc.get_all_subjects():
            key = subject.subject_uid.replace('-', '_')  # workaround for some unclean legacy subject_uid
            self.__setattr__(key, subject)
            count += 1
        print 'added', count, 'subjects'


@register_line_magic
def authenticate(tenant_id):
    """
    authenticate to the specified tenant_id
    store CogniacConnection in cc object
    load all Cogniac Subjects into S object
    """
    cc = cogniac.CogniacConnection(tenant_id=tenant_id)
    __builtins__['cc'] = cc  # workaround ipython silliness
    print cc.tenant
    print "Adding all subjects to S"
    S = Subjects()
    __builtins__['S'] = S
    print "Type S.<tab> to autocomplete subjects"
print "added ipython magic %authenticate"


def print_detections(detections):
    # remove None values from dict
    detections = [{k: v for k, v in d.items() if v is not None} for d in detections]

    detections.sort(key=lambda x: x['created_at'])

    for d in detections:
        if 'activation' in d:
            del d['activation']
        value = datetime.fromtimestamp(d['created_at'])
        d['created_at'] = value.strftime('%Y-%m-%d %H:%M:%S')
    print tabulate(detections, headers='keys')


@register_line_magic
def media_detections(media_id):
    "print media detections for the specified media_id"
    try:
        media = cc.get_media(media_id)
    except:
        print "media_id %s not found" % media_id
        return
    print_detections(media.detections())
print "added ipython magic %media_detections"


def print_subjects(media_subjects):
    subjects = [ms['subject'] for ms in media_subjects]
    subjects = [{k: v for k, v in s.items() if v is not None} for s in subjects]
    subjects.sort(key=lambda x: x['updated_at'])
    for s in subjects:
        if 'timestamp' in s:
            del s['timestamp']
        value = datetime.fromtimestamp(s['updated_at'])
        s['updated_at'] = value.strftime('%Y-%m-%d %H:%M:%S')
    print tabulate(subjects, headers='keys')


@register_line_magic
def media_subjects(media_id):
    "print subject media associations for the specified media_id"
    try:
        media = cc.get_media(media_id)
    except:
        print "media_id %s not found" % media_id
        return

    print_subjects(media.subjects())
print "added ipython magic %media_subjects"


@register_line_magic
def users(line):
    def user_to_list(u):
        try:
            last = datetime.fromtimestamp(float(u['last_auth']))
            last = last.strftime('%Y-%m-%d %H:%M:%S')
        except:
            last = ""
        return [u['given_name'] + " " + u['surname'], u['email'], u['role'], last, u['user_id']]
    print "Users for tenant %s (%s)" %  (cc.tenant.name, cc.tenant.tenant_id)
    users = cc.tenant.users()
    users.sort(key=lambda x: x['last_auth'])
    data = [['name', 'email', 'tenant_role', 'last_auth', 'user_id']]
    for user in users:
        data.append(user_to_list(user))
    print tabulate(data, headers='firstrow')



@register_line_magic
def timeranges(line):
    """
    print list of valid timeframe selector strings, their corresponding current values, and description
    """
    time_range.help()
print "added ipython magic %timeranges"


def tenant_usage_convert_for_display(ur):
    value = datetime.fromtimestamp(ur['start_time'])
    ur['start_time'] = value.strftime('%Y-%m-%d %H:%M:%S')
    value = datetime.fromtimestamp(ur['end_time'])
    ur['end_time'] = value.strftime('%Y-%m-%d %H:%M:%S')
    ur['app_count'] = len(ur['active_model_apps'])
    gb = float(ur.get('media_bytes', 0)) / 1e9
    if gb < 1000:
        ur['media_GB'] = round(gb, 1)
    else:
        ur['media_GB'] = round(gb, 0)
    if 'media_count' not in ur:
        ur['media_count'] = 0


@register_line_magic
def usage(line):

    if line in time_range.timeframes:
        timerange_str = line
        period = None
    elif ' ' in line:
        timerange_str, period = line.split(' ')
    else:
        timerange_str, period  = "day", "hour"

    start_time, end_time = time_range.start_end_times(timerange_str)
    print 'tenant id:\t', cc.tenant.tenant_id
    print 'tenant name:\t', cc.tenant.name
    print 'report start\t', datetime.fromtimestamp(start_time).strftime('%Y-%m-%d %H:%M:%S')
    print 'report end\t', datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M:%S')
    print

    if not period:
        if end_time - start_time >= (60*60*24*7):
            period = "day"
        elif end_time - start_time >= (60*60*6):
            period = 'hour'
        else:
            period = '15min'

    usage = list(cc.tenant.usage(start_time, end_time, period=period))
    for ur in usage:
        tenant_usage_convert_for_display(ur)

    tenant_headers = ['start_time', 'end_time', 'amu', 'model_outputs', 'user_feedback', 'other_outputs', 'app_count', 'media_count', 'media_GB']

    data = [tenant_headers] + [[d.get(h) for h in tenant_headers] for d in usage]
    print tabulate(data, headers='firstrow')
print "added ipython magic %usage"

try:
    username = os.environ['COG_USER']
    password = os.environ['COG_PASS']
    print "found environment credentials for %s" % username
except:
    print "No Cogniac Credentials. Specify username and password or set COG_USER and COG_PASS environment variables."
    os._exit(1)


@register_line_magic
def login(tname):
    """
    attempt to match user supplied partial tenant name or tenant_id 
    authenticate with the matched tenant
    """
    tenant_list = cogniac.CogniacConnection.get_all_authorized_tenants(username, password)['tenants']
    def match(t):
        return tname.lower() in t['name'].lower() or tname in t['tenant_id']
    filter_tenant_list = filter(match, tenant_list)
    if len(filter_tenant_list) == 1:
        authenticate(filter_tenant_list[0]['tenant_id'])  # use tenant from command line
    elif len(filter_tenant_list) > 1:
        print_tenants(filter_tenant_list)  # show tenants that match
    else:
        print_tenants(tenant_list)  # show all tenants


if 'COG_TENANT' in os.environ:
    tenant_id = os.environ['COG_TENANT']
    print "found COG_TENANT %s" % tenant_id
    authenticate(tenant_id)
else:
    login(argv[-1])
