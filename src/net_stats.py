import subprocess
import psutil
import time
import math


NO_MAX_CACHED_NET_VALUES = 50
net_values_list = [0.0] * NO_MAX_CACHED_NET_VALUES


def get_default_interface():
    result = subprocess.check_output("route | grep '^default' | grep -o '[^ ]*$'", shell=True)
    return result.decode('utf-8').strip()


def get_current_bandwidth():
    network = convert_size(get_current_bandwidth_bytes()[0]) + convert_size(get_current_bandwidth_bytes()[1])
    return network


def get_current_bandwidth_bytes():
    sleep_time = 0.2
    sleep_adapter = 1 / sleep_time

    # Get net in/out
    net1_out = psutil.net_io_counters().bytes_sent
    net1_in = psutil.net_io_counters().bytes_recv

    time.sleep(sleep_time)

    # Get new net in/out
    net2_out = psutil.net_io_counters().bytes_sent
    net2_in = psutil.net_io_counters().bytes_recv

    # Compare and get current speed
    if net1_in > net2_in:
        current_in = 0
    else:
        current_in = net2_in - net1_in

    if net1_out > net2_out:
        current_out = 0
    else:
        current_out = net2_out - net1_out

    real_bytes_in = current_in * sleep_adapter
    real_bytes_out = current_out * sleep_adapter
    return real_bytes_in, real_bytes_out


def convert_size(size_bytes):
    default_result = "~0 ", "B"

    if size_bytes == 0:
        return default_result

    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 1)

    if str(s) == "0":
        return default_result

    return str(s), size_name[i]


def in_out_historical():
    if len(net_values_list) >= NO_MAX_CACHED_NET_VALUES:
        net_values_list.pop(0)
    net_values_list.append(get_current_bandwidth_bytes()[0])
    max_net_usage = max(net_values_list)

    if max_net_usage == 0.0:
        return [0.0] * NO_MAX_CACHED_NET_VALUES

    result = []
    for v in net_values_list:
        result.append(100 * v / max_net_usage)

    return result
