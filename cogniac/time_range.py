"""
helper functions for dealing with time ranges

Copyright (C) 2018 Cogniac Corporation
"""

from time import time
import datetime


class UnknownTimeframe(Exception):
    """
    unknown timeframe specification
    """


timeframes = {
    "minute":         "last minute",
    "hour":           "last hour",
    "day":            "last 24 hours until now",
    "week":           "last 7 days (7*24 hours) until now",
    "month":          "last 31 days until now",
    "previous-month": "previous calendar month",
    "-month":         "previous calendar month (alias)",
    "halfmonth":      "first 15 days of month for midmonth service usage tracking",
    "current-day":    "current calendar day until now",
    "today":          "current calendar day until now (alias)",
    "yesterday":      "previous calendar day (alias)",
    "current-month":  "current calendar month until now",
    "previous-day":   "previous calendar day"
    }


def start_end_times(timeframe_str):
    """
    return unix timestamps for the start time and end time corresponding to the
    user-supplied timeframe_str:

    "minute":         last minute
    "hour":           last hour
    "day":            last 24 hours until now
    "week":           last 7 days (7*24 hours) until now
    "month":          last 31 days until now
    "previous-month": previous calendar month
    "-month":         previous calendar month (alias)
    "halfmonth":      first 15 days of month for midmonth service usage tracking
    "current-day":    current calendar day until now
    "today"           current calendar day until now (alias)
    "current-month":  current calendar month until now
    "previous-day":   previous calendar day
    "yesterday":      previous calendar day (alias)

    """
    # TODO
    """
    "previous-week"
    "previous-day"

    """
    time_end = time()   # query filter end time
    dt_now = datetime.datetime.now()

    if timeframe_str == 'minute':
        time_start = time_end - 60
    elif timeframe_str == 'hour':
        time_start = time_end - 60*60
    elif timeframe_str == 'day':
        time_start = time_end - 24*60*60
    elif timeframe_str == 'week':
        time_start = time_end - 24*60*60*7
    elif timeframe_str == 'month':
        time_start = time_end - 24*60*60*31
    elif timeframe_str == '-month' or timeframe_str == "previous-month":
        last_month = dt_now.month-1
        if last_month == 0:
            last_month = 12
        start_year = dt_now.year
        if last_month > dt_now.month:
            start_year -= 1
        dt_start = datetime.datetime(start_year, last_month, 1)
        dt_end = datetime.datetime(dt_now.year, dt_now.month, 1)
        time_start = float(dt_start.strftime('%s'))
        time_end = float(dt_end.strftime('%s'))
    elif timeframe_str == 'halfmonth':
        dt_start = datetime.datetime(dt_now.year, dt_now.month, 1)
        dt_end = datetime.datetime(dt_now.year, dt_now.month, 16)
        time_start = float(dt_start.strftime('%s'))
        time_end = float(dt_end.strftime('%s'))
    elif timeframe_str == 'today' or timeframe_str == "current-day":
        dt_start = datetime.datetime(dt_now.year, dt_now.month, dt_now.day, 0, 0, 0)
        dt_end = dt_now
        time_start = float(dt_start.strftime('%s'))
        time_end = float(dt_end.strftime('%s'))
    elif timeframe_str == "current-month":
        dt_start = datetime.datetime(dt_now.year, dt_now.month, 1, 0, 0, 0)
        dt_end = dt_now
        time_start = float(dt_start.strftime('%s'))
        time_end = float(dt_end.strftime('%s'))
    elif timeframe_str == 'yesterday' or timeframe_str == "previous-day":
        dt_start = datetime.date.today() - datetime.timedelta(days=1)
        dt_end = datetime.date.today()
        time_start = float(dt_start.strftime('%s'))
        time_end = float(dt_end.strftime('%s'))
    else:
        raise UnknownTimeframe(timeframe_str)

    return time_start, time_end



def help():
    for period in timeframes:
        time_start, time_end = start_end_times(period)
        print "%20s  %s  %s  %s" % (period, datetime.datetime.fromtimestamp(time_start).strftime('%Y-%m-%d %H:%M'), datetime.datetime.fromtimestamp(time_end).strftime('%Y-%m-%d %H:%M'), timeframes[period])
    

if __name__ == "__main__":
    help()
