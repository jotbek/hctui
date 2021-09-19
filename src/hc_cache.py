import time

MAX_CACHE_ITEMS = 100
CLEANUP_ITEMS_SEC = 10
cache = {}


def get_from_cache(key, action):
    global cache
    if len(cache) >= MAX_CACHE_ITEMS:
        cleanup_cache()

    if key not in cache:
        cache[key] = (action(), time.time())

    return cache[key][0]


def cleanup_cache():
    global cache

    time_sec = time.time()
    for key, value in list(cache.items()):
        if time_sec - value[1] > CLEANUP_ITEMS_SEC:
            cache.pop(key)
