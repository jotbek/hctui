import psutil


MAX_CACHED_VALUES = 20
cpu_values_list = [0.0] * MAX_CACHED_VALUES


def cpu_count():
    return psutil.cpu_count(logical=False)


def cpu_freq():
    return psutil.cpu_freq()


def cpu_usage_per_core():
    return psutil.cpu_percent(percpu=True, interval=0.1)


def cpu_usage_total():
    return psutil.cpu_percent(interval=0.1)


def cpu_values():
    if len(cpu_values_list) >= MAX_CACHED_VALUES:
        cpu_values_list.pop(0)
    cpu_values_list.append(cpu_usage_total())
    return cpu_values_list

# TODO ADD SOME KIND OF CACHING TO CALL TO THE SAME FUNCTION RETURN THE SAME VALUE
