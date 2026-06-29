"""
create_arm_assembly.py
======================
NX Journal: fully parametric L-shaped linkage arm assembly.

All dimensions stored as named NX Expressions.

Part Specification
------------------
  Arm Length              = 120 mm  (left tip to right face)
  Arm Width               = 30 mm
  Arm Thickness           = 10 mm
  End Radius              = 15 mm   (= Arm Width / 2, rounded left cap)
  Arm Hole Diameter       = 12 mm   (through-hole at left rounded end)
  Cylinder Diameter       = 30 mm   (boss at right end)
  Cylinder Height         = 60 mm
  Cylinder Top Hole Dia   = 12 mm   (through the cylinder axis)

Feature sequence
----------------
  1.  Named Expressions
  2.  Arm 1 Sketch (XY plane):
        - Top line, bottom line, right line, left semicircle, hole circle
        - Geometric constraints: Horizontal / Vertical
        - Dimensional constraints: HorizontalDim, VerticalDim, RadiusDim, DiameterDim
  3.  Extrude Arm 1 profile -> main_body (thickness = ARM_THICKNESS)
  4.  Cylinder boss sketch on top face of Arm 1 -> extrude -> unite with main_body
  5.  Copy arm 1 (MoveObject CopyOriginal, Associative):
        - Rotate 90 deg about cylinder axis (Z through cylinder center)
        - Translate delta-Z by ARM_THICKNESS + CYLINDER_HEIGHT
  6.  Unite arm2 into main_body
  7.  Arm-hole through entire combined body (Extrude Subtract)
  8.  Cylinder top-hole (Extrude Subtract)
  9.  Save part -> arm.prt
  10. Export STEP -> arm.step

Usage
-----
  run_journal.exe create_arm_assembly.py [arm.prt [arm.step]]
"""

import sys
import os
import math
from pathlib import Path
import subprocess

import NXOpen
import NXOpen.UF

# ---------------------------------------------------------------------------
# Parametric constants (mm)
# ---------------------------------------------------------------------------
ARM_LENGTH              = 120.0
ARM_WIDTH               =  30.0
ARM_THICKNESS           =  10.0
END_RADIUS              =  15.0
ARM_HOLE_DIAMETER       =  12.0
CYLINDER_DIAMETER       =  30.0
CYLINDER_HEIGHT         =  60.0
CYLINDER_TOP_HOLE_DIA   =  12.0


# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------
def _output_path():
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.parent.parent.parent.resolve() / "arm.prt"


def _step_path(part_path):
    if len(sys.argv) > 2:
        return Path(sys.argv[2]).resolve()
    # Always place arm.step next to arm.prt
    return part_path.with_suffix(".step")


# ---------------------------------------------------------------------------
# Boolean helpers
# ---------------------------------------------------------------------------
def _perform_subtract(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(
        NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Subtract
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body); break
                except Exception:
                    pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, tool_body); break
                except Exception:
                    pass
        builder.CommitFeature()
    finally:
        builder.Destroy()


def _perform_unite(work_part, target_body, tool_body):
    builder = work_part.Features.CreateBooleanBuilder(
        NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        for attr in ("Target", "TargetBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, target_body); break
                except Exception:
                    pass
        for attr in ("Tool", "ToolBody"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, tool_body); break
                except Exception:
                    pass
        builder.CommitFeature()
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Cylinder helper (for holes and boss)
# ---------------------------------------------------------------------------
def _create_cylinder(work_part, origin, direction_vec, diam_expr, height_expr):
    builder = work_part.Features.CreateCylinderBuilder(
        NXOpen.Features.Feature.Null)
    try:
        nx_dir = work_part.Directions.CreateDirection(
            origin, direction_vec,
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Diameter.RightHandSide = diam_expr
        builder.Height.RightHandSide   = height_expr
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = nx_dir
        feat = builder.Commit()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


# ---------------------------------------------------------------------------
# Sketch helpers
# ---------------------------------------------------------------------------
def _dim_geom(curve, assoc_type=None):
    """Build a Sketch.DimensionGeometry struct."""
    geom = NXOpen.Sketch.DimensionGeometry()
    geom.Geometry = curve
    if assoc_type is None:
        assoc_type = NXOpen.SketchAssocType.NotSet
    geom.AssocType = assoc_type
    return geom


def _con_geom(curve, point_type=None):
    """Build a Sketch.ConstraintGeometry struct."""
    geom = NXOpen.Sketch.ConstraintGeometry()
    geom.Geometry = curve
    if point_type is None:
        point_type = NXOpen.SketchConstraintPointType.NotSet
    geom.PointType = point_type
    return geom


def _apply_dim(sketch, dim_type, geom1, geom2, origin, expr, work_part):
    """Apply a driving dimensional constraint. geom2 may be None."""
    if geom2 is None:
        geom2 = NXOpen.Sketch.DimensionGeometry()
    try:
        sketch.CreateDimension(
            dim_type, geom1, geom2,
            origin, expr,
            NXOpen.SketchDimensionOption.CreateAsDriving)
    except Exception as exc:
        print("[WARN] Dimension {}: {}".format(dim_type, exc))


def _create_sketch_on_plane(work_part, plane_obj, sketch_name):
    factory = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder2", None)
    if factory is None:
        factory = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder", None)
    builder = factory(None)
    try:
        for attr in ("PlaneOrFace", "PlaneReference", "PlacementFace"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, plane_obj); break
                except Exception:
                    pass
        commit = getattr(builder, "CommitFeature", None) or getattr(builder, "Commit", None)
        feat = commit()
    finally:
        builder.Destroy()
    try:
        feat.SetName(sketch_name)
    except Exception:
        pass
    sketch = feat.Sketch if hasattr(feat, "Sketch") else feat
    return feat, sketch


def _extrude_curves(work_part, curves, z_start, z_end, feature_name):
    """Extrude a list of curves along +Z."""
    section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
    rules = [work_part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    section.AddToSection(
        rules, curves[0],
        NXOpen.NXObject.Null, NXOpen.NXObject.Null,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create, False)

    builder = work_part.Features.CreateExtrudeBuilder(
        NXOpen.Features.Feature.Null)
    try:
        builder.Section = section
        nx_dir = work_part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0),
            NXOpen.Vector3d(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Direction = nx_dir
        builder.Limits.StartExtend.Value.RightHandSide = str(float(z_start))
        builder.Limits.EndExtend.Value.RightHandSide   = str(float(z_end))
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()

    try:
        feat.SetName(feature_name)
    except Exception:
        pass
    return feat, feat.GetBodies()[0]


# ---------------------------------------------------------------------------
# Move Object helpers
# ---------------------------------------------------------------------------
def _copy_and_rotate(work_part, body, pivot_pt, axis_vec, angle_deg):
    """Copy body and rotate the copy. Returns the new body."""
    bodies_before = set(b.Tag for b in work_part.Bodies)

    builder = work_part.BaseFeatures.CreateMoveObjectBuilder(
        NXOpen.Features.MoveObject.Null)
    try:
        builder.MoveParents = False
        builder.Associative = True
        builder.MoveObjectResult = (
            NXOpen.Features.MoveObjectBuilder.MoveObjectResultOptions.CopyOriginal)
        builder.ObjectToMoveObject.Add(body)

        builder.TransformMotion.Option = (
            NXOpen.GeometricUtilities.ModlMotion.Options.Angle)
        builder.TransformMotion.Angle.RightHandSide = str(float(angle_deg))

        axis = work_part.Axes.CreateAxis(
            pivot_pt, axis_vec,
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.TransformMotion.AngularAxis = axis

        builder.Commit()
    finally:
        builder.Destroy()

    new_bodies = [b for b in work_part.Bodies if b.Tag not in bodies_before]
    if not new_bodies:
        raise RuntimeError("CopyOriginal produced no new body")
    return new_bodies[0]


def _move_body_delta_z(work_part, body, dz_value):
    """Translate body along +Z by dz_value (float, mm)."""
    origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    builder = work_part.BaseFeatures.CreateMoveObjectBuilder(
        NXOpen.Features.MoveObject.Null)
    try:
        builder.MoveParents = False
        builder.Associative = True
        builder.MoveObjectResult = (
            NXOpen.Features.MoveObjectBuilder.MoveObjectResultOptions.MoveOriginal)
        builder.ObjectToMoveObject.Add(body)

        opts = NXOpen.GeometricUtilities.ModlMotion.Options
        tm   = builder.TransformMotion

        # Try Distance along +Z vector
        tm.Option = opts.Distance
        z_dir = work_part.Directions.CreateDirection(
            origin,
            NXOpen.Vector3d(0.0, 0.0, 1.0),
            NXOpen.SmartObject.UpdateOption.WithinModeling)

        # DistanceValue may be Expression or float depending on NX version
        dv = tm.DistanceValue
        if hasattr(dv, "RightHandSide"):
            dv.RightHandSide = str(float(dz_value))
        else:
            # plain float attribute
            tm.DistanceValue = float(dz_value)

        # DistanceVector
        try:
            tm.DistanceVector = z_dir
        except Exception:
            pass

        builder.Commit()
    finally:
        builder.Destroy()



def _export_step(session, step_file):
    step_path = Path(step_file).resolve()
    step_path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure any old file is removed first
    if step_path.exists():
        try:
            step_path.unlink()
        except Exception:
            pass
    abs_path = str(step_path)
    print("[INFO] STEP output path: {}".format(abs_path))

    creator = session.DexManager.CreateStepCreator()
    try:
        creator.ObjectTypes.Solids   = True
        creator.ObjectTypes.Surfaces = True
        creator.ObjectTypes.Curves   = False
        creator.OutputFile   = abs_path
        creator.SettingsFile = ""
        creator.Commit()
    finally:
        creator.Destroy()

    if step_path.exists() and step_path.stat().st_size > 0:
        print("[OK] STEP verified ({} bytes).".format(step_path.stat().st_size))
    else:
        print("[WARN] STEP file not found or empty at: {}".format(abs_path))



# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    output_path = _output_path()
    step_out    = _step_path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    for p in (output_path, step_out):
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    session   = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    print("=" * 60)
    print("  CREATING PARAMETRIC L-LINKAGE ARM ASSEMBLY")
    print("  Part: {}".format(output_path))
    print("  STEP: {}".format(step_out))
    print("=" * 60)

    # ----------------------------------------------------------------
    # 1. Named expressions
    # ----------------------------------------------------------------
    expr_defs = [
        ("ARM_LENGTH",              ARM_LENGTH),
        ("ARM_WIDTH",               ARM_WIDTH),
        ("ARM_THICKNESS",           ARM_THICKNESS),
        ("END_RADIUS",              END_RADIUS),
        ("ARM_HOLE_DIAMETER",       ARM_HOLE_DIAMETER),
        ("CYLINDER_DIAMETER",       CYLINDER_DIAMETER),
        ("CYLINDER_HEIGHT",         CYLINDER_HEIGHT),
        ("CYLINDER_TOP_HOLE_DIA",   CYLINDER_TOP_HOLE_DIA),
    ]
    for name, val in expr_defs:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, val))

    # Derived expression: flat length of the arm bar (from arc center to right face)
    flat_expr = work_part.Expressions.CreateExpression(
        "Number", "ARM_LENGTH_FLAT = ARM_LENGTH - END_RADIUS")
    print("[OK] Expressions registered.")

    z_axis = NXOpen.Vector3d(0.0, 0.0, 1.0)
    # Cylinder center in XY (right end of arm, Y=0)
    cyl_cx  = ARM_LENGTH - END_RADIUS   # = 105.0
    cyl_cy  = 0.0
    cyl_top_z = ARM_THICKNESS + CYLINDER_HEIGHT  # = 70.0

    # ----------------------------------------------------------------
    # 2. Arm 1 Sketch on XY plane
    # ----------------------------------------------------------------
    print("[...] Step 2: Arm 1 sketch ...")
    xy_plane = work_part.Planes.CreatePlane(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        z_axis,
        NXOpen.SmartObject.UpdateOption.WithinModeling)

    _, sk1 = _create_sketch_on_plane(work_part, xy_plane, "Arm1_Sketch")
    sk1.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    # Outer profile points
    r   = END_RADIUS   # = 15
    p_tl = NXOpen.Point3d(r,                 r,  0.0)   # top-left of bar
    p_tr = NXOpen.Point3d(ARM_LENGTH,         r,  0.0)   # top-right
    p_br = NXOpen.Point3d(ARM_LENGTH,        -r,  0.0)   # bottom-right
    p_bl = NXOpen.Point3d(r,                -r,  0.0)   # bottom-left

    l_top = work_part.Curves.CreateLine(p_tl, p_tr)
    l_rt  = work_part.Curves.CreateLine(p_tr, p_br)
    l_bot = work_part.Curves.CreateLine(p_br, p_bl)

    # Left semicircle: centre at (r, 0), from p_bl to p_tl going CCW
    orientation = work_part.WCS.CoordinateSystem.Orientation
    center = NXOpen.Point3d(r, 0.0, 0.0)
    l_arc = work_part.Curves.CreateArc(
        center, orientation, r,
        math.radians(90.0),   # from 90° (top-left)
        math.radians(270.0))  # to 270° (bottom-left), CCW half-circle

    # Hole circle at same centre
    l_hole = work_part.Curves.CreateArc(
        center, orientation, ARM_HOLE_DIAMETER / 2.0,
        0.0, 2.0 * math.pi)

    # Add all to sketch
    infer = NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints
    for curve in (l_top, l_rt, l_bot, l_arc, l_hole):
        sk1.AddGeometry(curve, infer)

    print("[OK] Sketch curves added.")

    # ---- Geometric Constraints ----
    try:
        sk1.CreateHorizontalConstraint(_con_geom(l_top))
    except Exception as e:
        print("[WARN] Horiz constraint l_top: {}".format(e))
    try:
        sk1.CreateHorizontalConstraint(_con_geom(l_bot))
    except Exception as e:
        print("[WARN] Horiz constraint l_bot: {}".format(e))
    try:
        sk1.CreateVerticalConstraint(_con_geom(l_rt))
    except Exception as e:
        print("[WARN] Vert constraint l_rt: {}".format(e))

    # Fix arc in place so dimensions drive it
    try:
        sk1.CreateFixedConstraint(_con_geom(l_arc))
    except Exception as e:
        print("[WARN] Fixed arc: {}".format(e))

    print("[OK] Geometric constraints applied.")

    # ---- Dimensional Constraints ----
    # Expressions for dimensions
    expr_arm_len_flat = work_part.Expressions.CreateExpression(
        "Number", "ARM_LENGTH_FLAT_DIM = ARM_LENGTH - END_RADIUS")
    expr_arm_width = work_part.Expressions.CreateExpression(
        "Number", "ARM_WIDTH_DIM = ARM_WIDTH")
    expr_end_radius = work_part.Expressions.CreateExpression(
        "Number", "END_RADIUS_DIM = END_RADIUS")
    expr_hole_dia = work_part.Expressions.CreateExpression(
        "Number", "ARM_HOLE_DIM = ARM_HOLE_DIAMETER")

    CT = NXOpen.SketchConstraintType
    DO = NXOpen.SketchDimensionOption

    # Horizontal dim on top line (from StartPoint to EndPoint)
    _apply_dim(sk1, CT.HorizontalDim,
               _dim_geom(l_top, NXOpen.SketchAssocType.StartPoint),
               _dim_geom(l_top, NXOpen.SketchAssocType.EndPoint),
               NXOpen.Point3d(cyl_cx / 2.0, r + 8.0, 0.0),
               expr_arm_len_flat, work_part)

    # Vertical dim on right line
    _apply_dim(sk1, CT.VerticalDim,
               _dim_geom(l_rt, NXOpen.SketchAssocType.StartPoint),
               _dim_geom(l_rt, NXOpen.SketchAssocType.EndPoint),
               NXOpen.Point3d(ARM_LENGTH + 10.0, 0.0, 0.0),
               expr_arm_width, work_part)

    # Radius dim on left arc
    _apply_dim(sk1, CT.RadiusDim,
               _dim_geom(l_arc), None,
               NXOpen.Point3d(-r - 5.0, 0.0, 0.0),
               expr_end_radius, work_part)

    # Diameter dim on hole circle
    _apply_dim(sk1, CT.DiameterDim,
               _dim_geom(l_hole), None,
               NXOpen.Point3d(r, r + 5.0, 0.0),
               expr_hole_dia, work_part)

    print("[OK] Dimensional constraints applied.")

    sk1.Deactivate(
        NXOpen.Sketch.ViewReorient.TrueValue,
        NXOpen.Sketch.UpdateLevel.Model)

    # ----------------------------------------------------------------
    # 3. Extrude Arm 1
    # ----------------------------------------------------------------
    print("[...] Step 3: Extruding Arm 1 ...")
    all_arm1_curves = [l_top, l_rt, l_bot, l_arc]
    _, main_body = _extrude_curves(
        work_part, all_arm1_curves,
        0.0, ARM_THICKNESS,
        "Arm1_Extrude")
    print("[OK] Arm 1 extruded (Z=0 -> Z={}).".format(ARM_THICKNESS))

    # ----------------------------------------------------------------
    # 4. Cylinder boss — direct cylinder feature (no sketch needed)
    # ----------------------------------------------------------------
    print("[...] Step 4: Cylinder boss ...")
    cyl_origin = NXOpen.Point3d(cyl_cx, cyl_cy, ARM_THICKNESS)
    cyl_body = _create_cylinder(
        work_part, cyl_origin, z_axis,
        "CYLINDER_DIAMETER", "CYLINDER_HEIGHT")
    _perform_unite(work_part, main_body, cyl_body)
    print("[OK] Cylinder boss united (Z={} -> Z={}).".format(
        ARM_THICKNESS, ARM_THICKNESS + CYLINDER_HEIGHT))

    session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)


    # ----------------------------------------------------------------
    # 5. Copy Arm 1 and rotate 90 deg about cylinder axis
    # ----------------------------------------------------------------
    print("[...] Step 5: Copy Arm 1 and rotate 90 deg ...")
    pivot = NXOpen.Point3d(cyl_cx, cyl_cy, 0.0)
    arm2_body = _copy_and_rotate(
        work_part, main_body, pivot, z_axis, 90.0)
    print("[OK] Arm 2 body created (copy+rotate).")

    # ----------------------------------------------------------------
    # 6. Translate Arm 2 to cylinder top face
    # ----------------------------------------------------------------
    print("[...] Step 6: Translate Arm 2 to Z={} ...".format(cyl_top_z))
    _move_body_delta_z(
        work_part, arm2_body,
        float(ARM_THICKNESS + CYLINDER_HEIGHT))
    print("[OK] Arm 2 translated to Z={}..{}.".format(
        cyl_top_z, cyl_top_z + ARM_THICKNESS))


    session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)

    # ----------------------------------------------------------------
    # 7. Unite Arm 2 into main body
    # ----------------------------------------------------------------
    print("[...] Step 7: Unite Arm 2 ...")
    _perform_unite(work_part, main_body, arm2_body)
    print("[OK] Arm 2 united.")

    session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)
    body_count = sum(1 for b in work_part.Bodies if b.IsSolidBody)
    print("[INFO] Solid body count: {}".format(body_count))

    # ----------------------------------------------------------------
    # 8. Arm 1 through-hole at left rounded end (at END_RADIUS, 0)
    # ----------------------------------------------------------------
    print("[...] Step 8: Arm 1 through-hole ...")
    h1_origin = NXOpen.Point3d(END_RADIUS, 0.0, -1.0)
    h1_body   = _create_cylinder(
        work_part, h1_origin, z_axis,
        "ARM_HOLE_DIAMETER",
        str(ARM_THICKNESS + 2.0))
    _perform_subtract(work_part, main_body, h1_body)
    print("[OK] Arm 1 through-hole at ({},{}).".format(END_RADIUS, 0))

    # ----------------------------------------------------------------
    # 9. Cylinder top-hole (12 mm dia through cylinder + body)
    # ----------------------------------------------------------------
    print("[...] Step 9: Cylinder top through-hole ...")
    bore_total = ARM_THICKNESS + CYLINDER_HEIGHT + ARM_THICKNESS + 2.0
    h2_origin  = NXOpen.Point3d(cyl_cx, cyl_cy, -1.0)
    h2_body    = _create_cylinder(
        work_part, h2_origin, z_axis,
        "CYLINDER_TOP_HOLE_DIA",
        str(bore_total))
    _perform_subtract(work_part, main_body, h2_body)
    print("[OK] Cylinder top through-hole at ({},{}).".format(cyl_cx, cyl_cy))

    session.UpdateManager.DoUpdate(session.NewestVisibleUndoMark)

    # ----------------------------------------------------------------
    # 10. Save part
    # ----------------------------------------------------------------
    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue)
    print("=" * 60)
    print("[OK] Part saved -> {}".format(output_path))
    print("=" * 60)

    # ----------------------------------------------------------------
    # 11. Export STEP
    # ----------------------------------------------------------------
    print("[...] Exporting STEP ...")
    try:
        _export_step(session, step_out)
        print("[OK] STEP exported -> {}".format(step_out))
    except Exception as exc:
        print("[WARN] STEP export failed: {}".format(exc))

    # ----------------------------------------------------------------
    # Result files + auto-open
    # ----------------------------------------------------------------
    try:
        abs_str = str(output_path.resolve())
        root    = Path(__file__).parent.parent.parent.parent.resolve()
        (root / "latest_nx_result.txt").write_text(abs_str, encoding="utf-8")
        cmd = ('@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe"'
               ' -ug -use_file_dir "{}"\n').format(abs_str)
        (root / "open_current_nx_result.cmd").write_text(cmd, encoding="utf-8")
        print("[OK] Result files updated.")
    except Exception as exc:
        print("[WARN] Result file update: {}".format(exc))

    try:
        base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        ugs = next((c for c in [base_path / "NXBIN" / "ugs_router.exe",
                                 base_path / "UGII"  / "ugs_router.exe"]
                    if c.exists()), None)
        if ugs:
            subprocess.Popen([str(ugs), "-ug", "-use_file_dir",
                              str(output_path.resolve())])
            print("[OK] NX GUI launched.")
        else:
            print("[WARN] ugs_router.exe not found; open the part manually.")
    except Exception as exc:
        print("[WARN] Auto-open: {}".format(exc))

    print("[DONE] L-linkage arm assembly complete.")


if __name__ == "__main__":
    main()
