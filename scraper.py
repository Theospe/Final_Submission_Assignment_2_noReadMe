import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime
from threading import RLock
from urllib.parse import parse_qsl, urldefrag, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

ALLOWED_DOMAINS = (
    "ics.uci.edu",
    "cs.uci.edu",
    "informatics.uci.edu",
    "stat.uci.edu",
)

BAD_EXTENSIONS = re.compile(
    r".*\.(css|js|bmp|gif|jpe?g|ico"
    + r"|png|tiff?|mid|mp2|mp3|mp4"
    + r"|wav|avi|mov|mpeg|ram|m4v|mkv|ogg|ogv|pdf"
    + r"|ps|eps|tex|ppt|pptx|pps|ppsx|doc|docx|xls|xlsx|names"
    + r"|data|dat|exe|apk|bz2|tar|msi|bin|7z|psd|dmg|iso"
    + r"|ova|war|epub|dll|cnf|tgz|sha1"
    + r"|thmx|mso|arff|rtf|jar|csv|json|xml"
    + r"|txt|md|log|class|py|java|c|cc|cpp|cxx|h|hh|hpp|hxx"
    + r"|cs|go|rs|rb|pl|pm|sh|bash|zsh|sql|ipynb|r|scala"
    + r"|kt|kts|swift|asm|s|m|mm|lif|bib|mht|db|scm|z|nb|hs|als|tsv|ff"
    + r"|ma|ss|mzn|img|fig|cls|rkt|rm|smil|wmv|swf|wma|zip|rar|gz)$"
)

TRAP_WORDS = {
    "calendar",
    "date",
    "month",
    "year",
    "day",
    "week",
    "search",
    "query",
    "filter",
    "order",
    "page",
    "subpage",
    "sort",
    "orderby",
    "do",
    "ns",
    "tab_files",
    "sectok",
    "session",
    "sid",
    "phpsessid",
    "replytocom",
}

TRACKING_PREFIXES = ("utm_",)
MAX_URL_LENGTH = 220
MAX_PATH_DEPTH = 8
MAX_QUERY_PARAMS = 3
MAX_REPEATED_SEGMENT = 2
MIN_WORDS_FOR_DUPLICATE_EXPANSION = 50
SIMHASH_BITS = 64
SIMHASH_SHINGLE_SIZE = 3
SIMHASH_NEAR_DUP_THRESHOLD = 3
SIMHASH_BAND_SIZE = 16
MALFORMED_NUMERIC_ENTITY_RE = re.compile(rb"&#(\d+)(?=[A-Za-z&])")
PAGINATION_PATH_RE = re.compile(r"/page/\d+/?$")
DATE_ARCHIVE_PATH_RE = re.compile(r"/\d{4}/\d{1,2}(/\d{1,2})?/?$")

STOP_WORDS_FILE = "stop_words.txt"
ANALYTICS_DIR = os.path.join("analytics", datetime.now().strftime("%Y%m%d_%H%M%S"))
SEEN_CONTENT_HASHES = set()
SEEN_SIMHASHES = []
SIMHASH_BANDS = {}
CONTENT_STATE_LOCK = RLock()
ANALYTICS_LOCK = RLock()
STOP_WORDS = None
BLOCKED_HOSTS = {
    "grape.ics.uci.edu",
    "wics.ics.uci.edu",
    "ngs.ics.uci.edu",
    "gitlab.ics.uci.edu",
    "helpdesk.ics.uci.edu",
    "password.ics.uci.edu",
    "netreg.ics.uci.edu",
    "checkin.ics.uci.edu",
}
BLOCKED_PATH_SUBSTRINGS = (
    "/events/",
    "doku.php",
    "tkde",
    "~irus/twist",
    "~dhirschb/genealogy",
    "~pazzani/slides",
    "~wscacchi/presentations",
    "~eppstein/pix",
)
BLOCKED_HOST_PATH_PREFIXES = {
    "fano.ics.uci.edu": ("/ca/rules/",),
    "flamingo.ics.uci.edu": ("/releases/", "/toolkit/src"),
    "isg.ics.uci.edu": ("/events/",),
}


def scraper(url, resp):
    links = extract_next_links(url, resp)
    return [link for link in links if is_valid(link)]


def extract_next_links(url, resp):
    raw_response = getattr(resp, "raw_response", None) if resp else None
    if resp is None or getattr(resp, "status", None) != 200 or raw_response is None:
        record_fetch(
            url, resp, [], "", None, Counter(), 0, duplicate=False, near_duplicate=False
        )
        return []

    content = getattr(raw_response, "content", b"")
    if not content:
        record_fetch(
            url, resp, [], "", None, Counter(), 0, duplicate=False, near_duplicate=False
        )
        return []

    if not is_html_response(url, resp):
        record_fetch(
            url, resp, [], "", None, Counter(), 0, duplicate=False, near_duplicate=False
        )
        return []

    soup = parse_html(content)
    words, visible_text = extract_words(soup)
    word_counts = Counter(word for word in words if word not in load_stop_words())
    if has_binary_like_tokens(words):
        record_fetch(
            url, resp, [], "", None, Counter(), 0, duplicate=False, near_duplicate=False
        )
        return []

    content_hash = hash_text(visible_text)
    simhash = compute_simhash(words)
    with CONTENT_STATE_LOCK:
        duplicate = content_hash in SEEN_CONTENT_HASHES if content_hash else False
        near_duplicate = is_near_duplicate_simhash(simhash)
        if content_hash:
            SEEN_CONTENT_HASHES.add(content_hash)
        if simhash is not None:
            register_simhash(simhash)

    base_url = getattr(raw_response, "url", None) or getattr(resp, "url", None) or url
    links = []
    for tag in soup.find_all("a", href=True):
        normalized = normalize_link(base_url, tag.get("href"))
        if normalized:
            links.append(normalized)

    record_fetch(
        url,
        resp,
        links,
        content_hash,
        simhash,
        word_counts,
        len(words),
        duplicate,
        near_duplicate,
    )

    if (
        duplicate
        or near_duplicate
        or (
            len(words) < MIN_WORDS_FOR_DUPLICATE_EXPANSION
            and len(links) > len(words) * 2
        )
    ):
        return []
    return links


def is_valid(url):
    try:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return False

        host = parsed.hostname.lower() if parsed.hostname else ""
        if not is_allowed_host(host):
            return False
        # Accessing parsed.port raises ValueError for malformed ports.
        _ = parsed.port
        if host in BLOCKED_HOSTS:
            return False

        if len(url) > MAX_URL_LENGTH:
            return False

        path = parsed.path.lower()
        if is_blocked_trap_path(host, path):
            return False
        if BAD_EXTENSIONS.match(path):
            return False

        if has_repeated_segments(path) or path_depth(path) > MAX_PATH_DEPTH:
            return False

        if has_trap_query_or_path(path, parsed.query):
            return False

        return True
    except (TypeError, ValueError):
        return False


def normalize_link(base_url, href):
    if href is None:
        return None
    try:
        href = str(href).strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            return None

        absolute = urljoin(str(base_url), href)
        defragmented, _ = urldefrag(absolute)
        parsed = urlparse(defragmented)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None

        host = parsed.hostname.lower()
        port = parsed.port
        netloc = host
        if port and not (
            (parsed.scheme == "http" and port == 80)
            or (parsed.scheme == "https" and port == 443)
        ):
            netloc = f"{host}:{port}"

        path = parsed.path or "/"
        return urlunparse((parsed.scheme.lower(), netloc, path, "", parsed.query, ""))
    except (TypeError, ValueError, UnicodeError):
        return None


def is_allowed_host(host):
    return any(
        host == domain or host.endswith(f".{domain}") for domain in ALLOWED_DOMAINS
    )


def is_html_response(url, resp):
    raw_response = getattr(resp, "raw_response", None) if resp else None
    candidate_urls = [normalize_link(url, url) or url]
    final_url = getattr(resp, "url", None) if resp else None
    if raw_response is not None:
        final_url = getattr(raw_response, "url", final_url)
    if final_url:
        candidate_urls.append(normalize_link(url, final_url) or final_url)

    for candidate_url in candidate_urls:
        parsed = urlparse(candidate_url)
        host = parsed.hostname.lower() if parsed.hostname else ""
        if not is_allowed_host(host):
            return False
        if BAD_EXTENSIONS.match(parsed.path.lower()):
            return False

    headers = getattr(raw_response, "headers", {}) or {}
    content_type = ""
    try:
        content_type = headers.get("content-type", headers.get("Content-Type", ""))
    except AttributeError:
        content_type = ""
    content_type = content_type.lower()

    if not content_type:
        return True
    return "text/html" in content_type or "application/xhtml+xml" in content_type


def path_depth(path):
    return len([part for part in path.split("/") if part])


def has_repeated_segments(path):
    parts = [part for part in path.lower().split("/") if part]
    counts = Counter(parts)
    return any(count > MAX_REPEATED_SEGMENT for count in counts.values())


def has_trap_query_or_path(path, query):
    lowered_path = path.lower()
    path_parts = set(part for part in lowered_path.strip("/").split("/") if part)
    if (
        any(
            word in lowered_path
            for word in (
                "calendar",
                "nonexisting",
                "zip-attachment",
                "raw-attachment",
                "wp-login.php",
                "/wp-admin",
                "/mailman/",
                "/auth/login",
                "/wp-json",
                "ical",
                "tribe",
            )
        )
        or PAGINATION_PATH_RE.search(lowered_path)
        or DATE_ARCHIVE_PATH_RE.search(lowered_path)
        or path_parts.intersection(
            {"author", "category", "event", "events", "feed", "search", "tag"}
        )
    ):
        return True

    if "doku.php" in lowered_path and query:
        return True

    params = parse_qsl(query.replace(";", "&"), keep_blank_values=True)
    if len(params) > MAX_QUERY_PARAMS:
        return True
    param_keys = {key.lower() for key, _ in params}
    if {"c", "o"}.issubset(param_keys):
        return True

    for key, value in params:
        key = key.lower()
        value = value.lower()
        if key.startswith(TRACKING_PREFIXES):
            return True
        if "ical" in key or "ical" in value or "tribe" in key or "tribe" in value:
            return True
        if key in TRAP_WORDS or value in TRAP_WORDS:
            return True
    return False


def is_blocked_trap_path(host, path):
    lowered_path = path.lower()
    if any(fragment in lowered_path for fragment in BLOCKED_PATH_SUBSTRINGS):
        return True
    prefixes = BLOCKED_HOST_PATH_PREFIXES.get(host, ())
    return any(lowered_path.startswith(prefix) for prefix in prefixes)


def extract_words(soup):
    try:
        for tag in soup(["script", "style", "noscript", "svg", "canvas"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    except Exception:
        text = ""
    return tokenize_text(text), text


def parse_html(content):
    if isinstance(content, str):
        content = content.encode("utf-8", errors="ignore")
    try:
        return BeautifulSoup(content, "html.parser")
    except Exception:
        repaired = MALFORMED_NUMERIC_ENTITY_RE.sub(rb"&#\1;", content)
        try:
            return BeautifulSoup(repaired, "html.parser")
        except Exception:
            return BeautifulSoup(b"", "html.parser")


def tokenize_text(text):
    tokens = []
    current_token = ""

    for char in text:
        try:
            if char.isalnum() and char.isascii():
                current_token += char.lower()
            elif current_token != "":
                tokens.append(current_token)
                current_token = ""
        except Exception:
            continue

    if current_token != "":
        tokens.append(current_token)

    return tokens


def has_binary_like_tokens(words):
    if len(words) < 1000:
        return False
    single_character_count = sum(1 for word in words if len(word) == 1)
    return single_character_count / len(words) > 0.20


def load_stop_words():
    global STOP_WORDS
    with CONTENT_STATE_LOCK:
        if STOP_WORDS is not None:
            return STOP_WORDS

        words = set()
        if os.path.exists(STOP_WORDS_FILE):
            with open(STOP_WORDS_FILE, "r", encoding="utf-8") as stop_file:
                words = {line.strip().lower() for line in stop_file if line.strip()}
        STOP_WORDS = words
        return STOP_WORDS


def hash_text(text):
    normalized = " ".join(text.lower().split())
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_simhash(tokens):
    token_list = [token for token in tokens if token and token not in load_stop_words()]
    if len(token_list) < SIMHASH_SHINGLE_SIZE:
        return None
    bit_weights = [0] * SIMHASH_BITS
    for index in range(len(token_list) - SIMHASH_SHINGLE_SIZE + 1):
        shingle = " ".join(token_list[index : index + SIMHASH_SHINGLE_SIZE]).encode(
            "utf-8"
        )
        digest = hashlib.sha1(shingle).digest()
        value = int.from_bytes(digest[:8], byteorder="big", signed=False)
        for bit_index in range(SIMHASH_BITS):
            bit_mask = 1 << bit_index
            bit_weights[bit_index] += 1 if value & bit_mask else -1

    signature = 0
    for bit_index, weight in enumerate(bit_weights):
        if weight >= 0:
            signature |= 1 << bit_index
    return signature


def hamming_distance(left, right):
    return (left ^ right).bit_count()


def simhash_band_keys(signature):
    for band_id in range(SIMHASH_BITS // SIMHASH_BAND_SIZE):
        shift = band_id * SIMHASH_BAND_SIZE
        value = (signature >> shift) & ((1 << SIMHASH_BAND_SIZE) - 1)
        yield (band_id, value)


def is_near_duplicate_simhash(signature):
    if signature is None:
        return False
    candidate_indexes = set()
    for band_key in simhash_band_keys(signature):
        for candidate_index in SIMHASH_BANDS.get(band_key, ()):
            candidate_indexes.add(candidate_index)
    for candidate_index in candidate_indexes:
        if (
            hamming_distance(signature, SEEN_SIMHASHES[candidate_index])
            <= SIMHASH_NEAR_DUP_THRESHOLD
        ):
            return True
    return False


def register_simhash(signature):
    if signature is None:
        return
    index = len(SEEN_SIMHASHES)
    SEEN_SIMHASHES.append(signature)
    for band_key in simhash_band_keys(signature):
        SIMHASH_BANDS.setdefault(band_key, []).append(index)


def record_fetch(
    url,
    resp,
    outgoing_links,
    content_hash,
    simhash,
    word_counts,
    raw_word_count,
    duplicate,
    near_duplicate,
):
    os.makedirs(ANALYTICS_DIR, exist_ok=True)
    status = getattr(resp, "status", None) if resp else None
    requested_url = normalize_link(url, url) or url
    final_url = getattr(resp, "url", None) if resp else None
    if resp and getattr(resp, "raw_response", None) is not None:
        final_url = getattr(resp.raw_response, "url", final_url)

    record = {
        "requested_url": requested_url,
        "final_url": normalize_link(url, final_url) if final_url else None,
        "status": status,
        "subdomain": get_subdomain(requested_url),
        "word_count": raw_word_count,
        "non_stop_word_count": sum(word_counts.values()),
        "content_hash": content_hash,
        "duplicate_content": duplicate,
        "near_duplicate_content": near_duplicate,
        "simhash64": f"{simhash:016x}" if simhash is not None else "",
        "outgoing_link_count": len(outgoing_links),
        "word_counts": dict(word_counts),
        "top_words": word_counts.most_common(50),
    }

    with ANALYTICS_LOCK:
        with open(
            os.path.join(ANALYTICS_DIR, "pages.jsonl"), "a", encoding="utf-8"
        ) as out:
            out.write(json.dumps(record, sort_keys=True) + "\n")


def get_subdomain(url):
    try:
        parsed = urlparse(url)
        return parsed.hostname.lower() if parsed.hostname else ""
    except (TypeError, ValueError):
        return ""
