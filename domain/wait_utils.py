import time


def wait_until(fetch_fn, timeout: float, interval: float = 0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fetch_fn()
        if value:
            return value
        time.sleep(interval)
    return None

