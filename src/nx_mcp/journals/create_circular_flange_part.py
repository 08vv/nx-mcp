import math
import sys
import os
from pathlib import Path
import subprocess

import NXOpen

OUTER_DIAMETER = 120.0
THICKNESS = 15.0
CENTER_BORE_DIAMETER = 50.0
BOLT_CIRCLE_DIAMETER = 95.0
BOLT_HOLE_DIAMETER = 10.0
BOLT_HOLE_COUNT = 6


def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path.cwd().joinpath("circular_flange_6_holes.prt").resolve()


def perform_subtract(work_part, target_body, tool_body):
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


def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    # Create Named Expressions
    expressions = [
        ("OUTER_DIAMETER", OUTER_DIAMETER),
        ("THICKNESS", THICKNESS),
        ("CENTER_BORE_DIAMETER", CENTER_BORE_DIAMETER),
        ("BOLT_CIRCLE_DIAMETER", BOLT_CIRCLE_DIAMETER),
        ("BOLT_HOLE_DIAMETER", BOLT_HOLE_DIAMETER),
        ("BOLT_HOLE_COUNT", BOLT_HOLE_COUNT),
    ]
    for name, value in expressions:
        work_part.Expressions.CreateExpression("Number", f"{name} = {value}")

    # 1. Main outer cylinder
    cylinder_builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        dir_vector = NXOpen.Vector3d(0.0, 0.0, 1.0)
        direction = work_part.Directions.CreateDirection(origin, dir_vector, NXOpen.SmartObject.UpdateOption.WithinModeling)

        cylinder_builder.Diameter.RightHandSide = "OUTER_DIAMETER"
        cylinder_builder.Height.RightHandSide = "THICKNESS"
        cylinder_builder.Axis.Point.SetCoordinates(origin)
        cylinder_builder.Axis.Direction = direction

        main_feat = cylinder_builder.Commit()
    finally:
        cylinder_builder.Destroy()

    main_body = main_feat.GetBodies()[0]

    # 2. Center bore cylinder
    bore_builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        dir_vector = NXOpen.Vector3d(0.0, 0.0, 1.0)
        direction = work_part.Directions.CreateDirection(origin, dir_vector, NXOpen.SmartObject.UpdateOption.WithinModeling)

        bore_builder.Diameter.RightHandSide = "CENTER_BORE_DIAMETER"
        bore_builder.Height.RightHandSide = "THICKNESS"
        bore_builder.Axis.Point.SetCoordinates(origin)
        bore_builder.Axis.Direction = direction

        bore_feat = bore_builder.Commit()
    finally:
        bore_builder.Destroy()

    bore_body = bore_feat.GetBodies()[0]
    perform_subtract(work_part, main_body, bore_body)

    # 3. Create Bolt Holes at associative points
    csys = work_part.WCS.CoordinateSystem
    for i in range(int(BOLT_HOLE_COUNT)):
        # Create coordinates expressions
        expr_x = work_part.Expressions.CreateExpression("Number", f"HOLE_X_{i} = (BOLT_CIRCLE_DIAMETER / 2.0) * cos({i} * 360.0 / BOLT_HOLE_COUNT)")
        expr_y = work_part.Expressions.CreateExpression("Number", f"HOLE_Y_{i} = (BOLT_CIRCLE_DIAMETER / 2.0) * sin({i} * 360.0 / BOLT_HOLE_COUNT)")
        expr_z = work_part.Expressions.CreateExpression("Number", f"HOLE_Z_{i} = 0.0")

        # Create associative scalars and point
        x_scalar = work_part.Scalars.CreateScalarExpression(expr_x, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)
        y_scalar = work_part.Scalars.CreateScalarExpression(expr_y, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)
        z_scalar = work_part.Scalars.CreateScalarExpression(expr_z, NXOpen.Scalar.DimensionalityType.NotSet, NXOpen.SmartObject.UpdateOption.WithinModeling)
        
        assoc_point = work_part.Points.CreatePoint(csys, x_scalar, y_scalar, z_scalar, NXOpen.SmartObject.UpdateOption.WithinModeling)

        hole_builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
        try:
            hole_builder.Diameter.RightHandSide = "BOLT_HOLE_DIAMETER"
            hole_builder.Height.RightHandSide = "THICKNESS"
            
            # Set the associative point
            hole_builder.Axis.Point = assoc_point

            # Create associative direction based on the point
            dir_vector = NXOpen.Vector3d(0.0, 0.0, 1.0)
            direction = work_part.Directions.CreateDirection(assoc_point, dir_vector)
            hole_builder.Axis.Direction = direction

            hole_feat = hole_builder.Commit()
        finally:
            hole_builder.Destroy()

        hole_body = hole_feat.GetBodies()[0]
        perform_subtract(work_part, main_body, hole_body)

    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print(f"Created circular flange: {output_path}")

    # Write to latest_nx_result.txt
    try:
        latest_file = Path(output_path).parent / "latest_nx_result.txt"
        latest_file.write_text(str(output_path.resolve()), encoding="utf-8")
        print(f"Updated latest_nx_result.txt with: {output_path}")
    except Exception as e:
        print(f"Failed to write to latest_nx_result.txt: {e}")

    # Auto-open the part in Siemens NX GUI
    try:
        base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        ugs_router_candidates = [
            base_path / "NXBIN" / "ugs_router.exe",
            base_path / "UGII" / "ugs_router.exe",
        ]
        ugs_router_path = next((c for c in ugs_router_candidates if c.exists()), None)
        if ugs_router_path:
            subprocess.Popen([str(ugs_router_path), "-ug", "-use_file_dir", str(output_path.resolve())])
            print(f"Launched NX GUI to open: {output_path}")
        else:
            print("Could not find ugs_router.exe to open the part.")
    except Exception as e:
        print(f"Failed to auto-open in NX GUI: {e}")


if __name__ == "__main__":
    main()
