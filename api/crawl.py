import concurrent.futures
import http.client
import ipaddress
import json
import ssl
import socket
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler
from urllib.parse import urljoin, urlsplit, urlunsplit


MAX_PAGES = 6
MAX_WORKERS = 3
REQUEST_TIMEOUT = 2
MAX_HTML_BYTES = 1_000_000
MAX_RETURNED_LINKS = 200


class LinkParser(HTMLParser):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value:
                resolved = urljoin(self.base_url, value).split("#", 1)[0]
                if resolved:
                    self.links.append(resolved)


def parse_url(url):
    if not isinstance(url, str) or len(url) > 2048:
        raise ValueError("Enter a valid HTTPS URL.")
    try:
        parsed = urlsplit(url.strip())
        port = parsed.port
    except ValueError as error:
        raise ValueError("Enter a valid HTTPS URL.") from error

    hostname = parsed.hostname
    if (
        parsed.scheme.lower() != "https"
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or hostname.endswith(".")
        or hostname.lower() in ("localhost",)
        or hostname.lower().endswith((".localhost", ".local", ".internal"))
    ):
        raise ValueError("Only public HTTPS URLs on port 443 are allowed.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("Private, local, or non-public network hosts are blocked.")

    return parsed, hostname.lower()


def ensure_public_host(hostname):
    try:
        addresses = {
            ipaddress.ip_address(record[4][0])
            for record in socket.getaddrinfo(
                hostname, 443, type=socket.SOCK_STREAM
            )
        }
    except (OSError, ValueError) as error:
        raise ValueError("The URL host could not be resolved.") from error
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Private, local, or non-public network hosts are blocked.")
    return [str(address) for address in addresses]


def normalize_url(url):
    parsed, hostname = parse_url(url)
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return (
        urlunsplit(("https", parsed.netloc.lower(), path, parsed.query, "")),
        hostname,
        parsed,
    )


def fetch_page(url, hostname, address):
    connection = None
    try:
        normalized_url, _, parsed = normalize_url(url)
        connection = PinnedHTTPSConnection(hostname, address, REQUEST_TIMEOUT)
        target = parsed.path or "/"
        if parsed.query:
            target = f"{target}?{parsed.query}"
        connection.request(
            "GET",
            target,
            headers={
                "Host": parsed.netloc,
                "User-Agent": "WebCrawlerDemo/1.0",
                "Accept": "text/html",
            },
        )
        response = connection.getresponse()
        if 300 <= response.status < 400:
            return normalized_url, [], "Skipped: redirects are blocked"
        if response.status < 200 or response.status >= 300:
            return normalized_url, [], f"HTTP {response.status}"
        if "text/html" not in response.getheader("Content-Type", "").lower():
            return normalized_url, [], "Skipped: response is not HTML"
        content = response.read(MAX_HTML_BYTES + 1)
        if len(content) > MAX_HTML_BYTES:
            return normalized_url, [], "Skipped: HTML response exceeds 1 MB"
        parser = LinkParser(normalized_url)
        parser.feed(content.decode("utf-8", errors="ignore"))
        return normalized_url, parser.links, ""
    except (http.client.HTTPException, OSError, TimeoutError, ssl.SSLError) as error:
        return url, [], f"Request failed: {error}"
    finally:
        if connection is not None:
            connection.close()


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname, address, timeout):
        super().__init__(
            hostname,
            port=443,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self.address = address

    def connect(self):
        raw_socket = socket.create_connection(
            (self.address, self.port), self.timeout
        )
        self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)


def crawl(start_url, max_pages):
    start, base_hostname, _ = normalize_url(start_url)
    addresses = ensure_public_host(base_hostname)
    pages = []
    visited = {start}
    discovered_links = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        pending = {executor.submit(fetch_page, start, base_hostname, addresses[0])}
        while pending:
            done, pending = concurrent.futures.wait(
                pending, return_when=concurrent.futures.FIRST_COMPLETED
            )
            for future in done:
                page_url, discovered, error = future.result()
                pages.append(
                    {
                        "url": page_url,
                        "links_found": len(discovered),
                        "error": error,
                    }
                )
                if error:
                    continue
                for link in discovered:
                    try:
                        normalized, hostname, _ = normalize_url(link)
                    except ValueError:
                        continue
                    if hostname != base_hostname:
                        continue
                    discovered_links.add(normalized)
                    if len(visited) < max_pages and normalized not in visited:
                        visited.add(normalized)
                        pending.add(
                            executor.submit(
                                fetch_page, normalized, base_hostname, addresses[0]
                            )
                        )
    return {
        "pages": pages,
        "unique_links": sorted(discovered_links)[:MAX_RETURNED_LINKS],
    }


def respond(handler, status, payload):
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            respond(self, 400, {"error": "Invalid Content-Length header."})
            return
        if size <= 0 or size > 4096:
            respond(self, 400, {"error": "Invalid request size."})
            return
        try:
            payload = json.loads(self.rfile.read(size))
        except (json.JSONDecodeError, UnicodeDecodeError):
            respond(self, 400, {"error": "Request body must be valid JSON."})
            return
        if not isinstance(payload, dict):
            respond(self, 400, {"error": "Request body must be a JSON object."})
            return
        requested_limit = payload.get("max_pages", 6)
        if isinstance(requested_limit, bool) or not isinstance(requested_limit, int):
            respond(self, 400, {"error": "Page limit must be an integer."})
            return
        if not 1 <= requested_limit <= MAX_PAGES:
            respond(self, 400, {"error": f"Page limit must be between 1 and {MAX_PAGES}."})
            return
        try:
            result = crawl(payload.get("url"), requested_limit)
        except ValueError as error:
            respond(self, 400, {"error": str(error)})
            return
        respond(self, 200, result)
