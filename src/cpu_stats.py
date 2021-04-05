import psutil


def cpu_count(logical=True):
    return psutil.cpu_count(logical=False)


def cpu_count(logical=False):
    return psutil.cpu_count(logical=False)


def cpu_freq():
    return psutil.cpu_freq()


def cpu_usage_per_core():
    return psutil.cpu_percent(percpu=True, interval=0.1)


def cpu_usage_total():
    result = psutil.cpu_percent(interval=0.1)
    return result

# TODO ADD SOME KIND OF CACHING TO CALL TO THE SAME FUNCTION RETURN THE SAME VALUE
