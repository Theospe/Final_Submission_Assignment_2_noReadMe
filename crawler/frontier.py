import os
import shelve
import glob
import time

from collections import deque
from threading import RLock, Condition
from urllib.parse import urlparse

from utils import get_logger, get_urlhash, normalize
from scraper import is_valid


class ClosedSaveHandle:
    def close(self):
        pass


class Frontier(object):
    def __init__(self, config, restart):
        self.logger = get_logger("FRONTIER")
        self.config = config
        self.to_be_downloaded = deque()
        self.lock = RLock()
        self.condition = Condition(self.lock)
        self.in_flight = set()
        self.next_allowed_time = {}
        self.known_urls = {}
        self.save = ClosedSaveHandle()
        
        save_files = self._save_files()
        if not save_files and not restart:
            # Save file does not exist, but request to load save.
            self.logger.info(
                f"Did not find save file {self.config.save_file}, "
                f"starting from seed.")
        elif save_files and restart:
            # Save file exists, but request to start from seed.
            self.logger.info(
                f"Found save file {self.config.save_file}, deleting it.")
            self._remove_save_files()
        # Load existing save file, or create one if it does not exist.
        self._load_save_file()
        if restart:
            for url in self.config.seed_urls:
                self.add_url(url)
        else:
            # Set the frontier state with contents of save file.
            self._parse_save_file()
            if not self.known_urls:
                for url in self.config.seed_urls:
                    self.add_url(url)

    def _load_save_file(self):
        with shelve.open(self.config.save_file) as save:
            self.known_urls = dict(save)

    def _parse_save_file(self):
        ''' This function can be overridden for alternate saving techniques. '''
        total_count = len(self.known_urls)
        tbd_count = 0
        for url, completed in self.known_urls.values():
            if not completed and is_valid(url):
                self.to_be_downloaded.appendleft(url)
                tbd_count += 1
        self.logger.info(
            f"Found {tbd_count} urls to be downloaded from {total_count} "
            f"total urls discovered.")

    def _remove_save_files(self):
        for save_file in self._save_files():
            os.remove(save_file)

    def _save_files(self):
        return glob.glob(f"{self.config.save_file}*")

    def get_tbd_url(self):
        with self.condition:
            while True:
                if not self.to_be_downloaded:
                    if not self.in_flight:
                        return None
                    self.condition.wait(timeout=self.config.time_delay)
                    continue

                now = time.monotonic()
                earliest_ready_time = None
                queue_size = len(self.to_be_downloaded)
                for _ in range(queue_size):
                    url = self.to_be_downloaded.pop()
                    domain = self._get_domain(url)
                    ready_time = self.next_allowed_time.get(domain, 0.0)
                    if now >= ready_time:
                        self.next_allowed_time[domain] = now + self.config.time_delay
                        self.in_flight.add(get_urlhash(url))
                        return url
                    self.to_be_downloaded.appendleft(url)
                    if earliest_ready_time is None or ready_time < earliest_ready_time:
                        earliest_ready_time = ready_time

                wait_time = self.config.time_delay
                if earliest_ready_time is not None:
                    wait_time = max(0.0, earliest_ready_time - time.monotonic())
                self.condition.wait(timeout=wait_time)

    def add_url(self, url):
        if not is_valid(url):
            return
        url = normalize(url)
        urlhash = get_urlhash(url)
        with self.condition:
            if urlhash not in self.known_urls:
                self.known_urls[urlhash] = (url, False)
                self._write_save_record(urlhash, (url, False))
                self.to_be_downloaded.append(url)
                self.condition.notify_all()
    
    def mark_url_complete(self, url):
        normalized_url = normalize(url)
        urlhash = get_urlhash(normalized_url)
        with self.condition:
            if urlhash not in self.known_urls:
                # This should not happen.
                self.logger.error(
                    f"Completed url {normalized_url}, but have not seen it before.")
            else:
                self.known_urls[urlhash] = (normalized_url, True)
                self._write_save_record(urlhash, (normalized_url, True))

            self.in_flight.discard(urlhash)
            self.condition.notify_all()

    def _get_domain(self, url):
        parsed = urlparse(url)
        return parsed.hostname.lower() if parsed.hostname else ""

    def _write_save_record(self, urlhash, record):
        with shelve.open(self.config.save_file) as save:
            save[urlhash] = record
            save.sync()
