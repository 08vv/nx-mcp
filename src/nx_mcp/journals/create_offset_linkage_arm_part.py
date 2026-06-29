"""
create_offset_linkage_arm_part.py
==================================
NX Journal that creates a parametric offset linkage arm.
All dimensions are stored as named NX Expressions.
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
ARM_LENGTH      = 90.0
ARM_WIDTH       = 24.0
ARM_THICK       = 8.0
END_RADIUS      = 12.0
HOLE_DIA        = 10.0
HOLE_OFFSET     = 12.0
CYLINDER_DIA    = 22.0
CYLINDER_HEIGHT = 55.0
BLEND_RADIUS    = 2.0
CHAMFER_OFFSET  = 0.5


def _output_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path("C:/Users/HP/nx-mcp/offset_linkage_arm.prt").resolve()


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


def _create_cylinder(work_part, origin, direction_vec, diameter_expr, height_expr):
    builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        direction = work_part.Directions.CreateDirection(
            origin, direction_vec, NXOpen.SmartObject.UpdateOption.WithinModeling
        )
        builder.Diameter.RightHandSide = diameter_expr
        builder.Height.RightHandSide   = height_expr
        builder.Axis.Point.SetCoordinates(origin)
        builder.Axis.Direction = direction
        feat = builder.Commit()
    finally:
        builder.Destroy()
    return feat.GetBodies()[0]


def _create_block(work_part, corner_origin, length_str, width_str, height_str):
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

    # 1. Register named NX Expressions
    named_expressions = [
        ("ARM_LENGTH",      ARM_LENGTH),
        ("ARM_WIDTH",       ARM_WIDTH),
        ("ARM_THICK",       ARM_THICK),
        ("END_RADIUS",      END_RADIUS),
        ("HOLE_DIA",        HOLE_DIA),
        ("HOLE_OFFSET",     HOLE_OFFSET),
        ("CYLINDER_DIA",    CYLINDER_DIA),
        ("CYLINDER_HEIGHT", CYLINDER_HEIGHT),
        ("BLEND_RADIUS",    BLEND_RADIUS),
        ("CHAMFER_OFFSET",  CHAMFER_OFFSET),
    ]
    for name, value in named_expressions:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))

    z_axis = NXOpen.Vector3d(0.0, 0.0, 1.0)
    
    # 2. Build Lower Linkage Arm
    # Central block spans from X = 0 to X = ARM_LENGTH - 2 * END_RADIUS
    arm_len_between_centers = "ARM_LENGTH - 2 * END_RADIUS"
    
    lower_bar_corner = NXOpen.Point3d(0.0, -ARM_WIDTH/2.0, 0.0)
    main_body = _create_block(work_part, lower_bar_corner, arm_len_between_centers, "ARM_WIDTH", "ARM_THICK")
    
    # Left cap at (0, 0, 0)
    left_cap_origin = NXOpen.Point3d(0.0, 0.0, 0.0)
    left_cap = _create_cylinder(work_part, left_cap_origin, z_axis, "ARM_WIDTH", "ARM_THICK")
    _perform_unite(work_part, main_body, left_cap)
    
    # Right cap at (ARM_LENGTH - 2 * END_RADIUS, 0, 0)
    right_cap_origin = NXOpen.Point3d(ARM_LENGTH - 2.0 * END_RADIUS, 0.0, 0.0)
    right_cap = _create_cylinder(work_part, right_cap_origin, z_axis, "ARM_WIDTH", "ARM_THICK")
    _perform_unite(work_part, main_body, right_cap)
    
    # 3. Build Spacer Cylinder
    # Concentric with left cap at (0,0) starting at Z = ARM_THICK
    spacer_origin = NXOpen.Point3d(0.0, 0.0, ARM_THICK)
    spacer = _create_cylinder(work_part, spacer_origin, z_axis, "CYLINDER_DIA", "CYLINDER_HEIGHT")
    _perform_unite(work_part, main_body, spacer)
    
    # 4. Build Upper Linkage Arm
    # Concentric with spacer at X = 0, extending along -X direction
    upper_z_start = ARM_THICK + CYLINDER_HEIGHT
    
    # Upper central block spans from X = -(ARM_LENGTH - 2 * END_RADIUS) to X = 0
    upper_bar_corner = NXOpen.Point3d(-(ARM_LENGTH - 2.0 * END_RADIUS), -ARM_WIDTH/2.0, upper_z_start)
    upper_bar = _create_block(work_part, upper_bar_corner, arm_len_between_centers, "ARM_WIDTH", "ARM_THICK")
    
    # Right cap at (0, 0, upper_z_start)
    upper_right_cap_origin = NXOpen.Point3d(0.0, 0.0, upper_z_start)
    upper_right_cap = _create_cylinder(work_part, upper_right_cap_origin, z_axis, "ARM_WIDTH", "ARM_THICK")
    _perform_unite(work_part, upper_bar, upper_right_cap)
    
    # Left cap at (-(ARM_LENGTH - 2 * END_RADIUS), 0, upper_z_start)
    upper_left_cap_origin = NXOpen.Point3d(-(ARM_LENGTH - 2.0 * END_RADIUS), 0.0, upper_z_start)
    upper_left_cap = _create_cylinder(work_part, upper_left_cap_origin, z_axis, "ARM_WIDTH", "ARM_THICK")
    _perform_unite(work_part, upper_bar, upper_left_cap)
    
    # Unite upper arm into main_body
    _perform_unite(work_part, main_body, upper_bar)
    
    # 5. Create Holes
    hole_height_total = "2 * ARM_THICK + CYLINDER_HEIGHT + 2.0"
    
    # Left joint through-hole (X=0)
    h_joint_origin = NXOpen.Point3d(0.0, 0.0, -1.0)
    h_joint = _create_cylinder(work_part, h_joint_origin, z_axis, "HOLE_DIA", hole_height_total)
    _perform_subtract(work_part, main_body, h_joint)
    
    # Lower arm outer hole at X = ARM_LENGTH - 2 * END_RADIUS
    h_lower_origin = NXOpen.Point3d(ARM_LENGTH - 2.0 * END_RADIUS, 0.0, -1.0)
    h_lower = _create_cylinder(work_part, h_lower_origin, z_axis, "HOLE_DIA", "ARM_THICK + 2.0")
    _perform_subtract(work_part, main_body, h_lower)
    
    # Upper arm outer hole at X = -(ARM_LENGTH - 2 * END_RADIUS)
    h_upper_origin = NXOpen.Point3d(-(ARM_LENGTH - 2.0 * END_RADIUS), 0.0, upper_z_start - 1.0)
    h_upper = _create_cylinder(work_part, h_upper_origin, z_axis, "HOLE_DIA", "ARM_THICK + 2.0")
    _perform_subtract(work_part, main_body, h_upper)

    # 6. Apply Edge Blend to outer_edges
    all_edges = list(main_body.GetEdges())
    
    def _is_hole_or_junction_edge(pt, hole_dia, cyl_dia, arm_len_centers):
        # distance from Z-axis (x=0, y=0)
        d_center = math.sqrt(pt[0]**2 + pt[1]**2)
        if abs(d_center - hole_dia/2.0) < 0.1 or abs(d_center - cyl_dia/2.0) < 0.1:
            return True
        # distance from lower hole (x = arm_len_centers, y = 0)
        d_lower = math.sqrt((pt[0] - arm_len_centers)**2 + pt[1]**2)
        if abs(d_lower - hole_dia/2.0) < 0.1:
            return True
        # distance from upper hole (x = -arm_len_centers, y = 0)
        d_upper = math.sqrt((pt[0] + arm_len_centers)**2 + pt[1]**2)
        if abs(d_upper - hole_dia/2.0) < 0.1:
            return True
        return False

    outer_edges = []
    arm_len_centers = ARM_LENGTH - 2.0 * END_RADIUS
    max_z = 2.0 * ARM_THICK + CYLINDER_HEIGHT
    for edge in all_edges:
        try:
            pt1, pt2, _ = uf_session.Modeling.AskEdgeVerts(edge.Tag)
            # filter out vertical edges
            if abs(pt1[0] - pt2[0]) < 0.001 and abs(pt1[1] - pt2[1]) < 0.001:
                continue
            # filter out top edges of upper arm (Z = max_z) so they can be chamfered instead
            if abs(pt1[2] - max_z) < 0.001 and abs(pt2[2] - max_z) < 0.001:
                continue
            # filter out hole and cylinder joint edges
            mid_pt = ((pt1[0] + pt2[0]) / 2.0, (pt1[1] + pt2[1]) / 2.0, (pt1[2] + pt2[2]) / 2.0)
            if _is_hole_or_junction_edge(mid_pt, HOLE_DIA, CYLINDER_DIA, arm_len_centers):
                continue
            outer_edges.append(edge)
        except Exception:
            pass

    if outer_edges:
        blend_builder = work_part.Features.CreateEdgeBlendBuilder(NXOpen.Features.Feature.Null)
        try:
            collector = work_part.ScCollectors.CreateCollector()
            rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in outer_edges]
            collector.ReplaceRules(rules, False)
            blend_builder.Tolerance = 0.01
            blend_builder.AddChainset(collector, "BLEND_RADIUS")
            blend_builder.CommitFeature()
        finally:
            blend_builder.Destroy()

    # 7. Apply Chamfer to top_edges (edges at max Z)
    max_z = 2.0 * ARM_THICK + CYLINDER_HEIGHT
    top_edges = []
    for edge in list(main_body.GetEdges()):
        try:
            pt1, pt2, _ = uf_session.Modeling.AskEdgeVerts(edge.Tag)
            if abs(pt1[2] - max_z) < 0.001 and abs(pt2[2] - max_z) < 0.001:
                # Keep top outer profile and top hole edges
                top_edges.append(edge)
        except Exception:
            pass

    if top_edges:
        chamfer_builder = work_part.Features.CreateChamferBuilder(NXOpen.Features.Feature.Null)
        try:
            chamfer_builder.Option = NXOpen.Features.ChamferBuilder.ChamferOption.OffsetAndAngle
            chamfer_builder.Method = NXOpen.Features.ChamferBuilder.OffsetMethod.EdgesAlongFaces
            chamfer_builder.FirstOffset = "CHAMFER_OFFSET"
            chamfer_builder.SecondOffset = "CHAMFER_OFFSET"
            chamfer_builder.Angle = "45"
            chamfer_builder.Tolerance = 0.01
            rules = [work_part.ScRuleFactory.CreateRuleEdgeTangent(e, NXOpen.Edge.Null, False, 0.5, False) for e in top_edges]
            collector = work_part.ScCollectors.CreateCollector()
            collector.ReplaceRules(rules, False)
            chamfer_builder.SmartCollector = collector
            chamfer_builder.CommitFeature()
        finally:
            chamfer_builder.Destroy()

    # 8. Fit View and Save
    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    # 9. Update latest_nx_result.txt and open_current_nx_result.cmd
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

    print("[DONE] Parametric offset linkage arm complete -> {}".format(output_path))


if __name__ == "__main__":
    main()
