# Web Crawler

A responsive, animated web interface backed by a bounded Python crawler. It
follows same-host HTTPS links, shows per-page results, and exports them as CSV.

## Deploy to Vercel

Import this GitHub repository into Vercel. Vercel serves `index.html` and the
static assets and deploys `api/crawl.py` as a Python Function. No third-party
Python packages are required.

## Run locally

Install the Vercel CLI, then run `vercel dev` from the project directory. The
local Python API can also be started with:

```powershell
python -m http.server 8000
```

The HTTP server only serves the static UI; use Vercel CLI to exercise `/api/crawl`.

## Crawl limits and safety

The API limits each request to six pages, three concurrent workers, a two-second
per-request timeout, and one megabyte per HTML response. It only connects to
publicly routable HTTPS hosts on port 443, rejects private or local DNS results,
and does not follow redirects. Only crawl sites you are authorized to access
and follow their terms of service and robots policies.
