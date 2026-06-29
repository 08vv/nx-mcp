"""
create_mechanical_bracket.py
============================
NX Journal that creates a parametric mechanical bracket with specified named expressions:
BASE_LENGTH=44mm, BASE_WIDTH=34mm, BASE_HEIGHT=48mm, BOSS_DIAMETER=24mm, BOSS_LENGTH=70mm, 
CHANNEL_WIDTH=28mm, CHANNEL_DEPTH=40mm, FLOOR_THICKNESS=8mm, BORE_DIAMETER=14mm.
"""

import sys
import os
import math
from pathlib import Path
import subprocess

import NXOpen
import NXOpen.UF

# ---------------------------------------------------------------------------
# Default Parametric Constants (mm)
# ---------------------------------------------------------------------------
BASE_LENGTH      = 44.0
BASE_WIDTH       = 34.0
BASE_HEIGHT      = 48.0
BOSS_DIAMETER    = 24.0
BOSS_LENGTH      = 70.0
CHANNEL_WIDTH    = 28.0
CHANNEL_DEPTH    = 40.0
FLOOR_THICKNESS  = 8.0
BORE_DIAMETER    = 14.0

# ---------------------------------------------------------------------------
# Output path helper
# ---------------------------------------------------------------------------
def _output_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "mechanical_bracket.prt"

# ---------------------------------------------------------------------------
# Helper: boolean subtract
# ---------------------------------------------------------------------------
def _perform_subtract(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body)
                    break
                except Exception:
                    pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, tool_body)
                    break
                except Exception:
                    pass
        builder.CommitFeature()
    finally:
        builder.Destroy()

# ---------------------------------------------------------------------------
# Helper: boolean unite
# ---------------------------------------------------------------------------
def _perform_unite(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body)
                    break
                except Exception:
                    pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, tool_body)
                    break
                except Exception:
                    pass
        builder.CommitFeature()
    finally:
        builder.Destroy()

# ---------------------------------------------------------------------------
# Helper: create a block (cuboid)
# ---------------------------------------------------------------------------
def _create_block(work_part, corner_origin, length_str: str, width_str: str, height_str: str):
    builder = work_part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(corner_origin, length_str, width_str, height_str)
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]

# ---------------------------------------------------------------------------
# Helper: create a cylinder
# ---------------------------------------------------------------------------
def _create_cylinder(work_part, origin, direction_vec, diameter_expr: str, height_expr: str):
    builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        nx_dir = work_part.Directions.CreateDirection(
            origin, direction_vec, NXOpen.SmartObject.UpdateOption.WithinModeling
        )
        builder.Diameter.RightHandSide = diameter_expr
        builder.Height.RightHandSide   = height_expr
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = nx_dir
        feat = builder.Commit()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        try:
            output_path.unlink()
            print("[OK] Removed existing part file: {}".format(output_path))
        except Exception as exc:
            print("[WARN] Could not remove existing file: {}".format(exc))

    session   = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    print("=" * 60)
    print("  CREATING PARAMETRIC MECHANICAL BRACKET")
    print("  Output: {}".format(output_path))
    print("=" * 60)

    # 1. Register named expressions
    named_expressions = [
        ("BASE_LENGTH",     BASE_LENGTH),
        ("BASE_WIDTH",      BASE_WIDTH),
        ("BASE_HEIGHT",     BASE_HEIGHT),
        ("BOSS_DIAMETER",   BOSS_DIAMETER),
        ("BOSS_LENGTH",     BOSS_LENGTH),
        ("CHANNEL_WIDTH",   CHANNEL_WIDTH),
        ("CHANNEL_DEPTH",   CHANNEL_DEPTH),
        ("FLOOR_THICKNESS", FLOOR_THICKNESS),
        ("BORE_DIAMETER",   BORE_DIAMETER),
    ]
    for name, value in named_expressions:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
    print("[OK] Expressions created.")

    # 2. Base Block
    # Origin at (0, 0, 0)
    origin_base = NXOpen.Point3d(0.0, 0.0, 0.0)
    print("[...] Creating base plate cuboid...")
    base_body = _create_block(
        work_part, origin_base,
        "BASE_LENGTH", "BASE_WIDTH", "BASE_HEIGHT"
    )
    print("[OK] Base plate created.")

    # 3. Boss Cylinder
    # Center X = BASE_LENGTH / 2, Y starts at (BASE_WIDTH - BOSS_LENGTH) / 2, Z = BASE_HEIGHT
    # Vector along Y axis: (0, 1, 0)
    print("[...] Creating boss cylinder...")
    boss_x = BASE_LENGTH / 2.0
    boss_y = (BASE_WIDTH - BOSS_LENGTH) / 2.0
    boss_z = BASE_HEIGHT
    origin_boss = NXOpen.Point3d(boss_x, boss_y, boss_z)
    direction_y = NXOpen.Vector3d(0.0, 1.0, 0.0)
    boss_body = _create_cylinder(
        work_part, origin_boss, direction_y,
        "BOSS_DIAMETER", "BOSS_LENGTH"
    )
    print("[OK] Boss cylinder created.")

    # Unite the boss with the base body
    print("[...] Uniting base plate and boss...")
    _perform_unite(work_part, base_body, boss_body)
    print("[OK] United successfully.")

    # 4. Cut Channel
    # Starts at X=0, Y=(BASE_WIDTH - CHANNEL_WIDTH)/2, Z=BASE_HEIGHT - CHANNEL_DEPTH
    # X-length = BASE_LENGTH, Y-width = CHANNEL_WIDTH, Z-height = CHANNEL_DEPTH + BOSS_DIAMETER
    print("[...] Creating channel subtract block...")
    channel_x = 0.0
    channel_y = (BASE_WIDTH - CHANNEL_WIDTH) / 2.0
    channel_z = BASE_HEIGHT - CHANNEL_DEPTH
    origin_channel = NXOpen.Point3d(channel_x, channel_y, channel_z)
    
    # We want Z height to be large enough to clear the top of the boss/ears
    channel_height_expr = "CHANNEL_DEPTH + BOSS_DIAMETER"
    channel_body = _create_block(
        work_part, origin_channel,
        "BASE_LENGTH", "CHANNEL_WIDTH", channel_height_expr
    )
    
    print("[...] Subtracting channel...")
    _perform_subtract(work_part, base_body, channel_body)
    print("[OK] Channel subtracted.")

    # 5. Cut Bore Hole
    # Coaxial along the Y-axis. Starts slightly outside the boss (Y = boss_y - 5.0)
    # Extends beyond the entire boss length (height = BOSS_LENGTH + 10.0)
    print("[...] Creating coaxial bore cylinder...")
    origin_bore = NXOpen.Point3d(boss_x, boss_y - 5.0, boss_z)
    bore_height_expr = "BOSS_LENGTH + 10.0"
    bore_body = _create_cylinder(
        work_part, origin_bore, direction_y,
        "BORE_DIAMETER", bore_height_expr
    )
    
    print("[...] Subtracting bore...")
    _perform_subtract(work_part, base_body, bore_body)
    print("[OK] Bore subtracted.")

    # 6. Fit View and Save
    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print("=" * 60)
    print("[OK] Part saved -> {}".format(output_path))
    print("=" * 60)

    # 7. Update latest_nx_result.txt and open_current_nx_result.cmd
    try:
        abs_path_str = str(output_path.resolve())

        # Write to local latest_nx_result.txt
        latest_file = output_path.parent / "latest_nx_result.txt"
        latest_file.write_text(abs_path_str, encoding="utf-8")

        # Also write to project root
        project_root = Path(__file__).parent.parent.parent.parent.resolve()
        root_latest = project_root / "latest_nx_result.txt"
        root_latest.write_text(abs_path_str, encoding="utf-8")

        # Update open_current_nx_result.cmd
        cmd_path = project_root / "open_current_nx_result.cmd"
        cmd_content = '@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{}"\n'.format(abs_path_str)
        cmd_path.write_text(cmd_content, encoding="utf-8")

        print("[OK] Result files updated.")
    except Exception as exc:
        print("[WARN] Could not update result files: {}".format(exc))

    # 8. Auto-open in Siemens NX GUI
    try:
        base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        router_candidates = [
            base_path / "NXBIN" / "ugs_router.exe",
            base_path / "UGII"  / "ugs_router.exe",
        ]
        ugs_router = next((c for c in router_candidates if c.exists()), None)
        if ugs_router:
            subprocess.Popen([str(ugs_router), "-ug", "-use_file_dir", str(output_path.resolve())])
            print("[OK] NX GUI launched -> opening {}".format(output_path.name))
        else:
            print("[WARN] ugs_router.exe not found.")
    except Exception as exc:
        print("[WARN] Could not auto-open in NX GUI: {}".format(exc))

    print("[DONE] Mechanical bracket complete.")

if __name__ == "__main__":
    main()
