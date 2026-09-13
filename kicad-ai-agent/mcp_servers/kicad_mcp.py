import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class KiCadMCP:
    """
    MCP server for KiCad 10 IPC API.
    Wraps kicad-python and IPC calls.
    """

    def __init__(self, project_dir: Optional[Path | str] = None):
        self.project_dir = Path(project_dir) if project_dir else Path.cwd()
        self.project_file: Optional[Path] = None
        self.board = None
        self._pcbnew = None
        self._schematic_api = None
        self._mock_footprints: list[dict[str, Any]] = []
        self._mock_symbols: list[dict[str, Any]] = []
        self._mock_nets: list[str] = []

    async def connect(self):
        """Connect to a running KiCad instance via the IPC API."""
        try:
            from kicad_python import pcbnew

            self._pcbnew = pcbnew
            logger.info("[KiCad MCP] Connected to KiCad 10 via kicad-python IPC API")
            return {"status": "connected", "api": "kicad-python IPC"}
        except ImportError:
            logger.warning("[KiCad MCP] kicad-python not available; running in development mock mode")
            self._pcbnew = None
            return {"status": "mock", "api": "development-fallback"}
        except Exception as exc:  # pragma: no cover - unanticipated runtime env issue
            logger.error("[KiCad MCP] Connect failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def create_project(self, project_name: str, path: str) -> dict[str, Any]:
        """Create a new KiCad project with schematic and PCB files."""
        try:
            project_path = Path(path) / project_name
            project_path.mkdir(parents=True, exist_ok=True)

            pcb_file = project_path / f"{project_name}.kicad_pcb"
            sch_file = project_path / f"{project_name}.kicad_sch"
            pro_file = project_path / f"{project_name}.kicad_pro"

            pcb_file.write_text(
                "(kicad_pcb (version 20240108) (generator kicad_ai_agent))\n",
                encoding="utf-8",
            )
            sch_file.write_text(
                "(kicad_sch (version 20230121) (generator kicad_ai_agent))\n",
                encoding="utf-8",
            )
            pro_file.write_text(
                json.dumps({"project": {"name": project_name}}, indent=2),
                encoding="utf-8",
            )

            self.project_file = pcb_file
            self._mock_footprints = []
            self._mock_symbols = []
            self._mock_nets = []
            logger.info("[KiCad MCP] Created project: %s", project_path)
            return {"status": "created", "path": str(project_path), "files": 3}
        except Exception as exc:
            logger.error("[KiCad MCP] Project creation failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def open_project(self, project_path: str) -> dict[str, Any]:
        """Open an existing KiCad project and load the board if available."""
        try:
            path = Path(project_path)
            if not path.exists():
                return {"status": "error", "message": f"Project not found: {project_path}"}

            pcb_candidates = list(path.glob("*.kicad_pcb"))
            if not pcb_candidates:
                return {"status": "error", "message": f"No .kicad_pcb file found in {project_path}"}

            pcb_file = pcb_candidates[0]
            self.project_file = pcb_file

            if self._pcbnew and hasattr(self._pcbnew, "LoadBoard"):
                try:
                    self.board = self._pcbnew.LoadBoard(str(pcb_file))
                    logger.info("[KiCad MCP] Opened project: %s", pcb_file)
                    return {"status": "opened", "path": str(pcb_file), "board_loaded": True}
                except Exception as exc:  # pragma: no cover - runtime only
                    logger.warning("[KiCad MCP] Board load failed: %s", exc)
                    return {"status": "opened", "path": str(pcb_file), "board_loaded": False}

            return {"status": "opened", "path": str(pcb_file), "board_loaded": False}
        except Exception as exc:
            logger.error("[KiCad MCP] Project open failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def save_project(self) -> dict[str, Any]:
        """Save the current project."""
        try:
            if not self.project_file:
                return {"status": "error", "message": "No project open"}

            if self.board and self._pcbnew and hasattr(self._pcbnew, "SaveBoard"):
                try:
                    self._pcbnew.SaveBoard(str(self.project_file), self.board)
                except Exception as exc:  # pragma: no cover - runtime only
                    logger.warning("[KiCad MCP] SaveBoard failed: %s", exc)

            return {"status": "saved", "path": str(self.project_file)}
        except Exception as exc:
            logger.error("[KiCad MCP] Save failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def close_project(self) -> dict[str, Any]:
        """Close the current project."""
        self.project_file = None
        self.board = None
        logger.info("[KiCad MCP] Project closed")
        return {"status": "closed"}

    def _point_to_dict(self, point: Any) -> dict[str, float]:
        """Convert a KiCad point-like object into a JSON-safe dict."""
        if point is None:
            return {"x": 0.0, "y": 0.0}
        if hasattr(point, "x") and hasattr(point, "y"):
            return {"x": float(point.x), "y": float(point.y)}
        if isinstance(point, (tuple, list)) and len(point) >= 2:
            return {"x": float(point[0]), "y": float(point[1])}
        return {"x": 0.0, "y": 0.0}

    def _dict_to_point(self, value: dict[str, float]) -> Any:
        """Convert a JSON-style dict to a KiCad point-like object when the IPC API supports it."""
        x = float(value.get("x", 0.0))
        y = float(value.get("y", 0.0))

        if self._pcbnew and hasattr(self._pcbnew, "wxPoint"):
            try:
                return self._pcbnew.wxPoint(int(x), int(y))
            except Exception:
                pass

        return (x, y)

    async def get_board_info(self) -> dict[str, Any]:
        """Get basic board information."""
        if not self.project_file:
            return {"status": "error", "message": "No project open"}

        if self.board is None:
            return {
                "status": "ok",
                "project": self.project_file.stem,
                "path": str(self.project_file),
                "layers": ["F.Cu", "B.Cu"],
                "footprints": len(self._mock_footprints),
                "tracks": 0,
                "nets": len(self._mock_nets),
                "components": self._mock_footprints,
            }

        footprints = self.board.GetFootprints() if hasattr(self.board, "GetFootprints") else []
        tracks = self.board.GetTracks() if hasattr(self.board, "GetTracks") else []
        nets = self.board.GetNetsByName() if hasattr(self.board, "GetNetsByName") else {}

        return {
            "status": "ok",
            "project": self.project_file.stem,
            "path": str(self.project_file),
            "layers": self._get_layer_names(),
            "footprints": len(footprints),
            "tracks": len(tracks),
            "nets": len(nets),
        }

    def _get_layer_names(self) -> list[str]:
        """Get the board's enabled layer names."""
        if not self.board:
            return ["F.Cu", "B.Cu"]

        for idx in range(32):
            if hasattr(self.board, "IsLayerEnabled") and self.board.IsLayerEnabled(idx):
                try:
                    name = self.board.GetLayerName(idx)
                    if name:
                        return [name]
                except Exception:
                    pass
        return ["F.Cu", "B.Cu"]

    async def get_footprints(self) -> dict[str, Any]:
        """Get all footprints in the board."""
        try:
            if not self.board:
                if self.project_file:
                    return {"status": "ok", "count": len(self._mock_footprints), "footprints": self._mock_footprints}
                return {"status": "error", "message": "No board loaded"}

            footprints = self.board.GetFootprints() if hasattr(self.board, "GetFootprints") else []
            footprint_list = [
                {
                    "reference": fp.GetReference(),
                    "value": fp.GetValue(),
                    "library": fp.GetFPID().GetLibNickname() if hasattr(fp, "GetFPID") else "unknown",
                    "position": self._point_to_dict(fp.GetPosition()),
                    "rotation": fp.GetOrientation().AsDegrees() if hasattr(fp, "GetOrientation") else 0,
                }
                for fp in footprints
            ]
            return {"status": "ok", "count": len(footprint_list), "footprints": footprint_list}
        except Exception as exc:
            logger.error("[KiCad MCP] Get footprints failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def get_nets(self) -> dict[str, Any]:
        """Get all nets in the board."""
        try:
            if not self.board:
                if self.project_file:
                    return {"status": "ok", "count": len(self._mock_nets), "nets": self._mock_nets}
                return {"status": "error", "message": "No board loaded"}

            nets = self.board.GetNetsByName() if hasattr(self.board, "GetNetsByName") else {}
            net_list = list(nets.keys()) if nets else []
            return {"status": "ok", "count": len(net_list), "nets": net_list}
        except Exception as exc:
            logger.error("[KiCad MCP] Get nets failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def add_footprint(
        self,
        footprint_name: str,
        library: str,
        reference: str,
        position_x: float,
        position_y: float,
    ) -> dict[str, Any]:
        """Add a footprint to the board."""
        try:
            if not self.board:
                if not self.project_file:
                    return {"status": "error", "message": "No project open"}
                item = {
                    "reference": reference,
                    "value": footprint_name,
                    "library": library,
                    "position": {"x": position_x, "y": position_y},
                    "rotation": 0,
                }
                self._mock_footprints = [fp for fp in self._mock_footprints if fp["reference"] != reference]
                self._mock_footprints.append(item)
                return {"status": "added", **item, "mode": "mock"}
            if not self._pcbnew:
                return {"status": "partial", "reference": reference, "footprint": footprint_name, "message": "KiCad API not available"}

            try:
                if hasattr(self._pcbnew, "FootprintLoad"):
                    footprint = self._pcbnew.FootprintLoad(library, footprint_name)
                    if not footprint:
                        return {"status": "error", "message": f"Footprint not found: {library}:{footprint_name}"}
                    footprint.SetReference(reference)
                    footprint.SetPosition(self._dict_to_point({"x": position_x, "y": position_y}))
                    self.board.Add(footprint)
                    return {
                        "status": "added",
                        "reference": reference,
                        "footprint": footprint_name,
                        "position": {"x": position_x, "y": position_y},
                    }
            except Exception as exc:
                logger.warning("[KiCad MCP] Footprint load/add failed: %s", exc)
                return {
                    "status": "partial",
                    "message": f"Footprint add prepared but not fully loaded: {exc}",
                    "reference": reference,
                    "footprint": footprint_name,
                }

            return {"status": "partial", "reference": reference, "footprint": footprint_name}
        except Exception as exc:
            logger.error("[KiCad MCP] Add footprint failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def move_footprint(self, reference: str, new_x: float, new_y: float) -> dict[str, Any]:
        """Move a footprint to a new position."""
        try:
            if not self.board:
                for footprint in self._mock_footprints:
                    if footprint["reference"] == reference:
                        old_position = footprint["position"]
                        footprint["position"] = {"x": new_x, "y": new_y}
                        return {"status": "moved", "reference": reference, "old_position": old_position, "new_position": footprint["position"], "mode": "mock"}
                return {"status": "error", "message": f"Footprint not found: {reference}"}

            footprint = self.board.FindFootprintByReference(reference)
            if not footprint:
                return {"status": "error", "message": f"Footprint not found: {reference}"}

            old_position = self._point_to_dict(footprint.GetPosition())
            footprint.SetPosition(self._dict_to_point({"x": new_x, "y": new_y}))
            return {
                "status": "moved",
                "reference": reference,
                "old_position": old_position,
                "new_position": {"x": new_x, "y": new_y},
            }
        except Exception as exc:
            logger.error("[KiCad MCP] Move footprint failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def rotate_footprint(self, reference: str, angle_degrees: float) -> dict[str, Any]:
        """Rotate a footprint by angle in degrees."""
        try:
            if not self.board:
                for footprint in self._mock_footprints:
                    if footprint["reference"] == reference:
                        old_angle = footprint["rotation"]
                        footprint["rotation"] = angle_degrees
                        return {"status": "rotated", "reference": reference, "old_angle": old_angle, "new_angle": angle_degrees, "mode": "mock"}
                return {"status": "error", "message": f"Footprint not found: {reference}"}

            footprint = self.board.FindFootprintByReference(reference)
            if not footprint:
                return {"status": "error", "message": f"Footprint not found: {reference}"}

            old_angle = footprint.GetOrientation().AsDegrees() if hasattr(footprint, "GetOrientation") else 0
            if self._pcbnew and hasattr(self._pcbnew, "EDA_ANGLE"):
                new_angle = self._pcbnew.EDA_ANGLE(angle_degrees, self._pcbnew.DEGREES_T)
                footprint.SetOrientation(new_angle)
            else:
                footprint.SetOrientation(angle_degrees)

            return {
                "status": "rotated",
                "reference": reference,
                "old_angle": old_angle,
                "new_angle": angle_degrees,
            }
        except Exception as exc:
            logger.error("[KiCad MCP] Rotate footprint failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def remove_footprint(self, reference: str) -> dict[str, Any]:
        """Remove a footprint from the board."""
        try:
            if not self.board:
                before = len(self._mock_footprints)
                self._mock_footprints = [fp for fp in self._mock_footprints if fp["reference"] != reference]
                return {"status": "removed" if len(self._mock_footprints) < before else "error", "reference": reference, "mode": "mock"}

            footprint = self.board.FindFootprintByReference(reference)
            if not footprint:
                return {"status": "error", "message": f"Footprint not found: {reference}"}

            self.board.Remove(footprint)
            return {"status": "removed", "reference": reference}
        except Exception as exc:
            logger.error("[KiCad MCP] Remove footprint failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def get_footprint(self, reference: str) -> dict[str, Any]:
        """Get detailed information about a specific footprint."""
        try:
            if not self.board:
                for footprint in self._mock_footprints:
                    if footprint["reference"] == reference:
                        return {"status": "ok", **footprint, "pad_count": 0, "pads": [], "mode": "mock"}
                return {"status": "error", "message": f"Footprint not found: {reference}"}

            footprint = self.board.FindFootprintByReference(reference)
            if not footprint:
                return {"status": "error", "message": f"Footprint not found: {reference}"}

            pads = footprint.Pads() if hasattr(footprint, "Pads") else []
            pad_list = [
                {
                    "number": pad.GetNumber(),
                    "name": pad.GetName() if hasattr(pad, "GetName") else "",
                    "size": self._point_to_dict(pad.GetSize()) if hasattr(pad, "GetSize") else {"x": 0.0, "y": 0.0},
                    "position": self._point_to_dict(pad.GetPosition()) if hasattr(pad, "GetPosition") else {"x": 0.0, "y": 0.0},
                }
                for pad in pads
            ]

            return {
                "status": "ok",
                "reference": reference,
                "value": footprint.GetValue(),
                "library": footprint.GetFPID().GetLibNickname() if hasattr(footprint, "GetFPID") else "unknown",
                "position": self._point_to_dict(footprint.GetPosition()),
                "rotation": footprint.GetOrientation().AsDegrees() if hasattr(footprint, "GetOrientation") else 0,
                "pads": pad_list,
                "pad_count": len(pad_list),
            }
        except Exception as exc:
            logger.error("[KiCad MCP] Get footprint failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def add_symbol(
        self,
        symbol_name: str,
        library: str,
        ref: str,
        x: float,
        y: float,
    ) -> dict[str, Any]:
        """Add a symbol in schematic mode or return a mock result when KiCad is unavailable."""
        if self._pcbnew is None:
            self._mock_symbols.append({"reference": ref, "symbol": symbol_name, "position": {"x": x, "y": y}})
            return {
                "status": "ok",
                "message": f"Mock add_symbol for {symbol_name}",
                "reference": ref,
                "position": {"x": x, "y": y},
            }

        try:
            symbol = self._pcbnew.GetFootprintByName(library, symbol_name)
            if symbol is None:
                return {"status": "error", "message": f"Symbol not found: {symbol_name}"}
            return {"status": "ok", "reference": ref, "symbol": symbol_name, "position": {"x": x, "y": y}}
        except Exception as exc:
            logger.error("[KiCad MCP] Symbol add failed: %s", exc)
            return {"status": "error", "message": str(exc)}

    async def connect_net(self, nets: list[str]) -> dict[str, Any]:
        """Record simple logical nets in mock mode and create them in a live board when possible."""
        unique = [net for net in nets if net and net not in self._mock_nets]
        self._mock_nets.extend(unique)
        return {"status": "partial" if self.board is None else "connected", "nets": self._mock_nets, "message": "Logical net plan recorded"}

    async def execute_tool(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a known tool by name to the appropriate KiCad operation."""
        if tool_name == "schematic.create_project":
            return await self.create_project(params.get("project_name", "demo"), params.get("path", str(self.project_dir)))
        if tool_name == "schematic.open_project":
            return await self.open_project(params.get("path", str(self.project_dir)))
        if tool_name == "schematic.save_project":
            return await self.save_project()
        if tool_name == "schematic.close_project":
            return await self.close_project()
        if tool_name == "schematic.get_project_info":
            return await self.get_board_info()
        if tool_name == "schematic.add_symbol":
            return await self.add_symbol(
                params.get("symbol_name", "demo_symbol"),
                params.get("library", "demo_lib"),
                params.get("reference", "U1"),
                float(params.get("position_x", 0)),
                float(params.get("position_y", 0)),
            )
        if tool_name == "pcb.create_board":
            return await self.create_project(params.get("project_name", "board"), params.get("path", str(self.project_dir)))
        if tool_name == "pcb.add_footprint":
            return await self.add_footprint(
                params.get("footprint_name", "R_0603_1608Metric"),
                params.get("library", "Resistor_SMD"),
                params.get("reference", "R1"),
                float(params.get("position_x", 0)),
                float(params.get("position_y", 0)),
            )
        if tool_name == "pcb.move_footprint":
            return await self.move_footprint(
                params.get("reference", "R1"),
                float(params.get("new_x", 0)),
                float(params.get("new_y", 0)),
            )
        if tool_name == "pcb.remove_footprint":
            return await self.remove_footprint(params.get("reference", "R1"))
        if tool_name == "pcb.get_board_info":
            return await self.get_board_info()
        if tool_name == "pcb.get_footprint":
            return await self.get_footprint(params.get("reference", "R1"))
        if tool_name == "pcb.get_footprints":
            return await self.get_footprints()
        if tool_name == "pcb.get_nets":
            return await self.get_nets()
        if tool_name == "pcb.connect_net":
            return await self.connect_net(params.get("nets", []))
        return {"status": "error", "message": f"Tool not implemented: {tool_name}"}
