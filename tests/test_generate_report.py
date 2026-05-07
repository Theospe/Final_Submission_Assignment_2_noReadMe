import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from generate_report import generate_report


class GenerateReportTests(unittest.TestCase):
    def run_report(self, records):
        with tempfile.TemporaryDirectory() as temp_dir:
            analytics_dir = Path(temp_dir)
            pages_path = analytics_dir / "pages.jsonl"
            with pages_path.open("w", encoding="utf-8") as pages_file:
                for record in records:
                    pages_file.write(json.dumps(record) + "\n")

            output = io.StringIO()
            with redirect_stdout(output):
                generate_report(analytics_dir)
            return output.getvalue()

    def run_report_lines(self, lines):
        with tempfile.TemporaryDirectory() as temp_dir:
            analytics_dir = Path(temp_dir)
            pages_path = analytics_dir / "pages.jsonl"
            with pages_path.open("w", encoding="utf-8") as pages_file:
                for line in lines:
                    pages_file.write(line + "\n")

            output = io.StringIO()
            with redirect_stdout(output):
                generate_report(analytics_dir)
            return output.getvalue()

    def page(self, url, **overrides):
        record = {
            "requested_url": url,
            "final_url": url,
            "status": 200,
            "word_count": 10,
            "word_counts": {"crawler": 2, "research": 1},
            "top_words": [["crawler", 2], ["research", 1]],
        }
        record.update(overrides)
        return record

    def test_counts_unique_pages_by_url_not_content_hash(self):
        output = self.run_report([
            self.page("https://www.ics.uci.edu/a", content_hash="same"),
            self.page("https://www.ics.uci.edu/b", content_hash="same", duplicate_content=True),
        ])

        self.assertIn("Unique pages: 2", output)
        self.assertIn("www.ics.uci.edu, 2", output)

    def test_report_counts_fragment_variants_as_one_url(self):
        output = self.run_report([
            self.page("https://www.ics.uci.edu/a#one"),
            self.page("https://www.ics.uci.edu/a#two"),
        ])

        self.assertIn("Unique pages: 1", output)
        self.assertIn("www.ics.uci.edu, 1", output)

    def test_filters_artifacts_by_requested_or_final_url(self):
        output = self.run_report([
            self.page("https://www.ics.uci.edu/good"),
            self.page(
                "https://www.ics.uci.edu/download",
                final_url="https://www.ics.uci.edu/files/syllabus.pdf",
            ),
            self.page("https://www.ics.uci.edu/source.py"),
            self.page("https://ics.uci.edu/~eppstein/pubs/pubs.ff", word_count=55298),
        ])

        self.assertIn("Unique pages: 1", output)
        self.assertIn("www.ics.uci.edu, 1", output)

    def test_malformed_urls_do_not_crash_report(self):
        output = self.run_report([
            self.page("https://www.ics.uci.edu/good"),
            self.page("http://[bad"),
        ])

        self.assertIn("Unique pages: 2", output)
        self.assertIn("www.ics.uci.edu, 1", output)

    def test_malformed_jsonl_lines_do_not_crash_report(self):
        output = self.run_report_lines([
            json.dumps(self.page("https://www.ics.uci.edu/good")),
            '{"partial":',
        ])

        self.assertIn("Unique pages: 1", output)
        self.assertIn("www.ics.uci.edu, 1", output)


if __name__ == "__main__":
    unittest.main()
