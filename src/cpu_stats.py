import uuid

import psutil

MAX_CACHED_VALUES = 20
cpu_values_list = [0.0] * MAX_CACHED_VALUES
cache_enabled = False
session_id = None
cache = {}


def cpu_count():
    global session_id
    return try_get_from_cache(
        session_id, cpu_count.__name__, lambda: psutil.cpu_count(logical=False))


def cpu_freq():
    return try_get_from_cache(session_id, cpu_freq.__name__, lambda: psutil.cpu_freq())


def cpu_usage_per_core():
    return try_get_from_cache(session_id, cpu_usage_per_core.__name__, lambda: psutil.cpu_percent(percpu=True, interval=0.1))


def cpu_usage_total():
    return try_get_from_cache(session_id, cpu_usage_total.__name__, lambda: psutil.cpu_percent(interval=0.1))


def cpu_values():
    return try_get_from_cache(session_id, cpu_values.__name__, lambda: cpu_values_internal())


def cpu_values_internal():
    if len(cpu_values_list) >= MAX_CACHED_VALUES:
        cpu_values_list.pop(0)
    cpu_values_list.append(cpu_usage_total())
    return cpu_values_list


# CACHE part starts here
def init_cache_session(session_identifier):
    global cache_enabled
    global session_id
    global cache
    cache_enabled = True
    session_id = uuid.UUID(session_identifier)


def disable_cache():
    global cache_enabled
    global session_id
    global cache
    cache_enabled = False
    session_id = None
    cache.clear()


def try_get_from_cache(session_identifier, function_name, action):
    global cache
    if session_identifier is None:
        return action()

    key = function_name + str(session_identifier)
    if not use_cache(session_identifier, function_name):
        cache[key] = action()
    return cache[key]


def use_cache(session_identifier, function_name):
    global session_id
    global cache
    return cache_enabled and session_identifier == session_id and function_name + str(session_id) in cache
