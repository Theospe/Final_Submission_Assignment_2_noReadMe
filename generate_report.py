import argparse
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urldefrag, urlparse


BAD_REPORT_EXTENSIONS = {
    ".css", ".js", ".bmp", ".gif", ".jpg", ".jpeg", ".ico", ".png", ".tif", ".tiff",
    ".mid", ".mp2", ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mpeg", ".ram", ".m4v",
    ".mkv", ".ogg", ".ogv", ".pdf", ".ps", ".eps", ".tex", ".ppt", ".pptx", ".pps",
    ".ppsx", ".doc", ".docx", ".xls", ".xlsx", ".names", ".data", ".dat", ".exe", ".apk", ".bz2", ".tar",
    ".msi", ".bin", ".7z", ".psd", ".dmg", ".iso", ".ova", ".war", ".epub", ".dll", ".cnf",
    ".tgz", ".sha1", ".thmx", ".mso", ".arff", ".rtf", ".jar", ".csv", ".json",
    ".xml", ".txt", ".md", ".log", ".class", ".py", ".java", ".c", ".cc", ".cpp",
    ".cxx", ".h", ".hh", ".hpp", ".hxx", ".cs", ".go", ".rs", ".rb", ".pl", ".pm",
    ".sh", ".bash", ".zsh", ".sql", ".ipynb", ".r", ".scala", ".kt", ".kts",
    ".swift", ".asm", ".s", ".m", ".mm", ".rm", ".smil", ".wmv", ".swf", ".wma",
    ".lif", ".bib", ".mht", ".db", ".scm", ".z", ".nb", ".hs", ".als", ".tsv",
    ".ma", ".ss", ".mzn", ".img", ".fig", ".cls", ".rkt", ".ff", ".zip", ".rar", ".gz",
}


def read_pages(path):
    with path.open("r", encoding="utf-8") as pages_file:
        for line in pages_file:
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def generate_report(analytics_dir):
    pages_path = Path(analytics_dir) / "pages.jsonl"
    if not pages_path.exists():
        raise FileNotFoundError(f"Missing analytics file: {pages_path}")

    unique_urls = set()
    subdomains = {}
    total_words = Counter()
    longest_page = {"url": None, "word_count": 0}

    for page in read_pages(pages_path):
        if page.get("status") != 200:
            continue

        requested_url = page.get("requested_url")
        final_url = page.get("final_url")
        page_url = normalize_report_url(requested_url or final_url)
        if not page_url or page_url in unique_urls:
            continue
        if has_bad_report_extension(requested_url) or has_bad_report_extension(final_url) or has_binary_like_record(page):
            continue

        unique_urls.add(page_url)

        subdomain = safe_hostname(page_url)
        if subdomain:
            subdomains.setdefault(subdomain, set()).add(page_url)

        word_count = page.get("word_count", 0)
        if word_count > longest_page["word_count"]:
            longest_page = {"url": page_url, "word_count": word_count}

        word_counts = page.get("word_counts")
        if word_counts:
            total_words.update(word_counts)
        else:
            for word, count in page.get("top_words", []):
                total_words[word] += count

    print(f"Unique pages: {len(unique_urls)}")
    print(f"Longest page: {longest_page['url']}, {longest_page['word_count']} words")
    print()
    print("Top 50 words:")
    for word, count in total_words.most_common(50):
        print(f"{word}, {count}")
    print()
    print(f"Unique subdomains: {len(subdomains)}")
    print("Subdomains:")
    for subdomain in sorted(subdomains):
        print(f"{subdomain}, {len(subdomains[subdomain])}")


def has_bad_report_extension(url):
    if not url:
        return False
    path = safe_path(normalize_report_url(url)).lower()
    if "zip-attachment" in path or "raw-attachment" in path:
        return True
    return any(path.endswith(extension) for extension in BAD_REPORT_EXTENSIONS)


def normalize_report_url(url):
    if not url:
        return url
    try:
        normalized, _ = urldefrag(url)
        return normalized.rstrip("/") if normalized.endswith("/") else normalized
    except (TypeError, ValueError):
        return url


def safe_hostname(url):
    try:
        return urlparse(url).hostname
    except (TypeError, ValueError):
        return None


def safe_path(url):
    try:
        return urlparse(url).path
    except (TypeError, ValueError):
        return ""


def has_binary_like_record(page):
    word_count = page.get("word_count", 0)
    if word_count < 1000:
        return False

    word_counts = page.get("word_counts") or {}
    if word_counts:
        single_character_count = sum(
            count for word, count in word_counts.items() if len(word) == 1
        )
    else:
        single_character_count = sum(
            count for word, count in page.get("top_words", []) if len(word) == 1
        )
    return single_character_count / word_count > 0.20


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("analytics_dir", help="Path to an analytics run folder.")
    args = parser.parse_args()
    generate_report(args.analytics_dir)


if __name__ == "__main__":
    main()
