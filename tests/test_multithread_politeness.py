import os
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace

import crawler.worker as worker_module
from crawler.frontier import Frontier
from crawler.worker import Worker


class FrontierPolitenessTests(unittest.TestCase):
    def make_config(self, save_file):
        return SimpleNamespace(
            save_file=save_file,
            seed_urls=[],
            time_delay=0.5,
        )

    def test_same_domain_dispatch_respects_politeness_delay(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            save_file = os.path.join(temp_dir, "frontier.shelve")
            frontier = Frontier(self.make_config(save_file), restart=True)
            try:
                frontier.add_url("https://www.ics.uci.edu/a")
                frontier.add_url("https://www.ics.uci.edu/b")

                first = frontier.get_tbd_url()
                first_time = time.monotonic()
                second = frontier.get_tbd_url()
                second_time = time.monotonic()

                self.assertEqual(first, "https://www.ics.uci.edu/b")
                self.assertEqual(second, "https://www.ics.uci.edu/a")
                self.assertGreaterEqual(second_time - first_time, 0.5)

                frontier.mark_url_complete(first)
                frontier.mark_url_complete(second)
            finally:
                frontier.save.close()

    def test_get_tbd_url_waits_while_work_is_in_flight(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            save_file = os.path.join(temp_dir, "frontier.shelve")
            frontier = Frontier(self.make_config(save_file), restart=True)
            try:
                frontier.add_url("https://www.ics.uci.edu/active")
                active = frontier.get_tbd_url()
                results = []

                def worker():
                    results.append(frontier.get_tbd_url())

                thread = threading.Thread(target=worker)
                thread.start()
                time.sleep(0.1)
                self.assertTrue(thread.is_alive())

                frontier.add_url("https://www.ics.uci.edu/new")
                frontier.mark_url_complete(active)
                thread.join(timeout=2.0)

                self.assertEqual(results, ["https://www.ics.uci.edu/new"])
                frontier.mark_url_complete(results[0])
            finally:
                frontier.save.close()

    def test_worker_thread_can_add_and_complete_urls(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            save_file = os.path.join(temp_dir, "frontier.shelve")
            frontier = Frontier(self.make_config(save_file), restart=True)
            frontier.add_url("https://www.ics.uci.edu/start")
            errors = []

            def worker():
                try:
                    url = frontier.get_tbd_url()
                    frontier.add_url("https://www.ics.uci.edu/next")
                    frontier.mark_url_complete(url)
                except Exception as err:
                    errors.append(err)

            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(timeout=2.0)
            frontier.save.close()

            self.assertEqual(errors, [])

    def test_restart_removes_shelve_sidecar_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            save_file = os.path.join(temp_dir, "frontier.shelve")
            sidecar_file = f"{save_file}.db"
            with open(sidecar_file, "w", encoding="utf-8") as sidecar:
                sidecar.write("stale")

            frontier = Frontier(self.make_config(save_file), restart=True)
            frontier.save.close()

            self.assertFalse(os.path.exists(sidecar_file))

    def test_worker_marks_url_complete_when_download_raises(self):
        class FakeFrontier:
            def __init__(self):
                self.urls = ["https://www.ics.uci.edu/fail"]
                self.completed = []

            def get_tbd_url(self):
                return self.urls.pop() if self.urls else None

            def add_url(self, url):
                raise AssertionError("No URLs should be added after download failure")

            def mark_url_complete(self, url):
                self.completed.append(url)

        original_download = worker_module.download

        def failing_download(url, config, logger):
            raise RuntimeError("cache failure")

        frontier = FakeFrontier()
        worker_module.download = failing_download
        try:
            worker = Worker(0, SimpleNamespace(cache_server=("cache", 9000)), frontier)
            worker.run()
        finally:
            worker_module.download = original_download

        self.assertEqual(frontier.completed, ["https://www.ics.uci.edu/fail"])

    def test_worker_adds_scraped_links_and_continues_past_seed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            save_file = os.path.join(temp_dir, "frontier.shelve")
            config = SimpleNamespace(
                save_file=save_file,
                seed_urls=["https://www.ics.uci.edu/start"],
                time_delay=0.0,
                cache_server=("cache", 9000),
            )
            frontier = Frontier(config, restart=True)
            original_download = worker_module.download

            def fake_download(url, config, logger):
                if url.endswith("/start"):
                    html = "<html><body><p>" + ("seed content " * 80) + "</p><a href='/next'>Next</a></body></html>"
                else:
                    html = "<html><body><p>" + ("next content " * 80) + "</p></body></html>"
                raw_response = SimpleNamespace(
                    content=html.encode("utf-8"),
                    url=url,
                    headers={"content-type": "text/html"},
                )
                return SimpleNamespace(url=url, status=200, raw_response=raw_response, error=None)

            worker_module.download = fake_download
            try:
                worker = Worker(0, config, frontier)
                worker.run()
            finally:
                worker_module.download = original_download

            completed_urls = {url for url, completed in frontier.known_urls.values() if completed}
            self.assertEqual(completed_urls, {
                "https://www.ics.uci.edu/start",
                "https://www.ics.uci.edu/next",
            })


if __name__ == "__main__":
    unittest.main()
