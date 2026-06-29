"""
create_clevis_mount_bracket_part.py
====================================
NX Journal that creates a parametric clevis mount bracket.
All dimensions and coordinates are stored as named NX Expressions.
Uses only Block, Cylinder, Unite, and Subtract features.
"""

import sys
import os
import math
from pathlib import Path

import NXOpen
import NXOpen.UF


def _output_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path("C:/Users/HP/nx-mcp/clevis_mount_bracket.prt").resolve()


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


def _create_block_assoc(work_part, x_expr, y_expr, z_expr, lx_expr, ly_expr, lz_expr, x_vec=None, y_vec=None):
    expr_x = work_part.Expressions.FindObject(x_expr)
    expr_y = work_part.Expressions.FindObject(y_expr)
    expr_z = work_part.Expressions.FindObject(z_expr)
    
    x_scalar = work_part.Scalars.CreateScalarExpression(
        expr_x, NXOpen.Scalar.DimensionalityType.NotSet,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    y_scalar = work_part.Scalars.CreateScalarExpression(
        expr_y, NXOpen.Scalar.DimensionalityType.NotSet,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    z_scalar = work_part.Scalars.CreateScalarExpression(
        expr_z, NXOpen.Scalar.DimensionalityType.NotSet,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    
    csys = work_part.WCS.CoordinateSystem
    assoc_point = work_part.Points.CreatePoint(
        csys, x_scalar, y_scalar, z_scalar,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    
    builder = work_part.Features.CreateBlockFeatureBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Type = NXOpen.Features.BlockFeatureBuilder.Types.OriginAndEdgeLengths
        builder.OriginPoint = assoc_point
        if x_vec is not None and y_vec is not None:
            builder.SetOrientation(x_vec, y_vec)
        builder.SetLength(lx_expr)
        builder.SetWidth(ly_expr)
        builder.SetHeight(lz_expr)
        builder.SetBooleanOperationAndTarget(
            NXOpen.Features.Feature.BooleanType.Create,
            NXOpen.Body.Null,
        )
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


def _create_cylinder_assoc(work_part, x_expr_name, y_expr_name, z_expr_name, dir_vec, dia_expr_name, height_expr_name):
    expr_x = work_part.Expressions.FindObject(x_expr_name)
    expr_y = work_part.Expressions.FindObject(y_expr_name)
    expr_z = work_part.Expressions.FindObject(z_expr_name)
    
    x_scalar = work_part.Scalars.CreateScalarExpression(
        expr_x, NXOpen.Scalar.DimensionalityType.NotSet,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    y_scalar = work_part.Scalars.CreateScalarExpression(
        expr_y, NXOpen.Scalar.DimensionalityType.NotSet,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    z_scalar = work_part.Scalars.CreateScalarExpression(
        expr_z, NXOpen.Scalar.DimensionalityType.NotSet,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    
    csys = work_part.WCS.CoordinateSystem
    assoc_point = work_part.Points.CreatePoint(
        csys, x_scalar, y_scalar, z_scalar,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )
    
    builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Diameter.RightHandSide = dia_expr_name
        builder.Height.RightHandSide = height_expr_name
        builder.Axis.Point = assoc_point
        direction = work_part.Directions.CreateDirection(
            assoc_point, dir_vec
        )
        builder.Axis.Direction = direction
        feat = builder.Commit()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


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
    uf_session = NXOpen.UF.UFSession.GetUFSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    # Register expressions (including coordinate calculation formulas)
    expressions = [
        ("BASE_LENGTH", "70.0"),
        ("BASE_WIDTH", "40.0"),
        ("BASE_THICK", "10.0"),
        ("SIDE_WALL_HEIGHT", "45.0"),
        ("SIDE_WALL_THICKNESS", "10.0"),
        ("INNER_GAP", "30.0"),
        ("WALL_TOP_OFFSET", "4.0"),
        ("BOSS_DIAMETER", "24.0"),
        ("BOSS_LENGTH", "12.0"),
        ("HOLE_DIAMETER", "10.0"),
        ("WALL_ANGLE", "arctan(WALL_TOP_OFFSET / SIDE_WALL_HEIGHT)"),
        ("L_local", "SIDE_WALL_HEIGHT / cos(WALL_ANGLE)"),
        ("BASE_CORNER_X", "-BASE_LENGTH / 2.0"),
        ("BASE_CORNER_Y", "-BASE_WIDTH / 2.0"),
        ("BASE_CORNER_Z", "0.0"),
        ("LEFT_WALL_X", "-INNER_GAP / 2.0 - SIDE_WALL_THICKNESS * cos(WALL_ANGLE)"),
        ("LEFT_WALL_Y", "-BASE_WIDTH / 2.0"),
        ("LEFT_WALL_Z", "BASE_THICK - SIDE_WALL_THICKNESS * sin(WALL_ANGLE)"),
        ("RIGHT_WALL_X", "INNER_GAP / 2.0"),
        ("RIGHT_WALL_Y", "-BASE_WIDTH / 2.0"),
        ("RIGHT_WALL_Z", "BASE_THICK"),
        ("LEFT_BOSS_X", "LEFT_WALL_X - (SIDE_WALL_HEIGHT / 2.0 + SIDE_WALL_THICKNESS * sin(WALL_ANGLE)) * tan(WALL_ANGLE)"),
        ("LEFT_BOSS_Y", "0.0"),
        ("LEFT_BOSS_Z", "BASE_THICK + SIDE_WALL_HEIGHT / 2.0"),
        ("RIGHT_BOSS_X", "RIGHT_WALL_X + SIDE_WALL_THICKNESS * cos(WALL_ANGLE) + (SIDE_WALL_HEIGHT / 2.0 + SIDE_WALL_THICKNESS * sin(WALL_ANGLE)) * tan(WALL_ANGLE)"),
        ("RIGHT_BOSS_Y", "0.0"),
        ("RIGHT_BOSS_Z", "BASE_THICK + SIDE_WALL_HEIGHT / 2.0"),
        ("LEFT_HOLE_X", "LEFT_BOSS_X - BOSS_LENGTH - 1.0"),
        ("RIGHT_HOLE_X", "RIGHT_BOSS_X + BOSS_LENGTH + 1.0"),
        ("HOLE_DEPTH", "BOSS_LENGTH + SIDE_WALL_THICKNESS + 2.0"),
    ]

    for name, formula in expressions:
        work_part.Expressions.CreateExpression("Number", f"{name} = {formula}")

    # Get the evaluated wall angle from expressions to define direction vectors
    wall_angle_val = work_part.Expressions.FindObject("WALL_ANGLE").Value
    theta_rad = math.radians(wall_angle_val)
    
    # Left Wall local X vector (tilted left: Z = (-sin, 0, cos), X = (cos, 0, sin))
    x_vec_left = NXOpen.Vector3d(math.cos(theta_rad), 0.0, math.sin(theta_rad))
    y_vec_left = NXOpen.Vector3d(0.0, 1.0, 0.0)
    
    # Right Wall local X vector (tilted right: Z = (sin, 0, cos), X = (cos, 0, -sin))
    x_vec_right = NXOpen.Vector3d(math.cos(theta_rad), 0.0, -math.sin(theta_rad))
    y_vec_right = NXOpen.Vector3d(0.0, 1.0, 0.0)

    # 1. Base Plate Block
    main_body = _create_block_assoc(
        work_part, "BASE_CORNER_X", "BASE_CORNER_Y", "BASE_CORNER_Z",
        "BASE_LENGTH", "BASE_WIDTH", "BASE_THICK"
    )
    
    # 2. Left Side Wall Block
    left_wall = _create_block_assoc(
        work_part, "LEFT_WALL_X", "LEFT_WALL_Y", "LEFT_WALL_Z",
        "SIDE_WALL_THICKNESS", "BASE_WIDTH", "L_local", x_vec_left, y_vec_left
    )
    
    # 3. Unite Left Side Wall
    _perform_unite(work_part, main_body, left_wall)
    
    # 4. Right Side Wall Block
    right_wall = _create_block_assoc(
        work_part, "RIGHT_WALL_X", "RIGHT_WALL_Y", "RIGHT_WALL_Z",
        "SIDE_WALL_THICKNESS", "BASE_WIDTH", "L_local", x_vec_right, y_vec_right
    )
    
    # 5. Unite Right Side Wall
    _perform_unite(work_part, main_body, right_wall)
    
    # 6. Left Boss Cylinder
    left_boss = _create_cylinder_assoc(
        work_part, "LEFT_BOSS_X", "LEFT_BOSS_Y", "LEFT_BOSS_Z",
        NXOpen.Vector3d(-1.0, 0.0, 0.0), "BOSS_DIAMETER", "BOSS_LENGTH"
    )
    
    # 7. Unite Left Boss
    _perform_unite(work_part, main_body, left_boss)
    
    # 8. Right Boss Cylinder
    right_boss = _create_cylinder_assoc(
        work_part, "RIGHT_BOSS_X", "RIGHT_BOSS_Y", "RIGHT_BOSS_Z",
        NXOpen.Vector3d(1.0, 0.0, 0.0), "BOSS_DIAMETER", "BOSS_LENGTH"
    )
    
    # 9. Unite Right Boss
    _perform_unite(work_part, main_body, right_boss)
    
    # 10. Left Hole Cylinder
    left_hole = _create_cylinder_assoc(
        work_part, "LEFT_HOLE_X", "LEFT_BOSS_Y", "LEFT_BOSS_Z",
        NXOpen.Vector3d(1.0, 0.0, 0.0), "HOLE_DIAMETER", "HOLE_DEPTH"
    )
    
    # 11. Subtract Left Hole
    _perform_subtract(work_part, main_body, left_hole)
    
    # 12. Right Hole Cylinder
    right_hole = _create_cylinder_assoc(
        work_part, "RIGHT_HOLE_X", "RIGHT_BOSS_Y", "RIGHT_BOSS_Z",
        NXOpen.Vector3d(-1.0, 0.0, 0.0), "HOLE_DIAMETER", "HOLE_DEPTH"
    )
    
    # 13. Subtract Right Hole
    _perform_subtract(work_part, main_body, right_hole)

    # 8. Fit View and Save
    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    
    # Update latest_nx_result.txt and open_current_nx_result.cmd
    try:
        abs_path_str = str(output_path.resolve())

        latest_file = output_path.parent / "latest_nx_result.txt"
        latest_file.write_text(abs_path_str, encoding="utf-8")

        project_root = Path(__file__).parent.parent.parent.parent.resolve()
        root_latest = project_root / "latest_nx_result.txt"
        root_latest.write_text(abs_path_str, encoding="utf-8")

        cmd_path = project_root / "open_current_nx_result.cmd"
        cmd_content = '@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{}"\n'.format(abs_path_str)
        cmd_path.write_text(cmd_content, encoding="utf-8")
        print("[OK] Result files updated.")
    except Exception as exc:
        print("[WARN] Could not update result files: {}".format(exc))

    print("[DONE] Parametric clevis mount bracket complete -> {}".format(output_path))


if __name__ == "__main__":
    main()
