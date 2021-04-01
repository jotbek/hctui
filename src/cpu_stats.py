import psutil
import time


def cpu_count(logical=True):
    return psutil.cpu_count(logical=False)


def cpu_count(logical=False):
    return psutil.cpu_count(logical=False)


def cpu_freq():
    return psutil.cpu_freq()


def cpu_usage_per_core():
    result = []
    for i, percentage in enumerate(psutil.cpu_percent(percpu=True, interval=0.1)):
        result.append((i, percentage))
    return result


def cpu_usage_total():
    result = psutil.cpu_percent(interval=0.1)
    return result
