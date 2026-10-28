"""Read a small set of official company pages without requiring search credentials."""
from dataclasses import asdict, dataclass
import re
import ssl
from urllib.parse import urldefrag, urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup

from business_email import published_emails
from company_public_data import SourceDocument, host, public_url
from request_limits import REQUEST_LIMITS, RequestDeferred
from run_support import EvidenceCache
from scraper_engine import lookup_budget
from app.utils.config import CACHE_DIR


@dataclass
class WebsiteEvidence:
    documents: tuple[SourceDocument, ...] = ()
    status: str = "Not Found"
    reason: str = ""
    cached: bool = False

    def matches(self, record):
        facts = [fact for doc in self.documents for fact in published_emails(doc, record)
                 if fact["_rank"] == 3]
        # Conflicting published addresses require review, never choose arbitrarily.
        return facts if len({fact["email"] for fact in facts}) == 1 else []


class WebsiteEmailLookup:
    def __init__(self, *, cache=None, metrics=None, control=None, timeout_seconds=8):
        self.cache = cache if cache is not None else EvidenceCache(
            CACHE_DIR / "website_emails.sqlite3", "official_pages_v1", ttl=86400, metrics=metrics)
        self.metrics = metrics
        self.control = control
        self.timeout_seconds = min(8, max(1, timeout_seconds))

    @staticmethod
    def allowed(url, domain):
        return (public_url(url) and (host(url) == domain or host(url).endswith("." + domain))
                and not any(domain == d or domain.endswith("." + d) for d in
                            ("linkedin.com", "facebook.com", "instagram.com", "twitter.com", "x.com")))

    @staticmethod
    def document(url, html):
        soup = BeautifulSoup(html, "html.parser")
        for node in soup(["script", "style", "noscript", "svg"]):
            node.decompose()
        links = []
        for link in soup.find_all("a", href=True):
            address = urljoin(url, link["href"])
            links.append({"url": address, "text": link.get_text(" ", strip=True),
                          "context": link.parent.get_text("\n", strip=True)[:550]})
        return SourceDocument(url, soup.title.get_text(" ", strip=True) if soup.title else "",
                              soup.get_text("\n", strip=True), links=links)

    def fetch(self, client, url, domain):
        for _ in range(4):
            if not self.allowed(url, domain):
                raise RequestDeferred("The website redirects outside the supplied company domain.")
            if self.control:
                self.control.checkpoint()
            with REQUEST_LIMITS.slot(url, budget=lookup_budget, metrics=self.metrics,
                                     checkpoint=self.control.checkpoint if self.control else None):
                with client.stream("GET", url, timeout=lookup_budget.timeout(self.timeout_seconds)) as response:
                    if response.status_code in {401, 403, 429, 503}:
                        REQUEST_LIMITS.cooldown(url, response.headers.get("Retry-After"))
                        raise RequestDeferred("The website is unavailable or requested a pause; retry later.")
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    response.raise_for_status()
                    if "html" not in response.headers.get("content-type", "").lower():
                        raise RequestDeferred("The website did not return a readable HTML page.")
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        lookup_budget.timeout(1)
                        if self.control:
                            self.control.checkpoint()
                        body.extend(chunk)
                        if len(body) > 2_000_000:
                            raise RequestDeferred("The page is too large for this lookup.")
                    doc = self.document(str(response.url), body.decode(response.encoding or "utf-8", errors="replace"))
                    if re.search(r"verify (?:that )?you are human|checking your browser|just a moment|"
                                 r"access denied|complete the captcha", doc.title + "\n" + doc.text[:1500], re.I):
                        REQUEST_LIMITS.cooldown(url, default=900)
                        raise RequestDeferred("The website requires verification; retry later.")
                    return doc
        raise RequestDeferred("The website redirected too many times.")

    def discover(self, domain, *, force_refresh=False):
        cached = None if force_refresh else self.cache.get(domain)
        if cached is not None:
            return WebsiteEvidence(tuple(SourceDocument(**doc) for doc in cached),
                                   reason="Reused public company pages.", cached=True)
        docs = []
        try:
            # Include the OS trust store (including managed Windows roots) while
            # retaining certificate and hostname validation.
            with httpx.Client(follow_redirects=False, verify=ssl.create_default_context(), headers={
                "User-Agent": "LeadWorkspace/1.0 (public business contact lookup)",
                "Accept": "text/html",
            }) as client:
                root = self.fetch(client, "https://" + domain + "/", domain)
                docs.append(root)
                seen = {urldefrag(root.url)[0]}
                links = []
                for link in root.links:
                    url = urldefrag(link["url"])[0]
                    if (url not in seen and self.allowed(url, domain) and not urlsplit(url).query
                            and re.search(r"contact|team|people|staff|leadership|about", url + " " + link["text"], re.I)):
                        seen.add(url)
                        links.append(url)
                # One homepage and at most two relevant, same-company linked pages.
                for url in links[:2]:
                    docs.append(self.fetch(client, url, domain))
            self.cache[domain] = [asdict(doc) for doc in docs]
            return WebsiteEvidence(tuple(docs), reason="Checked public company pages; no unique published address matched this person.")
        except lookup_budget.LookupTimeout:
            return WebsiteEvidence(tuple(docs), "Timed Out", "The 15-second lookup budget was reached; retry is available.")
        except (httpx.HTTPError, RequestDeferred) as exc:
            # Partial or blocked crawls must remain retryable, not cached negatives.
            return WebsiteEvidence(tuple(docs), "Search Error", str(exc))
