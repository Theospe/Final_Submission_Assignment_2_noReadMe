import unittest
from configparser import ConfigParser

from utils.config import Config


class ConfigTests(unittest.TestCase):
    def test_seed_urls_are_stripped_and_empty_entries_removed(self):
        parser = ConfigParser()
        parser.read_dict({
            "IDENTIFICATION": {"USERAGENT": "IR US26 1, 2"},
            "LOCAL PROPERTIES": {
                "THREADCOUNT": "4",
                "SAVE": "frontier.shelve",
            },
            "CONNECTION": {
                "HOST": "styx.ics.uci.edu",
                "PORT": "9000",
            },
            "CRAWLER": {
                "SEEDURL": " https://www.ics.uci.edu, , https://www.cs.uci.edu ",
                "POLITENESS": "0.5",
            },
        })

        config = Config(parser)

        self.assertEqual(config.seed_urls, [
            "https://www.ics.uci.edu",
            "https://www.cs.uci.edu",
        ])


if __name__ == "__main__":
    unittest.main()
