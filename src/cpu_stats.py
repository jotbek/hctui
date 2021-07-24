import uuid

import psutil

MAX_CACHED_VALUES = 20
cpu_values_list = [0.0] * MAX_CACHED_VALUES
cache_enabled = False
session_id = None
cache = {}


def enable_cache(enable, session_identifier=None):
    global cache_enabled
    global session_id
    global cache
    cache_enabled = enable
    session_id = uuid.UUID(session_identifier)
    # clear cache
    cache.clear()


def cpu_count(session_identifier=None):
    return try_get_from_cache(
        session_identifier, cpu_count.__name__, lambda: psutil.cpu_count(logical=False))


def cpu_freq(session_identifier=None):
    return try_get_from_cache(
        session_identifier, cpu_count.__name__, lambda: psutil.cpu_freq())


def cpu_usage_per_core(session_identifier=None):
    return try_get_from_cache(
        session_identifier, cpu_count.__name__, lambda: psutil.cpu_percent(percpu=True, interval=0.1))


def cpu_usage_total(session_identifier=None):
    return try_get_from_cache(
        session_identifier, cpu_count.__name__, lambda: psutil.cpu_percent(interval=0.1))


def cpu_values(session_identifier=None):
    return try_get_from_cache(session_identifier, cpu_count.__name__, lambda: cpu_values_internal())


def cpu_values_internal():
    if len(cpu_values_list) >= MAX_CACHED_VALUES:
        cpu_values_list.pop(0)
    cpu_values_list.append(cpu_usage_total())
    return cpu_values_list


def try_get_from_cache(session_identifier, function_name, action):
    global cache
    key = function_name + str(session_identifier)
    if not use_cache(session_identifier, function_name):
        cache[key] = action()
    return cache[key]


def use_cache(session_identifier, function_name):
    global session_id
    global cache
    return cache_enabled and session_identifier == session_id and function_name + str(session_id) in cache
