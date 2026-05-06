from gig_ops.domain.models import ScanResult


class MCPScanner:
    def scan(self, query: str) -> list[ScanResult]:
        raise NotImplementedError("MCP scanner not yet implemented")
