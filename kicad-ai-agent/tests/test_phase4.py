import asyncio

from mcp_servers.research_mcp import ResearchMCP
from tools.component.component_generator import ComponentGenerator


async def test_phase4():
    """Test the research → generation pipeline for a component."""
    print("\n=== PHASE 4: Omniroute Research & Component Generation ===\n")

    async with ResearchMCP() as research:
        gen = ComponentGenerator()

        print("Test 1: Searching for RK3566 datasheet...")
        search_result = await research.advanced_search("RK3566", "datasheet")
        print(f"  Found {search_result.get('count', 0)} results")
        print(f"  Status: {search_result['status']}")

        print("\nTest 2: Extracting pinout from mock datasheet...")
        pinout_result = await research.extract_pdf_pinout("mock.pdf", "RK3566")
        print(f"  Pinout: {pinout_result.get('total_pins', 0)} pins")
        print(f"  Status: {pinout_result['status']}")

        print("\nTest 3: Extracting package data...")
        package_result = await research.extract_package_data("mock.pdf")
        print(f"  Package: {package_result.get('package', 'Unknown')}")
        print(f"  Status: {package_result['status']}")

        if pinout_result.get('status') == 'ok':
            print("\nTest 4: Generating symbol...")
            symbol_result = gen.generate_symbol(
                "RK3566",
                pinout_result.get('pinout', {}),
                package_result.get('package', 'Unknown'),
            )
            print(f"  Symbol file: {symbol_result.get('symbol_file', 'N/A')}")
            print(f"  Status: {symbol_result['status']}")

            print("\nTest 5: Generating footprint...")
            footprint_result = gen.generate_footprint("RK3566", package_result)
            print(f"  Footprint file: {footprint_result.get('footprint_file', 'N/A')}")
            print(f"  Status: {footprint_result['status']}")

            print("\nTest 6: Creating evidence record...")
            evidence_result = gen.create_evidence_record(
                "RK3566",
                ["https://example.com/RK3566_datasheet.pdf"],
                pinout_result.get('pinout', {}),
                package_result,
                confidence=0.92,
            )
            print(f"  Evidence file: {evidence_result.get('evidence_file', 'N/A')}")
            print(f"  Confidence: {evidence_result.get('confidence', 0)}")
            print(f"  Status: {evidence_result['status']}")

    print("\n=== Phase 4 tests complete ===\n")


if __name__ == "__main__":
    asyncio.run(test_phase4())
