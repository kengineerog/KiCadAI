import json
import re
from pathlib import Path
from typing import Optional


class ToolRegistry:
    """
    Registry for MCP tools.
    Tools are discovered dynamically; the model can search for them.
    """

    def __init__(self, tools_dir: Path | str = Path("tools")):
        self.tools_dir = Path(tools_dir)
        self.tools_cache: dict[str, dict] = {}
        self._load_tools()

    def _load_tools(self):
        """Recursively load tool definitions from the tools/ directory."""
        if not self.tools_dir.exists():
            return

        for tool_file in sorted(self.tools_dir.rglob("*.json")):
            try:
                with tool_file.open("r", encoding="utf-8") as handle:
                    tools = json.load(handle)
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(tools, list):
                continue

            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                tool_name = tool.get("name")
                if tool_name:
                    self.tools_cache[tool_name] = tool

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    def search_tools(self, query: str) -> list[dict]:
        """
        Search for tools by keyword.
        Returns tools whose description or name matches the query.
        """
        query_tokens = [token for token in self._normalize_text(query).split() if token]
        if not query_tokens:
            return []

        matches = []
        for name, tool in self.tools_cache.items():
            haystacks = [
                self._normalize_text(name),
                self._normalize_text(str(tool.get("description", ""))),
            ]
            if any(all(token in haystack for token in query_tokens) for haystack in haystacks):
                matches.append(tool)

        return matches[:10]

    def get_tool(self, name: str) -> Optional[dict]:
        """Get a specific tool by name."""
        return self.tools_cache.get(name)

    def get_all_tools(self) -> list[dict]:
        """Get all tools (use sparingly; tools are discoverable via search)."""
        return list(self.tools_cache.values())

    def count_tools(self) -> int:
        """Total number of registered tools."""
        return len(self.tools_cache)
