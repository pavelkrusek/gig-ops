from gig_ops.domain.models import ScanResult
from gig_ops.log import logger
from gig_ops.settings import get_settings


class TavilyScanner:
    def __init__(self) -> None:
        from tavily import TavilyClient
        self._client = TavilyClient(api_key=get_settings().tavily_api_key)

    def scan(self, query: str) -> list[ScanResult]:
        logger.info("Tavily scan: {}", query)
        response = self._client.search(query, max_results=10, include_raw_content=True)
        results = []
        for item in response.get("results", []):
            results.append(ScanResult(
                name=item.get("title", ""),
                url=item.get("url"),
                source="tavily",
                source_confidence="medium",
                raw_text=item.get("raw_content") or item.get("content"),
            ))
        logger.info("Tavily returned {} results", len(results))
        return results
