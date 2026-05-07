import requests
import cbor
import time

from utils.response import Response


CACHE_REQUEST_TIMEOUT = 30


def download(url, config, logger=None):
    host, port = config.cache_server
    try:
        resp = requests.get(
            f"http://{host}:{port}/",
            params=[("q", f"{url}"), ("u", f"{config.user_agent}")],
            timeout=CACHE_REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as err:
        message = f"Cache request error {err} with url {url}."
        if logger:
            logger.error(message)
        return Response({"error": message, "status": 601, "url": url})
    try:
        if resp is not None and resp.content:
            return Response(cbor.loads(resp.content))
    except (EOFError, ValueError, KeyError, TypeError) as e:
        pass
    if logger:
        logger.error(f"Spacetime Response error {resp} with url {url}.")
    return Response({
        "error": f"Spacetime Response error {resp} with url {url}.",
        "status": getattr(resp, "status_code", 602),
        "url": url})
