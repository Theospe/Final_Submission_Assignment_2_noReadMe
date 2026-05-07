import os
import logging
from hashlib import sha256
from urllib.parse import urldefrag, urlparse

def get_logger(name, filename=None):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return logger
    if not os.path.exists("Logs"):
        os.makedirs("Logs")
    fh = logging.FileHandler(f"Logs/{filename if filename else name}.log")
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter(
       "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    # add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def get_urlhash(url):
    url = normalize(url)
    parsed = urlparse(url)
    return sha256(
        f"{parsed.scheme}/{parsed.netloc}/{parsed.path}/{parsed.params}/"
        f"{parsed.query}".encode("utf-8")).hexdigest()

def normalize(url):
    url, _ = urldefrag(url)
    if url.endswith("/"):
        return url.rstrip("/")
    return url
