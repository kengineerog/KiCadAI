import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from agent.model import ModelClient, ModelConfig
from agent.planner import AgentPlanner
from agent.tool_registry import ToolRegistry
from mcp_servers.kicad_mcp import KiCadMCP
from mcp_servers.research_mcp import ResearchMCP
from tools.component.component_generator import ComponentGenerator

load_dotenv()


async def main():
    """Initialize the agent, run the Phase 5 planning loop, and print the outcome."""
    config = ModelConfig(
        base_url=os.getenv("MODEL_BASE_URL", "http://localhost:8000/v1"),
        api_key=os.getenv("MODEL_API_KEY", "test-key"),
        model=os.getenv("MODEL_NAME", "test-model"),
    )

    tool_registry = ToolRegistry(Path("tools"))
    kicad_mcp = KiCadMCP(Path("workspace/projects"))
    research_mcp = ResearchMCP(os.getenv("OMNIROUTE_KEY"))
    component_generator = ComponentGenerator(Path("workspace/libraries/custom"))
    model_client = ModelClient(config)
    planner = AgentPlanner(tool_registry, research_mcp, kicad_mcp, component_generator)

    await kicad_mcp.connect()

    print("[Agent] Starting KiCad AI Agent")
    print(f"[Agent] Model: {config.model}")
    print(f"[Agent] Tools available: {tool_registry.count_tools()}")

    project_result = await kicad_mcp.create_project("demo_project", "workspace/projects")
    print(f"[Agent] Project creation: {project_result}")

    goal = "Research and generate an RK3566 SoC symbol, footprint, and evidence record for KiCad"
    plan = planner.plan(goal)
    print(f"[Agent] Plan: {plan['steps']}")

    execution = await planner.execute(goal, project_name="demo_project", project_root=Path("workspace/projects"))
    print(f"[Agent] Execution: {execution}")

    await model_client.close()


if __name__ == "__main__":
    asyncio.run(main())
