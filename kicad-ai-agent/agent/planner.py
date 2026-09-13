import re
import inspect
from pathlib import Path
from typing import Any, Dict, List


class AgentPlanner:
    """Phase 5 planning loop for component research and generation."""

    def __init__(self, tool_registry, research_mcp, kicad_mcp, component_generator):
        self.tool_registry = tool_registry
        self.research_mcp = research_mcp
        self.kicad_mcp = kicad_mcp
        self.component_generator = component_generator

    def plan(self, goal: str) -> Dict[str, Any]:
        """Turn a goal into a compact execution plan."""
        component = self._extract_component_name(goal)
        tool_matches = self.tool_registry.search_tools(goal)
        steps = [
            {"id": "research", "tool": "research.advanced_search", "goal": f"Find {component} documentation"},
            {"id": "pinout", "tool": "research.extract_pdf_pinout", "goal": f"Extract pinout for {component}"},
            {"id": "package", "tool": "research.extract_package_data", "goal": f"Extract package data for {component}"},
            {"id": "symbol", "tool": "component.generate_symbol", "goal": f"Generate {component} symbol"},
            {"id": "footprint", "tool": "component.generate_footprint", "goal": f"Generate {component} footprint"},
            {"id": "evidence", "tool": "component.create_evidence_record", "goal": f"Track evidence for {component}"},
        ]
        return {
            "component": component,
            "goal": goal,
            "tool_candidates": [item.get("name") for item in tool_matches[:5]],
            "steps": steps,
        }

    def _extract_component_name(self, goal: str) -> str:
        match = re.search(r"([A-Z][A-Za-z0-9]+\d+[A-Za-z0-9]*)", goal)
        if match:
            return match.group(1)
        match = re.search(r"([A-Za-z]+\d+[A-Za-z]*)", goal)
        if match:
            return match.group(1)
        return "Component"

    async def _emit(self, callback, event_type: str, message: str, data: Dict[str, Any] | None = None):
        if callback is None:
            return
        event = {"type": event_type, "message": message, "data": data or {}}
        result = callback(event)
        if inspect.isawaitable(result):
            await result

    async def execute(
        self,
        goal: str,
        project_name: str = "demo_project",
        project_root: Path | str = Path("workspace/projects"),
        event_callback=None,
    ) -> Dict[str, Any]:
        """Execute the plan sequentially and return a compact summary."""
        component = self._extract_component_name(goal)
        project_root = Path(project_root)
        project_path = project_root / project_name

        await self._emit(event_callback, "status", "Creating project", {"project_name": project_name})
        project_result = await self.kicad_mcp.create_project(project_name, str(project_root))
        await self._emit(event_callback, "tool_result", "Project ready", project_result)

        await self._emit(event_callback, "status", "Researching component", {"component": component})
        await self._emit(event_callback, "tool_call", "research.advanced_search", {"component": component, "category": "datasheet"})
        research = await self.research_mcp.advanced_search(component, "datasheet")
        await self._emit(event_callback, "tool_result", "Research complete", research)

        await self._emit(event_callback, "status", "Extracting pinout", {"component": component})
        await self._emit(event_callback, "tool_call", "research.extract_pdf_pinout", {"component": component})
        pinout = await self.research_mcp.extract_pdf_pinout("mock.pdf", component)
        await self._emit(event_callback, "tool_result", "Pinout extracted", pinout)

        await self._emit(event_callback, "status", "Extracting package data", {"component": component})
        await self._emit(event_callback, "tool_call", "research.extract_package_data", {"component": component})
        package = await self.research_mcp.extract_package_data("mock.pdf")
        await self._emit(event_callback, "tool_result", "Package data ready", package)

        await self._emit(event_callback, "status", "Generating KiCad assets", {"component": component})
        await self._emit(event_callback, "tool_call", "component.generate_symbol", {"component": component})
        symbol = self.component_generator.generate_symbol(component, pinout.get("pinout", {}), package.get("package", "Unknown"))
        await self._emit(event_callback, "artifact", "Symbol generated", symbol)

        await self._emit(event_callback, "tool_call", "component.generate_footprint", {"component": component})
        footprint = self.component_generator.generate_footprint(component, package)
        await self._emit(event_callback, "artifact", "Footprint generated", footprint)

        await self._emit(event_callback, "tool_call", "component.create_evidence_record", {"component": component})
        evidence = self.component_generator.create_evidence_record(
            component,
            ["https://example.com/datasheets/" + component.lower() + ".pdf"],
            pinout.get("pinout", {}),
            package,
            confidence=0.9,
        )
        await self._emit(event_callback, "artifact", "Evidence record written", evidence)

        await self._emit(event_callback, "status", "Installing project library", {"project": project_name})
        installed = self.component_generator.install_project_library(project_path, component)
        await self._emit(event_callback, "tool_result", "Project library installed", installed)
        board_info = await self.kicad_mcp.get_board_info()
        await self._emit(event_callback, "status", "Execution complete", board_info)
        return {
            "status": "ok" if project_result.get("status") == "created" else project_result.get("status", "error"),
            "component": component,
            "research": research,
            "pinout": pinout,
            "package": package,
            "symbol": symbol,
            "footprint": footprint,
            "evidence": evidence,
            "installed": installed,
            "project": project_result,
            "board": board_info,
        }
