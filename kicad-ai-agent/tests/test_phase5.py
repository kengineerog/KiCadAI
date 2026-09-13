import asyncio
from pathlib import Path

from agent.planner import AgentPlanner
from agent.tool_registry import ToolRegistry
from mcp_servers.kicad_mcp import KiCadMCP
from mcp_servers.research_mcp import ResearchMCP
from tools.component.component_generator import ComponentGenerator


async def main():
    planner = AgentPlanner(
        ToolRegistry(Path("tools")),
        ResearchMCP(),
        KiCadMCP(Path("workspace/projects")),
        ComponentGenerator(Path("workspace/libraries/custom")),
    )
    goal = "Research and generate an RK3566 SoC symbol, footprint, and evidence record for KiCad"
    plan = planner.plan(goal)
    result = await planner.execute(goal, project_name="phase5_demo", project_root=Path("workspace/projects"))
    print(plan["component"])
    print(result["status"])
    print(result["symbol"]["status"])
    print(result["footprint"]["status"])
    print(result["evidence"]["status"])


if __name__ == "__main__":
    asyncio.run(main())
