const form = document.querySelector("#crawl-form");
const crawlButton = document.querySelector("#crawl-button");
const activity = document.querySelector("#activity");
const statusMessage = document.querySelector("#status-message");
const resultsSection = document.querySelector("#results");
const errorMessage = document.querySelector("#error-message");
const resultsBody = document.querySelector("#results-body");
const linksList = document.querySelector("#links-list");
const downloadButton = document.querySelector("#download-button");
let latestResults = null;

function safeText(element, value) {
  element.textContent = value;
}

function hideError() {
  errorMessage.classList.add("hidden");
  safeText(errorMessage, "");
}

function showError(message) {
  safeText(errorMessage, message);
  errorMessage.classList.remove("hidden");
}

function renderResults(data) {
  latestResults = data;
  const uniqueLinks = data.unique_links;
  safeText(document.querySelector("#pages-count"), String(data.pages.length));
  safeText(
    document.querySelector("#success-count"),
    String(data.pages.filter((page) => !page.error).length),
  );
  safeText(document.querySelector("#links-count"), String(uniqueLinks.length));
  safeText(document.querySelector("#links-summary-count"), `${uniqueLinks.length} links`);
  resultsBody.replaceChildren();

  for (const result of data.pages) {
    const row = document.createElement("tr");
    const urlCell = document.createElement("td");
    const countCell = document.createElement("td");
    const statusCell = document.createElement("td");
    const badge = document.createElement("span");
    urlCell.className = "url-cell";
    safeText(urlCell, result.url);
    safeText(countCell, String(result.links_found));
    badge.className = `status-pill${result.error ? " failed" : ""}`;
    safeText(badge, result.error || "OK");
    statusCell.append(badge);
    row.append(urlCell, countCell, statusCell);
    resultsBody.append(row);
  }

  linksList.replaceChildren();
  for (const link of uniqueLinks) {
    const item = document.createElement("li");
    const anchor = document.createElement("a");
    anchor.href = link;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    safeText(anchor, link);
    item.append(anchor);
    linksList.append(item);
  }
  resultsSection.classList.remove("hidden");
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  hideError();
  resultsSection.classList.add("hidden");
  activity.classList.remove("hidden");
  crawlButton.disabled = true;
  safeText(statusMessage, "Checking the URL and mapping same-host links…");

  const formData = new FormData(form);
  try {
    const response = await fetch("/api/crawl", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: formData.get("url"),
        max_pages: Number(formData.get("max_pages")),
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || `Request failed (${response.status}).`);
    }
    renderResults(payload);
    safeText(statusMessage, `Crawled ${payload.pages.length} pages.`);
  } catch (error) {
    showError(error instanceof Error ? error.message : "The crawl could not be completed.");
  } finally {
    activity.classList.add("hidden");
    crawlButton.disabled = false;
  }
});

downloadButton.addEventListener("click", () => {
  if (!latestResults) return;
  const csvEscape = (value) => `"${String(value).replaceAll('"', '""')}"`;
  const rows = [
    ["url", "links_found", "status"],
    ...latestResults.pages.map((page) => [
      page.url,
      page.links_found,
      page.error || "OK",
    ]),
  ];
  const csv = rows.map((row) => row.map(csvEscape).join(",")).join("\r\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "crawl_results.csv";
  anchor.click();
  URL.revokeObjectURL(url);
});
