import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class ComponentGenerator:
    """Generate KiCad symbol and footprint assets from component research."""

    def __init__(self, library_dir: Path | str = Path("workspace/libraries/custom")):
        self.library_dir = Path(library_dir)
        self.library_dir.mkdir(parents=True, exist_ok=True)

    def generate_symbol(
        self,
        component_name: str,
        pinout: Dict[str, Any],
        package: str = "Unknown",
    ) -> Dict[str, Any]:
        """Create a KiCad symbol (.kicad_sym) from pinout JSON."""
        symbol_content = self._create_symbol_content(component_name, pinout, package)
        symbol_file = self.library_dir / f"{component_name}.kicad_sym"
        symbol_file.write_text(symbol_content, encoding="utf-8")

        return {
            "status": "ok",
            "component": component_name,
            "symbol_file": str(symbol_file),
            "pin_count": len(pinout),
            "generated_at": datetime.now().isoformat(),
        }

    def _create_symbol_content(self, component_name: str, pinout: Dict[str, Any], package: str) -> str:
        """Build a compact KiCad symbol S-expression."""
        pins_content = ""
        for idx, (pin_num, pin_data) in enumerate(pinout.items()):
            pin_name = str(pin_data.get("name", f"PIN_{pin_num}"))
            pin_type = str(pin_data.get("type", "Unspecified"))
            electrical_type = self._map_pin_type(pin_type)
            y = -idx * 2.54
            pins_content += (
                f'    (pin "{electrical_type}" line (at 0 {y} 0) (length 3.81) '
                f'(name "{pin_name}" (effects (font (size 1.27 1.27) (thickness 0.15))))\n'
                f'      (number "{pin_num}" (effects (font (size 1.27 1.27) (thickness 0.15)))))\n'
            )

        return f'''(symbol "{component_name}"
  (property "Reference" "U" (at 0 0 0))
  (property "Value" "{component_name}" (at 0 -2.54 0))
  (property "Footprint" "{component_name}" (at 0 0 0))
  (property "Datasheet" "" (at 0 0 0))
  (symbol "{component_name}_0_1"
    (rectangle (start 0 0) (end 10 -30) (stroke (width 0.254)) (fill (type background))))
  (symbol "{component_name}_1_1"
{pins_content}  )
)
'''

    @staticmethod
    def _map_pin_type(pin_type: str) -> str:
        type_map = {
            "Power": "power_in",
            "Ground": "power_in",
            "GPIO": "bidirectional",
            "Input": "input",
            "Output": "output",
            "Analog": "analog",
            "Clock": "input",
            "Bidirectional": "bidirectional",
        }
        return type_map.get(pin_type, "unspecified")

    def generate_footprint(self, component_name: str, package_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a simple KiCad footprint file from package metadata."""
        footprint_content = self._create_footprint_content(component_name, package_data)
        footprint_file = self.library_dir / f"{component_name}.kicad_mod"
        footprint_file.write_text(footprint_content, encoding="utf-8")

        return {
            "status": "ok",
            "component": component_name,
            "footprint_file": str(footprint_file),
            "package": package_data.get("package", "Unknown"),
            "generated_at": datetime.now().isoformat(),
        }

    def _create_footprint_content(self, component_name: str, package_data: Dict[str, Any]) -> str:
        """Build a KiCad footprint S-expression."""
        package = package_data.get("package", "Unknown")
        pitch = package_data.get("pitch_mm", 0.8)
        rows = package_data.get("array_rows", 19)
        cols = package_data.get("array_cols", 22)

        pads_content = ""
        pad_size = float(pitch) * 0.9
        for row in range(rows):
            for col in range(cols):
                x = col * pitch
                y = row * pitch
                pad_num = f"{chr(65 + row)}{col + 1}"
                pads_content += (
                    f'  (pad "{pad_num}" smd circle (at {x} {y} 0) (size {pad_size} {pad_size}) '
                    f'(layers "F.Cu" "F.Paste" "F.Mask"))\n'
                )

        return f'''(footprint "{component_name}"
  (layer "F.Cu")
  (descr "{package} BGA {rows}x{cols}")
  (attr smd)
{pads_content}  (model "${{KICAD_MODELS}}/{component_name}.step"
    (at (xyz 0 0 0))
    (scale (xyz 1 1 1)))
)
'''

    def create_evidence_record(
        self,
        component_name: str,
        sources: List[str],
        pinout: Dict[str, Any],
        package_data: Dict[str, Any],
        confidence: float = 0.9,
    ) -> Dict[str, Any]:
        """Create an evidence.json record for source tracking."""
        evidence = {
            "component": component_name,
            "generated_at": datetime.now().isoformat(),
            "generation_confidence": confidence,
            "sources": sources,
            "pinout_source": "datasheet extraction",
            "pinout_pins": len(pinout),
            "package_data_source": "datasheet extraction",
            "package": package_data.get("package", "Unknown"),
            "symbol_file": f"{component_name}.kicad_sym",
            "footprint_file": f"{component_name}.kicad_mod",
            "validation_status": "pending",
        }

        evidence_file = self.library_dir / f"{component_name}_evidence.json"
        evidence_file.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

        return {
            "status": "ok",
            "component": component_name,
            "evidence_file": str(evidence_file),
            "confidence": confidence,
        }

    def install_project_library(self, project_path: str | Path, component_name: str) -> Dict[str, Any]:
        """Copy generated component files into a project-specific library folder."""
        project_root = Path(project_path)
        target_dir = project_root / "workspace" / "libraries" / "custom"
        target_dir.mkdir(parents=True, exist_ok=True)

        for suffix in (".kicad_sym", ".kicad_mod", "_evidence.json"):
            source = self.library_dir / f"{component_name}{suffix}"
            if source.exists():
                dest = target_dir / source.name
                dest.write_bytes(source.read_bytes())

        return {
            "status": "ok",
            "project_path": str(project_root),
            "library_dir": str(target_dir),
            "component": component_name,
        }
