import importlib
import json
import os
import shutil
import unittest
from types import SimpleNamespace


class ScraperTests(unittest.TestCase):
    def setUp(self):
        import scraper

        self.scraper = importlib.reload(scraper)
        self.scraper.ANALYTICS_DIR = os.path.join("test_analytics", self._testMethodName)
        shutil.rmtree(self.scraper.ANALYTICS_DIR, ignore_errors=True)
        self.scraper.SEEN_CONTENT_HASHES.clear()
        self.scraper.SEEN_SIMHASHES.clear()
        self.scraper.SIMHASH_BANDS.clear()

    def tearDown(self):
        pass

    def fake_response(self, html, url="https://www.ics.uci.edu/index.html", status=200, content_type="text/html"):
        raw = SimpleNamespace(content=html.encode("utf-8"), url=url)
        raw.headers = {"content-type": content_type}
        return SimpleNamespace(url=url, status=status, raw_response=raw, error=None)

    def test_allowed_domains_are_valid(self):
        valid_urls = [
            "https://www.ics.uci.edu/",
            "https://vision.ics.uci.edu/page",
            "https://www.cs.uci.edu/",
            "https://archive.informatics.uci.edu/a/b",
            "https://www.stat.uci.edu/about",
        ]
        for url in valid_urls:
            self.assertTrue(self.scraper.is_valid(url), url)

    def test_outside_domains_are_invalid(self):
        invalid_urls = [
            "https://uci.edu/",
            "https://ics.uci.edu.example.com/",
            "https://www.math.uci.edu/",
            "ftp://www.ics.uci.edu/file",
            "https://www.ics.uci.edu:badport/page",
        ]
        for url in invalid_urls:
            self.assertFalse(self.scraper.is_valid(url), url)

    def test_bad_file_extensions_are_invalid(self):
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/file.pdf"))
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/image.png"))
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/archive.zip"))
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/SSLPoke.class"))
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/example.py"))
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/project/source.cpp"))
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/notebook.ipynb"))
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/vm.ova"))
        extra_artifacts = (
            "lif", "bib", "mht", "db", "scm", "z", "nb", "hs", "als", "tsv",
            "ma", "ss", "mzn", "img", "fig", "cls", "rkt", "ff",
        )
        for extension in extra_artifacts:
            self.assertFalse(self.scraper.is_valid(f"https://www.ics.uci.edu/artifact.{extension}"), extension)

    def test_normalize_link_defragments_and_resolves_relative_urls(self):
        link = self.scraper.normalize_link(
            "https://www.ics.uci.edu/folder/page.html",
            "../next.html#section",
        )
        self.assertEqual(link, "https://www.ics.uci.edu/next.html")
        self.assertIsNone(self.scraper.normalize_link("https://www.ics.uci.edu/", "https://www.ics.uci.edu:badport/page"))

    def test_query_traps_are_invalid(self):
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/calendar?month=2025-01"))
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/search?q=faculty"))
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/page?utm_source=x"))
        self.assertFalse(self.scraper.is_valid("https://cml.ics.uci.edu/post/?page=events&subPage=dss_schedule"))
        self.assertFalse(self.scraper.is_valid("https://wiki.ics.uci.edu/doku.php/wiki:nonexisting?do=media&ns=wiki"))
        self.assertFalse(self.scraper.is_valid("https://wiki.ics.uci.edu/doku.php/wiki:nonexisting?tab_files=upload&do=media"))

    def test_research_paths_are_not_blocked_by_search_trap(self):
        valid_urls = [
            "https://ics.uci.edu/research/",
            "https://cs.uci.edu/research/areas/",
            "https://informatics.uci.edu/research/research-areas/",
            "https://stat.uci.edu/research/",
        ]
        for url in valid_urls:
            self.assertTrue(self.scraper.is_valid(url), url)

    def test_search_path_segment_is_still_invalid(self):
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/search?q=faculty"))
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/site/search"))

    def test_event_path_segments_are_invalid(self):
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/events"))
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/event"))
        self.assertFalse(self.scraper.is_valid("https://www.ics.uci.edu/news/events/faculty"))

    def test_runtime_trap_patterns_are_invalid(self):
        invalid_urls = [
            "http://www.ics.uci.edu/~shantas/publications/20-secret-sharing-aggregation-TKDE-shantanu",
            "https://ics.uci.edu/~irus/twist/wisen98",
            "https://ics.uci.edu/~dhirschb/genealogy/Krakow/index.html",
            "https://ics.uci.edu/~pazzani/Slides/MLC94/tsld001.htm",
            "https://ics.uci.edu/~wscacchi/Presentations",
            "http://flamingo.ics.uci.edu/releases/4.1/src/util/?C=N;O=A",
            "http://computableplant.ics.uci.edu/PNAS.103.5.1533(2006)/?C=M;O=D",
            "https://emj.ics.uci.edu/wp-login.php",
            "https://cloudberry.ics.uci.edu/wp-admin",
            "https://example.ics.uci.edu/wp-json/wp/v2/posts",
            "https://mailman.ics.uci.edu/mailman/listinfo/asterixresearch",
            "https://mailman.ics.uci.edu/mailman/admin/cml",
            "https://archive.ics.uci.edu/auth/login/github",
            "https://cml.ics.uci.edu/tag/news/page/4",
            "https://cml.ics.uci.edu/category/news",
            "https://cloudberry.ics.uci.edu/author/chenli",
            "https://emj.ics.uci.edu/feed",
            "http://flamingo.ics.uci.edu/releases/4.0/docs/SepiaDoc.html",
            "http://flamingo.ics.uci.edu/toolkit/src",
            "https://archive-beta.ics.uci.edu/datasets?order={%22donatedAt%22:%22desc%22}",
            "https://acoi.ics.uci.edu/2019/08/20",
            "https://acoi.ics.uci.edu/2019/08",
            "https://helpdesk.ics.uci.edu/Ticket/Display.html?id=73077",
            "https://helpdesk.ics.uci.edu/NoAuth/Login.html?next=abc",
            "https://password.ics.uci.edu/change",
            "https://netreg.ics.uci.edu/r",
            "https://checkin.ics.uci.edu/checkin",
        ]
        for url in invalid_urls:
            self.assertFalse(self.scraper.is_valid(url), url)

    def test_query_trap_words_do_not_match_substrings(self):
        valid_urls = [
            "https://www.ics.uci.edu/file?download=syllabus",
            "https://www.ics.uci.edu/profile?update=profile",
            "https://www.ics.uci.edu/help?sidebar=true",
            "https://www.ics.uci.edu/about?pagedesc=about",
            "https://www.ics.uci.edu/news?today=1",
        ]
        for url in valid_urls:
            self.assertTrue(self.scraper.is_valid(url), url)

    def test_exact_trap_query_key_values_still_block(self):
        invalid_urls = [
            "https://www.ics.uci.edu/page?do=media",
            "https://www.ics.uci.edu/page?ns=wiki",
            "https://www.ics.uci.edu/page?page=2",
            "https://www.ics.uci.edu/page?sid=abc",
            "https://www.ics.uci.edu/page?date=2026-05-03",
        ]
        for url in invalid_urls:
            self.assertFalse(self.scraper.is_valid(url), url)

    def test_explicit_trap_list_is_invalid(self):
        blocked = [
            "https://grape.ics.uci.edu/",
            "https://wics.ics.uci.edu/",
            "https://ngs.ics.uci.edu/",
            "https://gitlab.ics.uci.edu/",
            "https://isg.ics.uci.edu/events/calendar",
            "http://fano.ics.uci.edu/ca/rules/",
            "https://ics.uci.edu/~eppstein/pix/prague",
            "https://wiki.ics.uci.edu/doku.php/main",
            "https://www.ics.uci.edu/page?ical=1",
            "https://www.ics.uci.edu/page?tribe_event=1",
        ]
        for url in blocked:
            self.assertFalse(self.scraper.is_valid(url), url)

    def test_extract_next_links_ignores_script_text_and_counts_words(self):
        html = """
        <html><body>
            <script>secret script words</script>
            <p>Information retrieval crawler project project.</p>
            <a href="/about#team">About</a>
            <a href="https://example.com/outside">Outside</a>
        </body></html>
        """
        links = self.scraper.extract_next_links(
            "https://www.ics.uci.edu/",
            self.fake_response(html),
        )
        self.assertIn("https://www.ics.uci.edu/about", links)

        pages_path = os.path.join(self.scraper.ANALYTICS_DIR, "pages.jsonl")
        with open(pages_path, "r", encoding="utf-8") as pages_file:
            record = pages_file.readline()
        self.assertIn("project", record)
        self.assertNotIn("secret", record)

    def test_tokenize_text_matches_assignment1_rule(self):
        tokens = self.scraper.tokenize_text("CS121 can't parse café_42 as one token.")
        self.assertEqual(tokens, ["cs121", "can", "t", "parse", "caf", "42", "as", "one", "token"])

    def test_malformed_numeric_entity_does_not_crash_parser(self):
        html = '<html><body><a href="/next">&#269ansk&eacute; N&aacute;m</a></body></html>'
        links = self.scraper.extract_next_links(
            "https://ics.uci.edu/~eppstein/pix/prague/castle/StaryKralovskyLargeHall.html",
            self.fake_response(html, url="https://ics.uci.edu/~eppstein/pix/prague/castle/StaryKralovskyLargeHall.html"),
        )
        self.assertIn("https://ics.uci.edu/next", links)

    def test_missing_raw_response_does_not_crash(self):
        resp = SimpleNamespace(url="https://www.ics.uci.edu/no-raw", status=200, error=None)
        self.assertEqual(self.scraper.extract_next_links(resp.url, resp), [])

    def test_non_html_response_is_not_tokenized(self):
        resp = self.fake_response(
            "def crawler():\n    return 'code words should not count'",
            url="https://www.ics.uci.edu/source",
            content_type="text/plain",
        )
        self.assertEqual(self.scraper.extract_next_links(resp.url, resp), [])

        pages_path = os.path.join(self.scraper.ANALYTICS_DIR, "pages.jsonl")
        with open(pages_path, "r", encoding="utf-8") as pages_file:
            record = pages_file.readline()
        self.assertIn('"word_count": 0', record)
        self.assertNotIn("crawler", record)

    def test_bad_final_extension_is_not_tokenized_without_content_type(self):
        resp = self.fake_response(
            "def crawler():\n    return 'redirected code should not count'",
            url="https://www.ics.uci.edu/source.py",
            content_type="",
        )
        self.assertEqual(
            self.scraper.extract_next_links("https://www.ics.uci.edu/download", resp),
            [],
        )

        pages_path = os.path.join(self.scraper.ANALYTICS_DIR, "pages.jsonl")
        with open(pages_path, "r", encoding="utf-8") as pages_file:
            record = pages_file.readline()
        self.assertIn('"word_count": 0', record)
        self.assertNotIn("crawler", record)

    def test_outside_final_url_is_not_tokenized_or_expanded(self):
        resp = self.fake_response(
            "<html><body>Access restricted location block <a href='https://ics.uci.edu/leak'>Leak</a></body></html>",
            url="https://blocked.iplocationblock.com/",
            content_type="text/html",
        )
        self.assertEqual(
            self.scraper.extract_next_links("https://ics.uci.edu/news/item", resp),
            [],
        )

        pages_path = os.path.join(self.scraper.ANALYTICS_DIR, "pages.jsonl")
        with open(pages_path, "r", encoding="utf-8") as pages_file:
            record = pages_file.readline()
        self.assertIn('"word_count": 0', record)
        self.assertNotIn("restricted", record)

    def test_binary_like_response_is_not_tokenized(self):
        resp = self.fake_response(
            " ".join("abcdefghijklmnopqrstuvwxyz" * 50),
            url="https://www.ics.uci.edu/no-extension-download",
            content_type="",
        )
        self.assertEqual(self.scraper.extract_next_links(resp.url, resp), [])

        pages_path = os.path.join(self.scraper.ANALYTICS_DIR, "pages.jsonl")
        with open(pages_path, "r", encoding="utf-8") as pages_file:
            record = pages_file.readline()
        self.assertIn('"word_count": 0', record)

    def test_binary_like_detection_counts_raw_single_character_tokens(self):
        words = (["a"] * 250) + [f"word{i}" for i in range(800)]

        self.assertTrue(self.scraper.has_binary_like_tokens(words))

    def test_string_content_does_not_crash_parser(self):
        soup = self.scraper.parse_html("<html><body><p>Hello 121</p></body></html>")
        words, _ = self.scraper.extract_words(soup)
        self.assertEqual(words, ["hello", "121"])

    def test_duplicate_pages_do_not_expand_links(self):
        html = "<html><body><p>" + ("unique content " * 60) + "</p><a href='/next'>Next</a></body></html>"
        first = self.scraper.extract_next_links("https://www.ics.uci.edu/one", self.fake_response(html))
        second = self.scraper.extract_next_links("https://www.ics.uci.edu/two", self.fake_response(html))
        self.assertTrue(first)
        self.assertEqual(second, [])

    def test_near_duplicate_pages_do_not_expand_links_and_are_marked(self):
        base_tokens = " ".join(f"token{i}" for i in range(80))
        html_one = f"<html><body><p>{base_tokens}</p><a href='/a'>A</a></body></html>"
        html_two = f"<html><body><p>{base_tokens} extrachange</p><a href='/b'>B</a></body></html>"

        first = self.scraper.extract_next_links("https://www.ics.uci.edu/near1", self.fake_response(html_one))
        second = self.scraper.extract_next_links("https://www.ics.uci.edu/near2", self.fake_response(html_two))
        self.assertTrue(first)
        self.assertEqual(second, [])

        pages_path = os.path.join(self.scraper.ANALYTICS_DIR, "pages.jsonl")
        with open(pages_path, "r", encoding="utf-8") as pages_file:
            records = [json.loads(line) for line in pages_file]
        self.assertIn("simhash64", records[0])
        self.assertIn("near_duplicate_content", records[1])
        self.assertTrue(records[1]["near_duplicate_content"])


if __name__ == "__main__":
    unittest.main()
