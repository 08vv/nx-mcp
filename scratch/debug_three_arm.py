import sys
import os
import math
from pathlib import Path

sys.path.insert(0, r"c:\Users\HP\nx-mcp\src")

import NXOpen

# Copy the exact coordinates logic
ARM_LENGTH    = 110.0
ARM_WIDTH     =  22.0
ARM_THICKNESS =   8.0
HOLE_DIAMETER =  10.0
JUNCTION_SIZE =  28.0
RISE_ANGLE    =  45.0

def _create_block(work_part, corner, lx, ly, lz):
    builder = work_part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.SetOriginAndLengths(corner, str(lx), str(ly), str(lz))
        builder.SetBooleanOperationAndTarget(NXOpen.Features.Feature.BooleanType.Create, NXOpen.Body.Null)
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]

def _create_cylinder(work_part, origin, dir_vec, diam_expr, height_expr):
    builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        direction = work_part.Directions.CreateDirection(
            origin, dir_vec, NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Diameter.RightHandSide = diam_expr
        builder.Height.RightHandSide   = height_expr
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = direction
        feat = builder.Commit()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]

def _extrude_rect(work_part, corners, extrude_origin, extrude_dir, height_expr):
    lines = [
        work_part.Curves.CreateLine(corners[0], corners[1]),
        work_part.Curves.CreateLine(corners[1], corners[2]),
        work_part.Curves.CreateLine(corners[2], corners[3]),
        work_part.Curves.CreateLine(corners[3], corners[0]),
    ]
    section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
    rules = [work_part.ScRuleFactory.CreateRuleCurveDumb([ln]) for ln in lines]
    section.AddToSection(
        rules, lines[0],
        NXOpen.NXObject.Null, NXOpen.NXObject.Null,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create, False,
    )
    builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = section
        nx_dir = work_part.Directions.CreateDirection(
            extrude_origin, extrude_dir,
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Direction = nx_dir
        builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        builder.Limits.EndExtend.Value.RightHandSide   = height_expr
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]

def _perform_unite(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try: setattr(builder, attr, target_body); break
                except Exception: pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try: setattr(builder, attr, tool_body); break
                except Exception: pass
        builder.CommitFeature()
    finally:
        builder.Destroy()

def _perform_subtract(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try: setattr(builder, attr, target_body); break
                except Exception: pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try: setattr(builder, attr, tool_body); break
                except Exception: pass
        builder.CommitFeature()
    finally:
        builder.Destroy()

def main():
    output_path = Path(r"c:\Users\HP\nx-mcp\scratch\debug_three_arm.prt")
    if output_path.exists():
        output_path.unlink()
        
    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    # 1. Expressions
    for name, val in [("ARM_LENGTH",    ARM_LENGTH),
                      ("ARM_WIDTH",     ARM_WIDTH),
                      ("ARM_THICKNESS", ARM_THICKNESS),
                      ("HOLE_DIAMETER", HOLE_DIAMETER),
                      ("JUNCTION_SIZE", JUNCTION_SIZE),
                      ("RISE_ANGLE",    RISE_ANGLE)]:
        work_part.Expressions.CreateExpression("Number", f"{name} = {val}")

    # 2. Block
    half_js = JUNCTION_SIZE / 2.0
    block_corner = NXOpen.Point3d(-half_js, -half_js, 0.0)
    main_body = _create_block(work_part, block_corner, "JUNCTION_SIZE", "JUNCTION_SIZE", "JUNCTION_SIZE")
    print("Block created.")

    # 3. Arm 3 geometry
    rise_rad = math.radians(RISE_ANGLE)
    sin_r = math.sin(rise_rad)
    cos_r = math.cos(rise_rad)
    c45 = math.cos(math.radians(45.0))
    s45 = math.sin(math.radians(45.0))
    hw = ARM_WIDTH / 2.0

    u_len_x = sin_r * c45
    u_len_y = sin_r * s45
    u_len_z = cos_r

    u_wid_x = -s45
    u_wid_y =  c45
    u_wid_z =  0.0

    u_thk_x = -cos_r * c45
    u_thk_y = -cos_r * s45
    u_thk_z =  sin_r

    px, py, pz = 0.0, 0.0, JUNCTION_SIZE

    # Tip centre
    tip = NXOpen.Point3d(px + ARM_LENGTH * u_len_x, py + ARM_LENGTH * u_len_y, pz + ARM_LENGTH * u_len_z)

    # We extend the arm 15mm down into the block for solid overlap
    overlap = 15.0

    # Corners:
    c1 = NXOpen.Point3d(tip.X - (ARM_LENGTH + overlap) * u_len_x + hw * u_wid_x,
                        tip.Y - (ARM_LENGTH + overlap) * u_len_y + hw * u_wid_y,
                        tip.Z - (ARM_LENGTH + overlap) * u_len_z + hw * u_wid_z)
    c2 = NXOpen.Point3d(tip.X - (ARM_LENGTH + overlap) * u_len_x - hw * u_wid_x,
                        tip.Y - (ARM_LENGTH + overlap) * u_len_y - hw * u_wid_y,
                        tip.Z - (ARM_LENGTH + overlap) * u_len_z - hw * u_wid_z)
    c3 = NXOpen.Point3d(tip.X - hw * u_wid_x,
                        tip.Y - hw * u_wid_y,
                        tip.Z - hw * u_wid_z)
    c4 = NXOpen.Point3d(tip.X + hw * u_wid_x,
                        tip.Y + hw * u_wid_y,
                        tip.Z + hw * u_wid_z)

    u_thk_vec = NXOpen.Vector3d(u_thk_x, u_thk_y, u_thk_z)
    ext_origin = NXOpen.Point3d(px, py, pz)

    arm_body = _extrude_rect(work_part, [c1, c2, c3, c4], ext_origin, u_thk_vec, "ARM_THICKNESS")
    print("Arm bar extruded.")

    cap_body = _create_cylinder(work_part, tip, u_thk_vec, "ARM_WIDTH", "ARM_THICKNESS")
    print("Cap cylinder created.")

    _perform_unite(work_part, arm_body, cap_body)
    print("Arm + Cap united.")
    
    _perform_unite(work_part, main_body, arm_body)
    print("Arm united to Main block.")

    session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)
    print("Forced DoUpdate")

    # Hole cylinder
    hole_origin = NXOpen.Point3d(tip.X - 1.0 * u_thk_x, tip.Y - 1.0 * u_thk_y, tip.Z - 1.0 * u_thk_z)
    hole_body = _create_cylinder(work_part, hole_origin, u_thk_vec, "HOLE_DIAMETER", "ARM_THICKNESS + 2.0")
    print("Hole cylinder created.")

    try:
        _perform_subtract(work_part, main_body, hole_body)
        print("Subtract success!")
    except Exception as e:
        print(f"Subtract failed: {e}")

if __name__ == "__main__":
    main()
