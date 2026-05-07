import unittest

from utils import get_logger, get_urlhash, normalize


class UtilsTests(unittest.TestCase):
    def test_get_logger_does_not_duplicate_handlers(self):
        logger = get_logger("TEST_DUPLICATE_LOGGER", "TEST_DUPLICATE_LOGGER")
        handler_count = len(logger.handlers)

        same_logger = get_logger("TEST_DUPLICATE_LOGGER", "TEST_DUPLICATE_LOGGER")

        self.assertIs(logger, same_logger)
        self.assertEqual(len(same_logger.handlers), handler_count)

    def test_normalize_and_hash_ignore_fragments(self):
        base_url = "https://www.ics.uci.edu/page?x=1"
        self.assertEqual(normalize(f"{base_url}#section"), base_url)
        self.assertEqual(get_urlhash(f"{base_url}#a"), get_urlhash(f"{base_url}#b"))

    def test_url_hash_keeps_scheme_distinct(self):
        self.assertNotEqual(
            get_urlhash("http://www.ics.uci.edu/page"),
            get_urlhash("https://www.ics.uci.edu/page"),
        )


if __name__ == "__main__":
    unittest.main()
