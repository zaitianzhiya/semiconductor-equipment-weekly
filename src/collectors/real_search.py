"""Real web search collector — fetches actual news events via DDG + fallback skeleton."""

import hashlib
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional

import requests

from src.collectors.base import BaseCollector, EventRecord, SourceCitation

ARXIV_API = "http://export.arxiv.org/api/query"


def _fetch_arxiv(keywords: list[str], max_results: int = 5) -> list[dict]:
    query = " OR ".join(f'all:"{kw}"' for kw in keywords[:5])
    params = {"search_query": f"({query})", "sortBy": "submittedDate",
              "sortOrder": "descending", "max_results": max_results}
    try:
        resp = requests.get(ARXIV_API, params=params, timeout=30)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        results = []
        for entry in root.findall("atom:entry", ns):
            results.append({
                "title": " ".join((entry.find("atom:title", ns).text or "").split()),
                "url": entry.find("atom:id", ns).text,
                "snippet": " ".join((entry.find("atom:summary", ns).text or "").split())[:300],
                "published": (entry.find("atom:published", ns).text or "")[:10],
                "source": "arXiv",
            })
        return results
    except Exception as e:
        print(f"    [arXiv] {e}")
        return []


def _fetch_ddg(query: str, max_results: int = 3) -> list[dict]:
    """Quick DDG news search. Returns [] on rate limit or failure."""
    try:
        from ddgs import DDGS
        results = []
        with DDGS(timeout=10) as ddgs:
            for r in ddgs.news(query, max_results=max_results, timelimit="w"):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": (r.get("body", "") or "")[:300],
                    "published": r.get("date", ""),
                    "source": r.get("source", "News"),
                    "image": r.get("image", ""),
                })
        return results
    except ImportError:
        return []
    except Exception as e:
        msg = str(e).lower()
        if "ratelimit" in msg or "403" in msg:
            print(f"    [DDG] rate-limited, skipping")
        else:
            print(f"    [DDG] {str(e)[:80]}")
        return []


def _fetch_github_topics(topics: list[str], gh_token: Optional[str], max_results: int = 5) -> list[dict]:
    if not gh_token:
        return []
    query = " OR ".join(f"topic:{t}" for t in topics[:3])
    headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github+json"}
    params = {"q": query, "sort": "updated", "order": "desc", "per_page": max_results}
    try:
        resp = requests.get("https://api.github.com/search/repositories",
                            headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        results = []
        for item in resp.json().get("items", []):
            results.append({"title": item["full_name"], "url": item["html_url"],
                            "snippet": (item.get("description") or "")[:300],
                            "published": item.get("updated_at", "")[:10], "source": "GitHub"})
        return results
    except Exception as e:
        print(f"    [GitHub] {e}")
        return []


class RealSearchCollector(BaseCollector):
    """Collect real event content with a tiered strategy.

    Tier 1 sources → DuckDuckGo news (real, fresh content)
    Tier 2 sources → keyword skeleton (fast, no external API needed)
    RSS (arXiv) → arXiv API
    API (GitHub topics) → GitHub Search API
    """

    def __init__(self, config: dict, source_key: str):
        super().__init__(config)
        self.source_key = source_key
        src_cfg = self.config.get("sources", {}).get(source_key, {})
        self.source_name = src_cfg.get("name", source_key)
        self.tier = src_cfg.get("tier", 2)
        self.ecosystem = src_cfg.get("ecosystem", "unknown")
        self.src_type = src_cfg.get("type", "web_search")
        self.keywords = src_cfg.get("keywords", [])
        self.topics = src_cfg.get("topics", [])
        self.enabled = src_cfg.get("enabled", True)
        self.max_items = src_cfg.get("max_items", 5)
        self.gh_token = None

    def collect(self) -> list[EventRecord]:
        if not self.enabled:
            return []

        results = []

        if self.src_type == "rss":
            results = _fetch_arxiv(self.keywords, self.max_items)
        elif self.src_type == "api" and self.topics:
            results = _fetch_github_topics(self.topics, self.gh_token, self.max_items)
        elif self.keywords and self.tier == 1:
            # Tier 1: real DDG search with first keyword
            q = f"{self.source_name} {self.keywords[0]}"
            results = _fetch_ddg(q, max_results=self.max_items)
            if not results:
                return self._skeleton()
        else:
            return self._skeleton()

        return self._build_records(results) if results else self._skeleton()

    def _build_records(self, results: list[dict]) -> list[EventRecord]:
        records = []
        for r in results[:self.max_items]:
            eid = hashlib.md5(r["url"].encode()).hexdigest()[:12]
            records.append(EventRecord(
                event_id=f"{self.source_key}:{eid}",
                title=r.get("title", "")[:200],
                description=r.get("snippet", ""),
                url=r.get("url", ""),
                image_url=r.get("image", ""),
                organization=self.source_name,
                published_at=r.get("published", ""),
                raw_data={**r, "source_key": self.source_key, "tier": self.tier,
                          "ecosystem": self.ecosystem, "collector": "RealSearchCollector",
                          "collected_at": datetime.utcnow().isoformat()},
                citations=[SourceCitation(source_key=self.source_key, source_name=self.source_name,
                                          tier=self.tier, ecosystem=self.ecosystem, url=r.get("url", ""))],
            ))
        return records

    def _skeleton(self) -> list[EventRecord]:
        records = []
        for kw in self.keywords[:self.max_items]:
            eid = hashlib.md5(f"{self.source_key}:{kw}:{datetime.utcnow().strftime('%Y-W%V')}".encode()).hexdigest()[:12]
            records.append(EventRecord(
                event_id=f"{self.source_key}:{eid}",
                title=f"[{self.source_name}] {kw}",
                description=f"搜索词 '{kw}' — 本周暂无检索结果",
                organization=self.source_name,
                published_at=datetime.utcnow().strftime("%Y-%m-%d"),
                raw_data={"source_key": self.source_key, "tier": self.tier,
                          "ecosystem": self.ecosystem, "keyword": kw, "fallback": True},
                citations=[SourceCitation(source_key=self.source_key, source_name=self.source_name,
                                          tier=self.tier, ecosystem=self.ecosystem)],
            ))
        return records
