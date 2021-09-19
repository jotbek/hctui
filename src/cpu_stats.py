import psutil
import hc_cache

NO_MAX_CACHED_CPU_VALUES = 20
cpu_values_list = [0.0] * NO_MAX_CACHED_CPU_VALUES
cache_enabled = False
session_id = None


def cpu_count():
    global session_id
    return try_get_from_cache(
        session_id, __name__, cpu_count.__name__, lambda: psutil.cpu_count(logical=False))


def cpu_freq():
    return try_get_from_cache(session_id, __name__, cpu_freq.__name__, lambda: psutil.cpu_freq())


def cpu_usage_per_core():
    return try_get_from_cache(session_id, __name__, cpu_usage_per_core.__name__, lambda: psutil.cpu_percent(percpu=True, interval=0.1))


def cpu_usage_total():
    return try_get_from_cache(session_id, __name__, cpu_usage_total.__name__, lambda: psutil.cpu_percent(interval=0.1))


def cpu_values():
    return try_get_from_cache(session_id, __name__, cpu_values.__name__, lambda: cpu_values_internal())


def cpu_values_internal():
    if len(cpu_values_list) >= NO_MAX_CACHED_CPU_VALUES:
        cpu_values_list.pop(0)
    cpu_values_list.append(cpu_usage_total())
    return cpu_values_list


# CACHE part starts here
def init_cache_session(session_identifier):
    global cache_enabled
    global session_id
    global cache
    cache_enabled = True
    session_id = session_identifier


def disable_cache():
    global cache_enabled
    global session_id
    cache_enabled = False
    session_id = None


def try_get_from_cache(session_identifier, module_name, function_name, action):
    global cache_enabled
    if cache_enabled:
        return hc_cache.get_from_cache(session_identifier + '.' + module_name + '.' + function_name, action)
    else:
        return action()
