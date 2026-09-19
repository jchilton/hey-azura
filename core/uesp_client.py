import requests
import json
import re
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class UESPClient:
    """Client for querying the Unofficial Elder Scrolls Pages (UESP) MediaWiki API."""

    def __init__(self, api_url: str = "https://en.uesp.net/w/api.php"):
        self.api_url = api_url
        self.headers = {
            "User-Agent": "MorrowindAzuraCompanion/1.0 (https://github.com/hey-azura)"
        }
        self.cache: Dict[str, Any] = {}

    def _extract_keywords(self, query: str) -> str:
        """Strip conversational filler phrases and contractions to isolate the core entity/keyword."""
        cleaned = query.strip().lower()
        
        # Strip contractions like where's, wheres, where s, what's, etc.
        cleaned = re.sub(r"^(where|what|who|how|why|which)['’]?s\b", r"\1", cleaned)
        cleaned = re.sub(r"^(where|what|who|how|why|which)\s+s\b", r"\1", cleaned)
        
        filler_patterns = [
            r"^where\s+(can\s+i|do\s+i|to|is|are|was|were)\s+(find|get|locate|see)?\b",
            r"^where\s+(is|are|was|were)\b",
            r"^where\b",
            r"^how\s+(can\s+i|do\s+i|to)\s+(get|find|reach|beat|cure|kill|finish|start)?\b",
            r"^how\s+(do\s+i|can\s+i|is|are)\b",
            r"^how\b",
            r"^who\s+(is|are|gives|starts|has)\b",
            r"^who\b",
            r"^what\s+(is|are|does|happens)\b",
            r"^what\b",
            r"^tell\s+me\s+about\b",
            r"^can\s+you\s+tell\s+me\s+about\b",
            r"^i\s+need\s+to\s+find\b"
        ]
        for pat in filler_patterns:
            cleaned = re.sub(pat, "", cleaned).strip()

        # Remove leading articles and stray single letters
        cleaned = re.sub(r"^(the|a|an|s)\s+", "", cleaned).strip()
        # Remove trailing quest/item words if at end of longer phrase
        cleaned = re.sub(r"\s+(quest|item|location)$", "", cleaned).strip()
        cleaned = cleaned.strip("?\"'., ")
        return cleaned if len(cleaned) >= 2 else query.strip()

    def _is_title_allowed(self, title: str, data_sources: Optional[Dict[str, bool]]) -> bool:
        if not data_sources:
            return True
        allow_goty = data_sources.get("goty", True)
        allow_tr = data_sources.get("tamriel_rebuilt", True)
        
        t_low = title.lower()
        if not allow_goty and ("tribunal" in t_low or "bloodmoon" in t_low):
            return False
        if not allow_tr and ("tamriel rebuilt" in t_low or "tr:" in t_low or "poison song" in t_low):
            return False
        return True

    def search(self, query: str, limit: int = 4, data_sources: Optional[Dict[str, bool]] = None) -> List[Dict[str, str]]:
        """
        Search UESP for articles matching query:
        1. Clean conversational filler to isolate core entity.
        2. Check exact and prefix title matches via OpenSearch across Morrowind: and Tamriel Rebuilt:.
        3. Filter out disabled expansions/data sources (GOTY / Tamriel Rebuilt).
        """
        cache_key = f"search_{query}_{limit}_{data_sources}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        kwd = self._extract_keywords(query)
        results = []
        seen_titles = set()

        # Build list of title namespaces based on allowed data sources (including singular variations for plural queries)
        kwd_singular = kwd
        if kwd.endswith("s") and len(kwd) > 3 and not kwd.endswith("ss"):
            if kwd.endswith("ves") and len(kwd) > 4:
                kwd_singular = kwd[:-3] + "f"
            elif kwd.endswith("ies") and len(kwd) > 4:
                kwd_singular = kwd[:-3] + "y"
            else:
                kwd_singular = kwd[:-1]

        keywords_to_try = [kwd]
        if kwd_singular != kwd:
            keywords_to_try.append(kwd_singular)

        title_searches = []
        for k in keywords_to_try:
            title_searches.append(f"Morrowind:{k}")
            if not data_sources or data_sources.get("goty", True):
                title_searches.extend([f"Bloodmoon:{k}", f"Tribunal:{k}"])
            if not data_sources or data_sources.get("tamriel_rebuilt", True):
                title_searches.append(f"Tamriel Rebuilt:{k}")
            title_searches.extend([f"Lore:{k}", k])

        for ts in title_searches:
            try:
                r = requests.get(
                    self.api_url,
                    params={"action": "opensearch", "search": ts, "limit": limit, "format": "json"},
                    headers=self.headers,
                    timeout=4
                )
                if r.status_code == 200:
                    data = r.json()
                    titles = data[1] if len(data) > 1 else []
                    urls = data[3] if len(data) > 3 else []
                    for i, t in enumerate(titles):
                        if t not in seen_titles and self._is_title_allowed(t, data_sources):
                            seen_titles.add(t)
                            u = urls[i] if i < len(urls) else f"https://en.uesp.net/wiki/{t.replace(' ', '_')}"
                            results.append({
                                "title": t,
                                "snippet": f"Article titled '{t}'",
                                "url": u
                            })
            except Exception as e:
                logger.debug(f"OpenSearch error on '{ts}': {e}")

            if len(results) >= limit:
                break

        # Phase 2: Full-text search to fill remaining slots or if no title match
        if len(results) < limit:
            full_text_queries = []
            for k in keywords_to_try:
                full_text_queries.append(f"Morrowind:{k}")
                if not data_sources or data_sources.get("goty", True):
                    full_text_queries.extend([f"Bloodmoon:{k}", f"Tribunal:{k}"])
                if not data_sources or data_sources.get("tamriel_rebuilt", True):
                    full_text_queries.append(f"Tamriel Rebuilt:{k}")
                full_text_queries.extend([k, query])
            for sq in full_text_queries:
                params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": sq,
                    "format": "json",
                    "srlimit": limit
                }
                try:
                    res = requests.get(self.api_url, params=params, headers=self.headers, timeout=5)
                    if res.status_code == 200:
                        data = res.json()
                        search_hits = data.get("query", {}).get("search", [])
                        for hit in search_hits:
                            title = hit.get("title", "")
                            snippet = self._clean_html(hit.get("snippet", ""))
                            if title not in seen_titles:
                                seen_titles.add(title)
                                results.append({
                                    "title": title,
                                    "snippet": snippet,
                                    "pageid": hit.get("pageid"),
                                    "url": f"https://en.uesp.net/wiki/{title.replace(' ', '_')}"
                                })
                except Exception as e:
                    logger.debug(f"Full-text search error on '{sq}': {e}")

                if len(results) >= limit:
                    break

        self.cache[cache_key] = results[:limit]
        return results[:limit]

    def get_article_summary(self, title: str) -> Optional[str]:
        """Fetch article extract by title (including location/quest sections)."""
        cache_key = f"summary_{title}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Use exintro first, but allow up to 1500 chars so location paragraphs are preserved
        params = {
            "action": "query",
            "prop": "extracts",
            "exchars": 1500,
            "explaintext": True,
            "titles": title,
            "format": "json"
        }
        try:
            response = requests.get(self.api_url, params=params, headers=self.headers, timeout=5)
            if response.status_code == 200:
                data = response.json()
                pages = data.get("query", {}).get("pages", {})
                for page_id, page in pages.items():
                    if page_id != "-1":
                        extract = page.get("extract", "").strip()
                        if extract:
                            self.cache[cache_key] = extract
                            return extract
        except Exception as e:
            logger.warning(f"[UESP Extract Warning] Title '{title}' error: {e}")

        return None

    def _clean_html(self, raw_html: str) -> str:
        """Strip HTML tags and unescape search snippets."""
        clean = re.sub(r'<[^>]+>', '', raw_html)
        clean = clean.replace('&quot;', '"').replace('&amp;', '&').replace('&#039;', "'")
        return clean.strip()
