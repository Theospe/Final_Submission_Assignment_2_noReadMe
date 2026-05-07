import unittest
from types import SimpleNamespace

import cbor
import requests
from requests import Response

import utils.download as download_module
from utils.response import Response as CacheResponse


class DownloadTests(unittest.TestCase):
    def test_cache_request_uses_timeout_and_returns_response_on_exception(self):
        original_get = download_module.requests.get
        errors = []

        def fake_get(url, params, timeout):
            self.assertEqual(timeout, download_module.CACHE_REQUEST_TIMEOUT)
            raise requests.exceptions.Timeout("cache timeout")

        download_module.requests.get = fake_get
        try:
            resp = download_module.download(
                "https://www.ics.uci.edu/",
                SimpleNamespace(cache_server=("cache", 9000), user_agent="IR US26 1"),
                SimpleNamespace(error=errors.append),
            )
        finally:
            download_module.requests.get = original_get

        self.assertEqual(resp.status, 601)
        self.assertIn("cache timeout", resp.error)
        self.assertTrue(errors)

    def test_falsey_http_error_response_with_cbor_body_is_decoded(self):
        original_get = download_module.requests.get

        def fake_get(url, params, timeout):
            response = Response()
            response.status_code = 604
            response._content = cbor.dumps({
                "url": "https://www.math.uci.edu/",
                "status": 604,
                "error": "Domain must be within spec",
            })
            return response

        download_module.requests.get = fake_get
        try:
            resp = download_module.download(
                "https://www.math.uci.edu/",
                SimpleNamespace(cache_server=("cache", 9000), user_agent="IR US26 1"),
            )
        finally:
            download_module.requests.get = original_get

        self.assertEqual(resp.status, 604)
        self.assertIn("Domain must be within spec", resp.error)

    def test_malformed_pickled_raw_response_does_not_crash(self):
        resp = CacheResponse({
            "url": "https://www.ics.uci.edu/bad",
            "status": 200,
            "response": b"not a pickle",
        })

        self.assertEqual(resp.status, 200)
        self.assertIsNone(resp.raw_response)

    def test_malformed_cbor_payload_returns_controlled_error_response(self):
        original_get = download_module.requests.get

        def fake_get(url, params, timeout):
            response = Response()
            response.status_code = 602
            response._content = cbor.dumps({"unexpected": "shape"})
            return response

        download_module.requests.get = fake_get
        try:
            resp = download_module.download(
                "https://www.ics.uci.edu/",
                SimpleNamespace(cache_server=("cache", 9000), user_agent="IR US26 1"),
            )
        finally:
            download_module.requests.get = original_get

        self.assertEqual(resp.status, 602)
        self.assertIn("Spacetime Response error", resp.error)

    def test_none_http_response_returns_controlled_error_response(self):
        original_get = download_module.requests.get

        def fake_get(url, params, timeout):
            return None

        download_module.requests.get = fake_get
        try:
            resp = download_module.download(
                "https://www.ics.uci.edu/",
                SimpleNamespace(cache_server=("cache", 9000), user_agent="IR US26 1"),
            )
        finally:
            download_module.requests.get = original_get

        self.assertEqual(resp.status, 602)
        self.assertIn("Spacetime Response error", resp.error)


if __name__ == "__main__":
    unittest.main()
