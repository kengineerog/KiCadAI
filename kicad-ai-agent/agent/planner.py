import inspect
import re
from pathlib import Path
from typing import Any, Dict


class AgentPlanner:
    """Small, deterministic execution loop for practical component workflows."""

    COMMON_COMPONENTS = (
        "ATmega328P",
        "RK3566",
        "LED",
        "resistor",
        "capacitor",
        "connector",
    )

    def __init__(self, tool_registry, research_mcp, kicad_mcp, component_generator):
        self.tool_registry = tool_registry
        self.research_mcp = research_mcp
        self.kicad_mcp = kicad_mcp
        self.component_generator = component_generator

    def _extract_components(self, goal: str) -> list[str]:
        found: list[str] = []
        lower = goal.lower()
        for component in self.COMMON_COMPONENTS:
            if component.lower() in lower and component.lower() not in {item.lower() for item in found}:
                found.append(component)
        for match in re.findall(r"\b[A-Z][A-Za-z0-9]*\d+[A-Za-z0-9]*\b", goal):
            if match.lower() not in {item.lower() for item in found}:
                found.append(match)
        return found or [self._extract_component_name(goal)]

    def _extract_component_name(self, goal: str) -> str:
        match = re.search(r"\b([A-Z][A-Za-z0-9]*\d+[A-Za-z0-9]*)\b", goal)
        return match.group(1) if match else "Component"

    def plan(self, goal: str) -> Dict[str, Any]:
        components = self._extract_components(goal)
        tool_matches = self.tool_registry.search_tools(goal)
        steps = [{"id": "create_project", "tool": "schematic.create_project", "goal": "Create or open the target project"}]
        for component in components:
            steps.extend(
                [
                    {"id": f"research_{component}", "tool": "research.advanced_search", "goal": f"Find {component} documentation"},
                    {"id": f"generate_{component}", "tool": "component.generate_symbol", "goal": f"Generate {component} libraries"},
                    {"id": f"place_{component}", "tool": "pcb.add_footprint", "goal": f"Place {component} on the board"},
                ]
            )
        if len(components) > 1 or re.search(r"\b(connect|power|ground|net|flash)\b", goal, re.I):
            steps.append({"id": "connect", "tool": "pcb.connect_net", "goal": "Connect requested power, ground, and signal nets"})
        steps.append({"id": "report", "tool": "pcb.get_board_info", "goal": "Report the resulting board state"})
        return {
            "component": components[0],
            "components": components,
            "goal": goal,
            "tool_candidates": [item.get("name") for item in tool_matches[:5]],
            "steps": steps,
        }

    async def _emit(self, callback, event_type: str, message: str, data: Dict[str, Any] | None = None):
        if callback is None:
            return
        result = callback({"type": event_type, "message": message, "data": data or {}})
        if inspect.isawaitable(result):
            await result

    async def execute(
        self,
        goal: str,
        project_name: str = "demo_project",
        project_root: Path | str = Path("workspace/projects"),
        event_callback=None,
        cancel_check=None,
    ) -> Dict[str, Any]:
        project_root = Path(project_root)
        project_path = project_root / project_name
        components = self._extract_components(goal)
        results: list[dict[str, Any]] = []

        async def checkpoint():
            if cancel_check and cancel_check():
                raise asyncio.CancelledError("Run stopped by user")

        import asyncio
        await self._emit(event_callback, "status", "Creating project", {"project_name": project_name})
        project_result = await self.kicad_mcp.create_project(project_name, str(project_root))
        await self._emit(event_callback, "tool_result", "Project ready", project_result)

        for index, component in enumerate(components):
            await checkpoint()
            await self._emit(event_callback, "status", f"Researching {component}", {"component": component, "step": index + 1, "total": len(components)})
            await self._emit(event_callback, "tool_call", "research.advanced_search", {"component": component, "category": "datasheet"})
            research = await self.research_mcp.advanced_search(component, "datasheet")
            await self._emit(event_callback, "tool_result", "Research complete", research)

            source_url = (research.get("results") or [{}])[0].get("url", "")
            await self._emit(event_callback, "tool_call", "research.download_pdf", {"component": component, "url": source_url})
            downloaded = await self.research_mcp.download_pdf(source_url or f"https://example.com/{component}.pdf")
            await self._emit(event_callback, "tool_result", "Datasheet cached", downloaded)

            await checkpoint()
            pdf_path = f"{downloaded.get('local_path', '')}_{component}"
            await self._emit(event_callback, "tool_call", "research.extract_pdf_pinout", {"component": component})
            pinout = await self.research_mcp.extract_pdf_pinout(pdf_path, component)
            await self._emit(event_callback, "tool_result", "Pinout extracted", pinout)
            await self._emit(event_callback, "tool_call", "research.extract_package_data", {"component": component})
            package = await self.research_mcp.extract_package_data(pdf_path)
            await self._emit(event_callback, "tool_result", "Package data ready", package)

            await self._emit(event_callback, "status", f"Generating {component} libraries", {"component": component})
            symbol = self.component_generator.generate_symbol(component, pinout.get("pinout", {}), package.get("package", "Unknown"))
            await self._emit(event_callback, "artifact", "Symbol generated", symbol)
            footprint = self.component_generator.generate_footprint(component, package)
            await self._emit(event_callback, "artifact", "Footprint generated", footprint)
            evidence = self.component_generator.create_evidence_record(
                component,
                [source_url] if source_url else [],
                pinout.get("pinout", {}),
                package,
                confidence=0.9 if pinout.get("status") == "ok" else 0.65,
            )
            await self._emit(event_callback, "artifact", "Evidence record written", evidence)
            installed = self.component_generator.install_project_library(project_path, component)
            await self._emit(event_callback, "tool_result", "Project library installed", installed)

            if re.search(r"\b(place|project|board|flash|connect|pcb)\b", goal, re.I):
                reference = {"ATmega328P": "U1", "LED": "D1", "resistor": "R1", "capacitor": "C1"}.get(component, f"U{index + 1}")
                await self._emit(event_callback, "tool_call", "pcb.add_footprint", {"component": component, "reference": reference})
                placed = await self.kicad_mcp.add_footprint(component, "custom", reference, 40 + index * 12, 50)
                await self._emit(event_callback, "tool_result", f"{component} placed", placed)
                await self._emit(event_callback, "tool_call", "schematic.add_symbol", {"component": component, "reference": reference})
                symbol_result = await self.kicad_mcp.add_symbol(component, "custom", reference, 100 + index * 25, 100)
                await self._emit(event_callback, "tool_result", f"{component} symbol added", symbol_result)
            results.append({"component": component, "research": research, "pinout": pinout, "package": package, "symbol": symbol, "footprint": footprint, "evidence": evidence, "installed": installed})

        if len(components) > 1 or re.search(r"\b(connect|power|ground|net|flash)\b", goal, re.I):
            await self._emit(event_callback, "status", "Connecting requested nets", {"nets": ["VCC", "GND", "LED_K"]})
            await self._emit(event_callback, "tool_call", "pcb.connect_net", {"nets": ["VCC", "GND", "LED_K"]})
            connection = await self.kicad_mcp.connect_net(["VCC", "GND", "LED_K"])
            await self._emit(event_callback, "tool_result", "Nets connected", connection)

        board_info = await self.kicad_mcp.get_board_info()
        await self._emit(event_callback, "status", "Execution complete", board_info)
        summary = {"status": "ok" if project_result.get("status") in {"created", "opened"} else project_result.get("status", "error"), "components": results, "project": project_result, "board": board_info}
        if results:
            summary.update({key: results[0][key] for key in ("component", "symbol", "footprint", "evidence", "research", "pinout", "package", "installed")})
        return summary
