import concurrent.futures
import csv
from html.parser import HTMLParser
from io import StringIO
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import streamlit as st


class LinkParser(HTMLParser):
    """Extract absolute HTTP/HTTPS links from HTML content."""

    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for attr, value in attrs:
                if attr == "href" and value:
                    resolved = urljoin(self.base_url, value)
                    clean_url = resolved.split("#")[0].rstrip("/")
                    if clean_url.startswith(("http://", "https://")):
                        self.links.append(clean_url)


class MultiThreadedCrawler:
    """Crawl pages on the seed URL's domain using a bounded worker pool."""

    def __init__(self, start_url, max_threads=5, max_pages=30, timeout=5):
        self.start_url = start_url.rstrip("/")
        self.base_domain = urlparse(self.start_url).netloc.lower()
        self.max_threads = max_threads
        self.max_pages = max_pages
        self.timeout = timeout

    def is_same_domain(self, url):
        return urlparse(url).netloc.lower() == self.base_domain

    def fetch_page(self, url):
        """Fetch one page and return its links or a displayable network error."""
        headers = {"User-Agent": "Mozilla/5.0 (compatible; PythonBot/1.0)"}
        request = Request(url, headers=headers)

        try:
            with urlopen(request, timeout=self.timeout) as response:
                content_type = response.headers.get("Content-Type", "")
                if "text/html" not in content_type.lower():
                    return url, [], "Skipped: response is not HTML"

                html_data = response.read().decode("utf-8", errors="ignore")
                parser = LinkParser(url)
                parser.feed(html_data)
                return url, parser.links, ""
        except HTTPError as error:
            return url, [], f"HTTP {error.code}: {error.reason}"
        except (URLError, TimeoutError, OSError) as error:
            return url, [], f"Request failed: {error}"

    def run(self, progress_callback=None):
        results = []
        visited = {self.start_url}

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_threads
        ) as executor:
            future_to_url = {
                executor.submit(self.fetch_page, self.start_url): self.start_url
            }

            while future_to_url:
                done, _ = concurrent.futures.wait(
                    future_to_url,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )

                for future in done:
                    url = future_to_url.pop(future)
                    crawled_url, links, error = future.result()
                    result = {
                        "url": crawled_url,
                        "links_found": len(links),
                        "error": error,
                        "links": links,
                    }
                    results.append(result)

                    if progress_callback:
                        progress_callback(len(results), crawled_url, len(links), error)

                    for link in links:
                        if len(visited) >= self.max_pages:
                            break
                        if self.is_same_domain(link) and link not in visited:
                            visited.add(link)
                            future_to_url[executor.submit(self.fetch_page, link)] = link

        return results


def validate_start_url(value):
    try:
        parsed = urlparse(value.strip())
        valid_url = (
            parsed.scheme.lower() in ("http", "https")
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
        )
        if valid_url:
            parsed.port
        return valid_url
    except ValueError:
        return False


def make_csv(results):
    output = StringIO()
    writer = csv.DictWriter(
        output, fieldnames=("url", "links_found", "status"), lineterminator="\n"
    )
    writer.writeheader()
    for result in results:
        writer.writerow(
            {
                "url": result["url"],
                "links_found": result["links_found"],
                "status": result["error"] or "OK",
            }
        )
    return output.getvalue()


st.set_page_config(page_title="Website Link Crawler", page_icon="🔎", layout="wide")
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

    :root {
        --ink: #f3f5ff;
        --muted: #9da8c4;
        --cyan: #58e1de;
        --violet: #a78bfa;
        --panel: rgba(17, 25, 47, .82);
        --line: rgba(164, 184, 226, .14);
    }

    .stApp {
        color: var(--ink);
        background:
            radial-gradient(ellipse at 12% 0%, rgba(66, 111, 206, .2), transparent 38rem),
            radial-gradient(ellipse at 92% 18%, rgba(112, 64, 180, .18), transparent 34rem),
            #080d19;
        font-family: 'DM Sans', sans-serif;
    }
    [data-testid="stHeader"] { background: transparent; }
    [data-testid="stMainBlockContainer"] {
        max-width: 1120px;
        padding-top: 3rem;
        padding-bottom: 5rem;
    }
    h1, h2, h3, [data-testid="stMetricValue"] {
        font-family: 'Space Grotesk', sans-serif !important;
    }
    .hero {
        position: relative;
        isolation: isolate;
        overflow: hidden;
        padding: clamp(2rem, 5vw, 4.5rem);
        margin-bottom: 2rem;
        border: 1px solid rgba(143, 167, 220, .2);
        border-radius: 30px;
        background: linear-gradient(120deg, rgba(22, 34, 63, .95), rgba(15, 21, 42, .78));
        box-shadow: 0 24px 80px rgba(0, 0, 0, .28), inset 0 1px rgba(255,255,255,.06);
        animation: rise-in .7s cubic-bezier(.2,.75,.3,1) both;
    }
    .hero::before, .hero::after {
        content: "";
        position: absolute;
        z-index: -1;
        width: 18rem;
        height: 18rem;
        right: -4rem;
        top: -7rem;
        border: 1px solid rgba(88, 225, 222, .2);
        border-radius: 50%;
        box-shadow: 0 0 80px rgba(88,225,222,.1), inset 0 0 60px rgba(167,139,250,.08);
        animation: orbit-glow 12s ease-in-out infinite alternate;
    }
    .hero::after {
        width: 12rem;
        height: 12rem;
        right: 5rem;
        top: 3rem;
        border-color: rgba(167, 139, 250, .25);
        animation-delay: -4s;
    }
    .eyebrow {
        display: inline-flex;
        align-items: center;
        gap: .5rem;
        padding: .45rem .8rem;
        margin-bottom: 1.1rem;
        border: 1px solid rgba(88,225,222,.25);
        border-radius: 999px;
        background: rgba(88,225,222,.07);
        color: #91f4ed;
        font-size: .75rem;
        font-weight: 700;
        letter-spacing: .12em;
        text-transform: uppercase;
    }
    .eyebrow-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: var(--cyan);
        box-shadow: 0 0 12px var(--cyan);
        animation: pulse 1.8s ease-in-out infinite;
    }
    .hero h1 {
        margin: 0;
        color: #f4f6ff;
        font-size: clamp(2.5rem, 7vw, 5rem);
        font-weight: 700;
        letter-spacing: -.065em;
        line-height: 1;
    }
    .hero h1 span {
        background: linear-gradient(95deg, #76f0e5 5%, #9bb6ff 52%, #c6a6ff 95%);
        background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .hero-copy {
        max-width: 38rem;
        margin: 1.2rem 0 0;
        color: #aab5d0;
        font-size: 1.05rem;
        line-height: 1.7;
    }
    .section-heading {
        margin: 2.2rem 0 .9rem;
        color: #f2f4ff;
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1.3rem;
        font-weight: 600;
        letter-spacing: -.025em;
    }
    div[data-testid="stForm"] {
        padding: clamp(1.2rem, 3vw, 2rem);
        border: 1px solid var(--line);
        border-radius: 24px;
        background: var(--panel);
        box-shadow: 0 18px 55px rgba(0,0,0,.22);
        backdrop-filter: blur(16px);
        animation: rise-in .8s .08s both;
    }
    [data-testid="stWidgetLabel"] p {
        color: #d4dcf1;
        font-size: .9rem;
        font-weight: 600;
    }
    [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input {
        border: 1px solid rgba(164,184,226,.2);
        border-radius: 12px;
        background: rgba(7,13,27,.8);
        color: #f3f5ff;
        transition: border-color .2s, box-shadow .2s;
    }
    [data-testid="stTextInput"] input:focus, [data-testid="stNumberInput"] input:focus {
        border-color: rgba(88,225,222,.75);
        box-shadow: 0 0 0 3px rgba(88,225,222,.12);
    }
    div.stButton > button, div[data-testid="stFormSubmitButton"] button,
    div[data-testid="stDownloadButton"] button {
        min-height: 2.8rem;
        border: 1px solid rgba(127,239,230,.45);
        border-radius: 12px;
        background: linear-gradient(100deg, #46cfc8, #829cfb 58%, #a983ed);
        color: #08111d;
        font-weight: 700;
        box-shadow: 0 8px 24px rgba(84,185,220,.16);
        transition: transform .2s ease, box-shadow .2s ease, filter .2s ease;
    }
    div.stButton > button:hover, div[data-testid="stFormSubmitButton"] button:hover,
    div[data-testid="stDownloadButton"] button:hover {
        transform: translateY(-2px);
        filter: brightness(1.08);
        box-shadow: 0 12px 30px rgba(84,185,220,.28);
        color: #08111d;
    }
    div[data-testid="stMetric"] {
        padding: 1.25rem 1.4rem;
        border: 1px solid var(--line);
        border-radius: 20px;
        background: linear-gradient(145deg, rgba(22,32,57,.9), rgba(14,21,39,.9));
        box-shadow: 0 14px 38px rgba(0,0,0,.18);
        animation: rise-in .55s both;
        transition: transform .2s, border-color .2s;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-4px);
        border-color: rgba(88,225,222,.4);
    }
    [data-testid="stMetricLabel"] p { color: var(--muted); font-weight: 600; }
    [data-testid="stMetricValue"] { color: #f4f6ff; }
    [data-testid="stDataFrame"] {
        overflow: hidden;
        border: 1px solid var(--line);
        border-radius: 18px;
        background: rgba(15,22,41,.8);
    }
    [data-testid="stExpander"] {
        border: 1px solid var(--line);
        border-radius: 16px;
        background: rgba(15,22,41,.65);
    }
    [data-testid="stProgressBar"] > div > div {
        background: linear-gradient(90deg, #51dcd4, #9c8df3);
        background-size: 200% 100%;
        animation: progress-shimmer 2s linear infinite;
    }
    [data-testid="stAlert"] { border-radius: 14px; }
    @keyframes rise-in {
        from { opacity: 0; transform: translateY(16px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes pulse {
        50% { opacity: .55; box-shadow: 0 0 4px var(--cyan); }
    }
    @keyframes orbit-glow {
        to { transform: translate(-1rem, 1rem) rotate(18deg); }
    }
    @keyframes progress-shimmer {
        to { background-position: -200% 0; }
    }
    @media (max-width: 640px) {
        [data-testid="stMainBlockContainer"] { padding: 1.2rem 1rem 3rem; }
        .hero { border-radius: 22px; }
        .hero::before { right: -10rem; }
    }
    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after {
            animation-duration: .01ms !important;
            animation-iteration-count: 1 !important;
            scroll-behavior: auto !important;
            transition-duration: .01ms !important;
        }
    }
    </style>
    <section class="hero">
        <div class="eyebrow"><span class="eyebrow-dot"></span> Intelligent web discovery</div>
        <h1>Find your next<br><span>connection.</span></h1>
        <p class="hero-copy">
            Explore a website one page at a time. Uncover its same-domain links
            with a fast, live-updating crawler.
        </p>
    </section>
    """,
    unsafe_allow_html=True,
)
st.markdown('<div class="section-heading">Configure your crawl</div>', unsafe_allow_html=True)

with st.form("crawler_settings"):
    start_url = st.text_input(
        "Starting URL", value="https://books.toscrape.com"
    ).strip()
    left, middle, right = st.columns(3)
    with left:
        max_pages = st.number_input(
            "Maximum pages", min_value=1, max_value=100, value=15, step=1
        )
    with middle:
        max_threads = st.number_input(
            "Concurrent workers", min_value=1, max_value=20, value=6, step=1
        )
    with right:
        timeout = st.number_input(
            "Request timeout (seconds)", min_value=1, max_value=60, value=5, step=1
        )
    submitted = st.form_submit_button("Start crawl", type="primary")

if submitted:
    if not validate_start_url(start_url):
        st.error("Enter a valid HTTP or HTTPS URL without embedded credentials.")
    else:
        st.markdown('<div class="section-heading">Live crawl</div>', unsafe_allow_html=True)
        progress = st.progress(0.0)
        status = st.empty()

        def update_progress(count, url, link_count, error):
            _ = progress.progress(min(count / max_pages, 1.0))
            outcome = f" — {error}" if error else f" — found {link_count} links"
            _ = status.write(f"**{count}/{max_pages}** Crawled `{url}`{outcome}")

        crawler = MultiThreadedCrawler(
            start_url=start_url,
            max_threads=int(max_threads),
            max_pages=int(max_pages),
            timeout=int(timeout),
        )
        with st.spinner("Crawling pages..."):
            results = crawler.run(progress_callback=update_progress)

        successful = sum(not result["error"] for result in results)
        unique_links = {
            link for result in results for link in result["links"]
        }
        st.success(f"Crawl finished: {len(results)} pages processed.")

        st.markdown('<div class="section-heading">Your crawl at a glance</div>', unsafe_allow_html=True)
        metric_columns = st.columns(3)
        metric_columns[0].metric("Pages crawled", len(results))
        metric_columns[1].metric("Successful HTML pages", successful)
        metric_columns[2].metric("Unique links found", len(unique_links))

        st.markdown('<div class="section-heading">Crawled pages</div>', unsafe_allow_html=True)
        st.dataframe(
            [
                {
                    "URL": result["url"],
                    "Links found": result["links_found"],
                    "Status": result["error"] or "OK",
                }
                for result in results
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.download_button(
            "Download results as CSV",
            data=make_csv(results),
            file_name="crawl_results.csv",
            mime="text/csv",
        )

        with st.expander(f"View {len(unique_links)} unique discovered links"):
            for link in sorted(unique_links):
                st.write(link)
