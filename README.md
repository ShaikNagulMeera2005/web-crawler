# Web Crawler

A multithreaded, same-domain link crawler with a Streamlit interface. Set a
starting URL, page limit, worker count, and request timeout to inspect a site.
Results include per-page link counts, unique discovered links, and a CSV
download.

## Run locally

```powershell
python -m pip install -r requirements.txt
python -m streamlit run web.py
```

The default starting URL is `https://books.toscrape.com`. Only crawl websites
you are authorized to access, and follow their terms of service and robots
policies.
