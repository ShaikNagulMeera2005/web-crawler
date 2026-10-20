import unittest
from unittest.mock import patch

from api import crawl as crawler


class FakeResponse:
    def __init__(self, html, status=200):
        self.status = status
        self.html = html.encode("utf-8")

    def getheader(self, name, default=""):
        if name.lower() == "content-type":
            return "text/html; charset=utf-8"
        return default

    def read(self, limit):
        return self.html[:limit]


class FakeConnection:
    pages = {}

    def __init__(self, hostname, address, timeout):
        self.hostname = hostname
        self.target = None

    def request(self, method, target, headers):
        self.target = target

    def getresponse(self):
        status, html = self.pages.get(self.target, (200, ""))
        return FakeResponse(html, status)

    def close(self):
        pass


class CrawlerTests(unittest.TestCase):
    def test_rejects_non_https_private_hosts_and_nonstandard_ports(self):
        for url in (
            "http://example.com",
            "https://localhost",
            "https://127.0.0.1",
            "https://example.com:8443",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                crawler.parse_url(url)

    def test_rejects_host_resolving_to_private_address(self):
        with patch.object(
            crawler.socket,
            "getaddrinfo",
            return_value=[(None, None, None, None, ("192.168.1.10", 443))],
        ):
            with self.assertRaisesRegex(ValueError, "Private"):
                crawler.ensure_public_host("example.com")

    def test_crawl_obeys_page_limit_and_reports_discovered_links(self):
        FakeConnection.pages = {
            "/": (
                200,
                '<a href="/one">One</a><a href="/two">Two</a>'
                '<a href="/three">Three</a><a href="https://elsewhere.test/">Elsewhere</a>',
            ),
            "/one": (200, "<p>One</p>"),
            "/two": (200, "<p>Two</p>"),
            "/three": (200, "<p>Three</p>"),
        }
        with (
            patch.object(crawler, "ensure_public_host", return_value=["93.184.216.34"]),
            patch.object(crawler, "PinnedHTTPSConnection", FakeConnection),
        ):
            result = crawler.crawl("https://example.com", max_pages=3)

        self.assertEqual(len(result["pages"]), 3)
        self.assertEqual(
            result["unique_links"],
            [
                "https://example.com/one",
                "https://example.com/three",
                "https://example.com/two",
            ],
        )

    def test_does_not_follow_redirects(self):
        FakeConnection.pages = {"/": (302, "")}
        with (
            patch.object(crawler, "ensure_public_host", return_value=["93.184.216.34"]),
            patch.object(crawler, "PinnedHTTPSConnection", FakeConnection),
        ):
            page_url, links, error = crawler.fetch_page(
                "https://example.com", "example.com", "93.184.216.34"
            )

        self.assertEqual(page_url, "https://example.com/")
        self.assertEqual(links, [])
        self.assertEqual(error, "Skipped: redirects are blocked")


if __name__ == "__main__":
    unittest.main()
