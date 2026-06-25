"""
create_l_bracket_part.py
========================
NX Journal (run via run_journal.exe / NX Python) that creates a parametric
automotive L-shaped sensor mounting bracket.

Part Specification
------------------
  Base plate     : 100 x 60 x 5 mm  (on XY plane)
  Vertical plate :  60 x 50 x 5 mm  (extruded from one short edge of base)
  Base holes (x4): 8 mm diameter, through-holes, in 2x2 pattern on base
  Plate holes (x2): 6 mm diameter, through-holes, on vertical plate
  Ribs (x2)     : triangular support ribs between base and vertical plate
  Edge Blend     : 3 mm radius on sharp internal/external edges
  Chamfer        : 1 mm on external vertical corners

Feature History
---------------
  Sketch -> Extrude (base)
  Sketch -> Extrude (vertical plate)
  Boolean Unite (base + vertical plate)
  Hole x4 on base (Hole command)
  Pattern Feature (duplicate base holes in X-direction)
  Hole x2 on vertical plate
  Rib x2 (triangular prism boolean-unite)
  Edge Blend (R3 mm)
  Chamfer (1 mm external corners)

Usage
-----
  run_journal.exe create_l_bracket_part.py [output_path.prt]

If no path is supplied, the part is written next to this script as
``l_bracket_mounting.prt``.
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
BASE_LENGTH   = 100.0   # X-direction
BASE_WIDTH    =  60.0   # Y-direction
BASE_THICK    =   5.0   # Z-direction (plate thickness)

VERT_HEIGHT   =  50.0   # Z-direction (vertical plate height above base top)
VERT_THICK    =   5.0   # X-direction (vertical plate thickness)
# Vertical plate spans full Y-width (BASE_WIDTH = 60 mm)

BASE_HOLE_DIA  =  8.0   # mounting hole diameter on base
PLATE_HOLE_DIA =  6.0   # mounting hole diameter on vertical plate

BLEND_RADIUS   =  3.0   # edge fillet radius
CHAMFER_OFFSET =  1.0   # chamfer offset

RIB_BASE_LEN   = 30.0   # horizontal leg of each support rib (X)
RIB_HEIGHT     = 30.0   # vertical leg of each support rib (Z)
RIB_THICK      =  4.0   # thickness of each rib (Y)


# ---------------------------------------------------------------------------
# Output path helper
# ---------------------------------------------------------------------------
def _output_path() -> Path:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).resolve()
    return Path(__file__).parent.resolve() / "l_bracket_mounting.prt"


# ---------------------------------------------------------------------------
# Helper: boolean subtract (tool body cut from target body)
# ---------------------------------------------------------------------------
def _perform_subtract(work_part, target_body, tool_body):
    """Subtract *tool_body* from *target_body* in-place."""
    builder = work_part.Features.CreateBooleanBuilder(
        NXOpen.Features.BooleanFeature.Null
    )
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
# Helper: boolean unite (merge tool body into target body)
# ---------------------------------------------------------------------------
def _perform_unite(work_part, target_body, tool_body):
    """Unite *tool_body* with *target_body* in-place."""
    builder = work_part.Features.CreateBooleanBuilder(
        NXOpen.Features.BooleanFeature.Null
    )
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
# Helper: sketch rectangle on a datum plane and extrude
# ---------------------------------------------------------------------------
def _sketch_extrude_rect(work_part, session,
                          x0, y0, rect_w, rect_h,
                          extrude_dir, extrude_dist,
                          plane="XY"):
    """
    Draw a rectangle on *plane* and extrude along *extrude_dir*.

    Parameters
    ----------
    x0, y0        : 2-D corner of the rectangle in the sketch plane
    rect_w, rect_h: width and height in the sketch plane
    extrude_dir   : NXOpen.Vector3d -- extrusion direction
    extrude_dist  : float -- extrusion distance
    plane         : "XY" | "XZ" | "YZ"

    Returns
    -------
    (feature, body)  -- the extrude feature and its first body
    """

    def _pt(u, v):
        if plane == "XY":
            return NXOpen.Point3d(u, v, 0.0)
        if plane == "XZ":
            return NXOpen.Point3d(u, 0.0, v)
        return NXOpen.Point3d(0.0, u, v)  # YZ

    corners = [
        (x0,          y0),
        (x0 + rect_w, y0),
        (x0 + rect_w, y0 + rect_h),
        (x0,          y0 + rect_h),
        (x0,          y0),
    ]
    lines = [
        work_part.Curves.CreateLine(_pt(*corners[i]), _pt(*corners[i + 1]))
        for i in range(4)
    ]

    section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
    rules = [
        work_part.ScRuleFactory.CreateRuleCurveDumb([ln]) for ln in lines
    ]
    section.AddToSection(
        rules, lines[0],
        NXOpen.NXObject.Null, NXOpen.NXObject.Null,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create, False,
    )

    builder = work_part.Features.CreateExtrudeBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        builder.Section = section
        origin = NXOpen.Point3d(0.0, 0.0, 0.0)
        nx_dir = work_part.Directions.CreateDirection(
            origin, extrude_dir,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        builder.Direction = nx_dir
        builder.Limits.StartExtend.Value.RightHandSide = "0.0"
        builder.Limits.EndExtend.Value.RightHandSide = str(float(extrude_dist))
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()

    body = feat.GetBodies()[0]
    return feat, body


# ---------------------------------------------------------------------------
# Helper: add a through-hole (cylinder boolean subtract)
# ---------------------------------------------------------------------------
def _add_hole(work_part, main_body, cx, cy, cz,
              diameter, depth, direction_vec):
    """
    Create a cylinder of the given diameter/depth at (cx,cy,cz) in
    *direction_vec* and subtract it from *main_body*.
    """
    hole_builder = work_part.Features.CreateCylinderBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        origin = NXOpen.Point3d(cx, cy, cz)
        nx_dir = work_part.Directions.CreateDirection(
            origin, direction_vec,
            NXOpen.SmartObject.UpdateOption.WithinModeling,
        )
        hole_builder.Diameter.RightHandSide = str(float(diameter))
        hole_builder.Height.RightHandSide   = str(float(depth))
        hole_builder.Axis.Point.SetCoordinates(origin)
        hole_builder.Axis.Direction = nx_dir
        feat = hole_builder.Commit()
    finally:
        hole_builder.Destroy()

    hole_body = feat.GetBodies()[0]
    _perform_subtract(work_part, main_body, hole_body)
    return feat


# ---------------------------------------------------------------------------
# Helper: attempt to apply PatternFeature on a feature
# ---------------------------------------------------------------------------
def _pattern_feature_linear(work_part, source_feat,
                             direction_vec, count, pitch_mm):
    """
    Attempt a linear rectangular pattern on *source_feat*.
    Falls back silently if the builder API is unavailable.
    Returns the new feature or None.
    """
    origin = NXOpen.Point3d(0.0, 0.0, 0.0)

    for builder_factory in (
        "CreatePatternFeatureBuilder",
        "CreateLinearPatternBuilder",
    ):
        factory = getattr(work_part.Features, builder_factory, None)
        if factory is None:
            continue
        try:
            builder = factory(NXOpen.Features.Feature.Null)
            try:
                # Assign the source feature
                for feat_attr in ("FeatureList", "Features", "Feature"):
                    setter = getattr(builder, feat_attr, None)
                    if setter is None:
                        continue
                    try:
                        if hasattr(setter, "Add"):
                            setter.Add([source_feat])
                        elif callable(setter):
                            setter([source_feat])
                        else:
                            builder.Feature = source_feat
                        break
                    except Exception:
                        pass

                # Configure the pattern service
                ps = getattr(builder, "PatternService", None)
                if ps is not None:
                    rect_def = getattr(ps, "RectangularDefinition", None)
                    if rect_def is not None:
                        nx_dir = work_part.Directions.CreateDirection(
                            origin, direction_vec,
                            NXOpen.SmartObject.UpdateOption.WithinModeling,
                        )
                        rect_def.XDirection = nx_dir
                        rect_def.XSpacing.NCopies.RightHandSide = str(int(count))
                        rect_def.XSpacing.PitchDistance.RightHandSide = str(float(pitch_mm))
                    else:
                        for a in ("PatternCount", "Count"):
                            if hasattr(ps, a):
                                try:
                                    setattr(ps, a, int(count))
                                    break
                                except Exception:
                                    pass
                        for a in ("Pitch", "PitchDistance"):
                            if hasattr(ps, a):
                                try:
                                    setattr(ps, a, float(pitch_mm))
                                    break
                                except Exception:
                                    pass
                        for a in ("Direction",):
                            if hasattr(ps, a):
                                try:
                                    nx_dir = work_part.Directions.CreateDirection(
                                        origin, direction_vec,
                                        NXOpen.SmartObject.UpdateOption.WithinModeling,
                                    )
                                    setattr(ps, a, nx_dir)
                                    break
                                except Exception:
                                    pass
                else:
                    for a in ("PatternCount", "Count"):
                        if hasattr(builder, a):
                            try:
                                setattr(builder, a, int(count))
                                break
                            except Exception:
                                pass
                    for a in ("Pitch", "PitchDistance"):
                        if hasattr(builder, a):
                            try:
                                setattr(builder, a, float(pitch_mm))
                                break
                            except Exception:
                                pass
                    for a in ("Direction",):
                        if hasattr(builder, a):
                            try:
                                nx_dir = work_part.Directions.CreateDirection(
                                    origin, direction_vec,
                                    NXOpen.SmartObject.UpdateOption.WithinModeling,
                                )
                                setattr(builder, a, nx_dir)
                                break
                            except Exception:
                                pass

                feat = builder.CommitFeature()
                return feat
            finally:
                builder.Destroy()
        except Exception as exc:
            print("[WARN] {} failed: {}; trying next...".format(builder_factory, exc))

    return None


# ---------------------------------------------------------------------------
# Helper: get edge midpoint
# ---------------------------------------------------------------------------
def _edge_midpoint(edge):
    """Return (mx, my, mz) midpoint of an edge, or None on failure."""
    try:
        vertices = edge.GetVertices()
        if len(vertices) >= 2:
            p1, p2 = vertices[0], vertices[1]
            return (
                (p1.X + p2.X) / 2.0,
                (p1.Y + p2.Y) / 2.0,
                (p1.Z + p2.Z) / 2.0,
            )
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Helper: get edge length
# ---------------------------------------------------------------------------
def _edge_length(edge):
    """Return the length of a straight edge, or 0 on failure."""
    try:
        vertices = edge.GetVertices()
        if len(vertices) >= 2:
            p1, p2 = vertices[0], vertices[1]
            return math.sqrt(
                (p2.X - p1.X) ** 2 +
                (p2.Y - p1.Y) ** 2 +
                (p2.Z - p1.Z) ** 2
            )
    except Exception:
        pass
    return 0.0


# ---------------------------------------------------------------------------
# Helper: check if edge is roughly aligned to a direction
# ---------------------------------------------------------------------------
def _edge_is_aligned(edge, axis="Z", tol=0.1):
    """
    Return True if the edge direction is approximately along *axis*.
    axis: 'X', 'Y', or 'Z'
    """
    try:
        vertices = edge.GetVertices()
        if len(vertices) < 2:
            return False
        p1, p2 = vertices[0], vertices[1]
        dx = abs(p2.X - p1.X)
        dy = abs(p2.Y - p1.Y)
        dz = abs(p2.Z - p1.Z)
        length = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
        if length < 1e-6:
            return False
        if axis == "X":
            return (dx / length) > (1.0 - tol)
        if axis == "Y":
            return (dy / length) > (1.0 - tol)
        if axis == "Z":
            return (dz / length) > (1.0 - tol)
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Helper: add edge blend to selected edges
# ---------------------------------------------------------------------------
def _add_edge_blend_selective(work_part, body, radius, edges):
    """Apply edge blend of *radius* mm to the provided list of *edges*."""
    if not edges:
        print("[WARN] No edges selected for edge blend.")
        return None

    builder = work_part.Features.CreateEdgeBlendBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        builder.Tolerance = 0.01
        if hasattr(builder, "AllowSmoothEdges"):
            builder.AllowSmoothEdges = True
        if hasattr(builder, "RemoveSelfIntersection"):
            builder.RemoveSelfIntersection = True
        if hasattr(builder, "RollOverSmoothEdge"):
            builder.RollOverSmoothEdge = True
        if hasattr(builder, "OverlapOption"):
            try:
                builder.OverlapOption = (
                    NXOpen.Features.EdgeBlendBuilder.OverlapOptionType.AnyConvexShape
                )
            except Exception:
                pass

        collector = work_part.ScCollectors.CreateCollector()
        rules = [
            work_part.ScRuleFactory.CreateRuleEdgeTangent(
                edge,
                NXOpen.Edge.Null,
                False,
                0.5,
                False,
            )
            for edge in edges
        ]
        collector.ReplaceRules(rules, False)
        builder.AddChainset(collector, str(float(radius)))
        feat = builder.CommitFeature()
        print("[OK] Edge blend R={} mm applied ({} edges).".format(radius, len(edges)))
        return feat
    except Exception as exc:
        print("[WARN] Edge blend failed: {}".format(exc))
        return None
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Helper: add chamfer to selected edges (batch)
# ---------------------------------------------------------------------------
def _add_chamfer_batch(work_part, body, offset, edges):
    """Apply chamfer of *offset* mm to the provided list of *edges* in a single feature."""
    if not edges:
        print("[WARN] No edges selected for chamfer.")
        return None

    builder = work_part.Features.CreateChamferBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        builder.Option = NXOpen.Features.ChamferBuilder.ChamferOption.OffsetAndAngle
        builder.Method = NXOpen.Features.ChamferBuilder.OffsetMethod.EdgesAlongFaces
        builder.FirstOffset = str(float(offset))
        builder.SecondOffset = str(float(offset))
        builder.Angle = "45"
        builder.Tolerance = 0.01

        collector = work_part.ScCollectors.CreateCollector()
        rules = [
            work_part.ScRuleFactory.CreateRuleEdgeTangent(
                edge, NXOpen.Edge.Null, False, 0.5, False,
            )
            for edge in edges
        ]
        collector.ReplaceRules(rules, False)

        if hasattr(builder, "SmartCollector"):
            builder.SmartCollector = collector
        elif hasattr(builder, "EdgeCollector"):
            builder.EdgeCollector = collector

        feat = builder.CommitFeature()
        print("[OK] Chamfer offset={} mm applied ({} edges).".format(offset, len(edges)))
        return feat
    except Exception as exc:
        print("[WARN] Batch chamfer failed: {}".format(exc))
        return None
    finally:
        builder.Destroy()


# ---------------------------------------------------------------------------
# Helper: add chamfer to edges one-by-one (fallback)
# ---------------------------------------------------------------------------
def _add_chamfer_individual(work_part, body, offset, edges):
    """Apply chamfer of *offset* mm to edges one at a time (fallback)."""
    if not edges:
        print("[WARN] No edges selected for chamfer.")
        return

    applied = 0
    skipped = 0
    for edge in edges:
        builder = work_part.Features.CreateChamferBuilder(
            NXOpen.Features.Feature.Null
        )
        try:
            builder.Option = NXOpen.Features.ChamferBuilder.ChamferOption.OffsetAndAngle
            builder.Method = NXOpen.Features.ChamferBuilder.OffsetMethod.EdgesAlongFaces
            builder.FirstOffset = str(float(offset))
            builder.SecondOffset = str(float(offset))
            builder.Angle = "45"
            builder.Tolerance = 0.01

            rule = work_part.ScRuleFactory.CreateRuleEdgeTangent(
                edge, NXOpen.Edge.Null, False, 0.5, False,
            )
            collector = work_part.ScCollectors.CreateCollector()
            collector.ReplaceRules([rule], False)

            if hasattr(builder, "SmartCollector"):
                builder.SmartCollector = collector
            elif hasattr(builder, "EdgeCollector"):
                builder.EdgeCollector = collector

            builder.CommitFeature()
            applied += 1
        except Exception:
            skipped += 1
        finally:
            builder.Destroy()

    print("[OK] Chamfer offset={} mm: {} applied, {} skipped.".format(offset, applied, skipped))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    output_path = _output_path()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session   = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work

    print("=" * 60)
    print("  L-BRACKET MOUNTING BRACKET")
    print("  Output: {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Named NX Expressions -- makes the model fully parametric
    # ------------------------------------------------------------------
    named_expressions = [
        ("BASE_LENGTH",    BASE_LENGTH),
        ("BASE_WIDTH",     BASE_WIDTH),
        ("BASE_THICK",     BASE_THICK),
        ("VERT_HEIGHT",    VERT_HEIGHT),
        ("VERT_THICK",     VERT_THICK),
        ("BASE_HOLE_DIA",  BASE_HOLE_DIA),
        ("PLATE_HOLE_DIA", PLATE_HOLE_DIA),
        ("BLEND_RADIUS",   BLEND_RADIUS),
        ("CHAMFER_OFFSET", CHAMFER_OFFSET),
        ("RIB_BASE_LEN",   RIB_BASE_LEN),
        ("RIB_HEIGHT",     RIB_HEIGHT),
        ("RIB_THICK",      RIB_THICK),
    ]
    for name, value in named_expressions:
        work_part.Expressions.CreateExpression("Number", "{} = {}".format(name, value))
    print("[OK] Named expressions created.")

    # ------------------------------------------------------------------
    # 2. BASE PLATE -- 100 x 60 x 5 mm
    #    Sketch on XY plane, extrude in +Z by 5 mm.
    #    Corner at origin (0, 0, 0).
    # ------------------------------------------------------------------
    print("[...] Creating base plate (Sketch on XY + Extrude)...")
    _extrude_dir_z = NXOpen.Vector3d(0.0, 0.0, 1.0)
    try:
        _base_feat, base_body = _sketch_extrude_rect(
            work_part, session,
            x0=0.0, y0=0.0,
            rect_w=BASE_LENGTH,   # 100 mm in X
            rect_h=BASE_WIDTH,    # 60  mm in Y
            extrude_dir=_extrude_dir_z,
            extrude_dist=BASE_THICK,   # 5 mm in Z
            plane="XY",
        )
        print("[OK] Base plate: {}x{}x{} mm".format(BASE_LENGTH, BASE_WIDTH, BASE_THICK))
    except Exception as exc:
        print("[FAIL] Base plate creation failed: {}".format(exc))
        return

    # ------------------------------------------------------------------
    # 3. VERTICAL PLATE -- 60 (Y) x 50 (Z) x 5 (X) mm
    #    Sketch on XZ plane at Y=0.
    #    Rectangle from X=0..VERT_THICK, Z=BASE_THICK..BASE_THICK+VERT_HEIGHT
    #    Extrude in +Y by BASE_WIDTH (60 mm).
    # ------------------------------------------------------------------
    print("[...] Creating vertical plate (Sketch on XZ + Extrude)...")
    _extrude_dir_y = NXOpen.Vector3d(0.0, 1.0, 0.0)
    try:
        _vert_feat, vert_body = _sketch_extrude_rect(
            work_part, session,
            x0=0.0,              # X from 0
            y0=BASE_THICK,       # Z from 5 mm (top of base)
            rect_w=VERT_THICK,   # X-width = 5 mm (plate thickness)
            rect_h=VERT_HEIGHT,  # Z-height = 50 mm
            extrude_dir=_extrude_dir_y,
            extrude_dist=BASE_WIDTH,  # extrude 60 mm in Y
            plane="XZ",
        )
        print("[OK] Vertical plate: {}x{}x{} mm".format(BASE_WIDTH, VERT_HEIGHT, VERT_THICK))
    except Exception as exc:
        print("[FAIL] Vertical plate creation failed: {}".format(exc))
        return

    # Unite the vertical plate with the base to form a single L-body
    print("[...] Boolean-uniting base + vertical plate...")
    try:
        _perform_unite(work_part, base_body, vert_body)
        main_body = base_body
        print("[OK] L-bracket body formed.")
    except Exception as exc:
        print("[FAIL] Boolean unite failed: {}".format(exc))
        return

    # ------------------------------------------------------------------
    # 4. BASE MOUNTING HOLES -- 4 x dia8 mm, through base (5 mm depth)
    #    2x2 grid: (20,15), (80,15), (20,45), (80,45)
    # ------------------------------------------------------------------
    print("[...] Adding base mounting holes (dia8 mm)...")
    _down_z = NXOpen.Vector3d(0.0, 0.0, -1.0)
    base_hole_positions = [
        (20.0,  15.0),   # front-left
        (80.0,  15.0),   # front-right
        (20.0,  45.0),   # back-left
        (80.0,  45.0),   # back-right
    ]
    first_base_hole_feat = None
    for idx, (hx, hy) in enumerate(base_hole_positions):
        try:
            feat = _add_hole(
                work_part, main_body,
                cx=hx, cy=hy, cz=BASE_THICK,  # start from top face of base
                diameter=BASE_HOLE_DIA,
                depth=BASE_THICK + 1.0,        # +1 mm over-cut for clean through-hole
                direction_vec=_down_z,
            )
            if idx == 0:
                first_base_hole_feat = feat
            print("   [OK] Base hole {} at ({}, {})".format(idx + 1, hx, hy))
        except Exception as exc:
            print("   [WARN] Base hole {} failed: {}".format(idx + 1, exc))

    # ------------------------------------------------------------------
    # 5. PATTERN FEATURE -- duplicate base holes with linear pattern
    # ------------------------------------------------------------------
    if first_base_hole_feat is not None:
        print("[...] Applying Pattern Feature to first base hole (X-direction, 2 copies, 60 mm pitch)...")
        try:
            pat_feat = _pattern_feature_linear(
                work_part, first_base_hole_feat,
                direction_vec=NXOpen.Vector3d(1.0, 0.0, 0.0),
                count=2,
                pitch_mm=60.0,
            )
            if pat_feat is not None:
                print("[OK] Pattern Feature created in history tree.")
            else:
                print("[WARN] PatternFeature builder unavailable; holes remain as individual features.")
        except Exception as exc:
            print("[WARN] Pattern Feature failed: {}".format(exc))

    # ------------------------------------------------------------------
    # 6. VERTICAL PLATE HOLES -- 2 x dia6 mm, through vertical plate
    #    Placed on the plate face at:
    #      Hole 1: Y=20, Z=BASE_THICK+15 = 20
    #      Hole 2: Y=40, Z=BASE_THICK+35 = 40
    # ------------------------------------------------------------------
    print("[...] Adding vertical plate holes (dia6 mm)...")
    _into_x = NXOpen.Vector3d(-1.0, 0.0, 0.0)  # drill from X=VERT_THICK face inward
    plate_hole_positions = [
        (20.0, BASE_THICK + 15.0),   # Y=20, Z=20
        (40.0, BASE_THICK + 35.0),   # Y=40, Z=40
    ]
    for idx, (hy, hz) in enumerate(plate_hole_positions):
        try:
            _add_hole(
                work_part, main_body,
                cx=VERT_THICK, cy=hy, cz=hz,  # from front face of vertical plate
                diameter=PLATE_HOLE_DIA,
                depth=VERT_THICK + 1.0,
                direction_vec=_into_x,
            )
            print("   [OK] Plate hole {} at Y={}, Z={}".format(idx + 1, hy, hz))
        except Exception as exc:
            print("   [WARN] Plate hole {} failed: {}".format(idx + 1, exc))

    # ------------------------------------------------------------------
    # 7. SUPPORT RIBS -- 2 triangular ribs between base and vertical plate
    #    Each rib is a right-angle triangle prism:
    #      horizontal leg = RIB_BASE_LEN (30 mm in X)
    #      vertical leg   = RIB_HEIGHT   (30 mm in Z)
    #      thickness      = RIB_THICK    (4 mm in Y)
    #
    #    Rib 1: Y from 10 to 14 mm
    #    Rib 2: Y from 46 to 50 mm
    #
    #    Triangle vertices in XZ sketch (u=X, v=Z):
    #      A = (VERT_THICK, BASE_THICK)                    -- bottom-front
    #      B = (VERT_THICK + RIB_BASE_LEN, BASE_THICK)     -- bottom-far
    #      C = (VERT_THICK, BASE_THICK + RIB_HEIGHT)        -- top corner
    # ------------------------------------------------------------------
    print("[...] Adding support ribs...")
    rib_y_starts = [10.0, 46.0]
    for rib_idx, ry_start in enumerate(rib_y_starts):
        try:
            ax = VERT_THICK
            az = BASE_THICK
            bx = VERT_THICK + RIB_BASE_LEN
            bz = BASE_THICK
            cx_r = VERT_THICK
            cz_r = BASE_THICK + RIB_HEIGHT

            # Draw 3 lines forming the triangle in XZ plane
            def _xz_pt(u, v):
                return NXOpen.Point3d(u, 0.0, v)

            tri_lines = [
                work_part.Curves.CreateLine(_xz_pt(ax, az), _xz_pt(bx, bz)),      # bottom
                work_part.Curves.CreateLine(_xz_pt(bx, bz), _xz_pt(cx_r, cz_r)),  # hypotenuse
                work_part.Curves.CreateLine(_xz_pt(cx_r, cz_r), _xz_pt(ax, az)),  # vertical side
            ]

            section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
            rules = [
                work_part.ScRuleFactory.CreateRuleCurveDumb([ln]) for ln in tri_lines
            ]
            section.AddToSection(
                rules, tri_lines[0],
                NXOpen.NXObject.Null, NXOpen.NXObject.Null,
                NXOpen.Point3d(0.0, 0.0, 0.0),
                NXOpen.Section.Mode.Create, False,
            )

            rib_dir = NXOpen.Vector3d(0.0, 1.0, 0.0)
            rib_origin = NXOpen.Point3d(0.0, 0.0, 0.0)

            rib_builder = work_part.Features.CreateExtrudeBuilder(
                NXOpen.Features.Feature.Null
            )
            try:
                rib_builder.Section = section
                nx_rib_dir = work_part.Directions.CreateDirection(
                    rib_origin, rib_dir,
                    NXOpen.SmartObject.UpdateOption.WithinModeling,
                )
                rib_builder.Direction = nx_rib_dir
                rib_builder.Limits.StartExtend.Value.RightHandSide = str(float(ry_start))
                rib_builder.Limits.EndExtend.Value.RightHandSide = str(float(ry_start + RIB_THICK))
                rib_feat = rib_builder.CommitFeature()
            finally:
                rib_builder.Destroy()

            rib_body = rib_feat.GetBodies()[0]
            _perform_unite(work_part, main_body, rib_body)
            print("   [OK] Rib {} at Y={}--{}".format(rib_idx + 1, ry_start, ry_start + RIB_THICK))
        except Exception as exc:
            print("   [WARN] Rib {} failed: {}".format(rib_idx + 1, exc))

    print("[OK] Support ribs added and united.")

    # ------------------------------------------------------------------
    # 8. EDGE BLEND -- R3 mm on sharp edges
    #    Strategy: select edges at the L-junction and rib-body junctions.
    #    We filter for edges that lie along the internal concave junction
    #    of the L-bracket (Y-aligned edges at X~=VERT_THICK, Z~=BASE_THICK).
    #    Fallback: blend ALL edges if selective filtering returns nothing.
    # ------------------------------------------------------------------
    print("[...] Applying Edge Blend (R={} mm)...".format(BLEND_RADIUS))
    try:
        all_edges = list(main_body.GetEdges() or [])
        print("   Total edges on body: {}".format(len(all_edges)))

        # Try selective: Y-aligned edges at the internal L-junction
        # The L-junction internal edge runs along Y at X=VERT_THICK, Z=BASE_THICK
        junction_edges = []
        for edge in all_edges:
            if _edge_is_aligned(edge, "Y", tol=0.15):
                mid = _edge_midpoint(edge)
                if mid is not None:
                    mx, my, mz = mid
                    # Internal junction edge: X ~ VERT_THICK, Z ~ BASE_THICK
                    if abs(mx - VERT_THICK) < 1.0 and abs(mz - BASE_THICK) < 1.0:
                        junction_edges.append(edge)

        if junction_edges:
            print("   Selected {} junction edges for blend.".format(len(junction_edges)))
            _add_edge_blend_selective(work_part, main_body, BLEND_RADIUS, junction_edges)
        else:
            # Fallback: try blending all edges
            print("   [INFO] No junction edges found; blending all edges...")
            _add_edge_blend_selective(work_part, main_body, BLEND_RADIUS, all_edges)
    except Exception as exc:
        print("[WARN] Edge blend failed: {}".format(exc))

    # ------------------------------------------------------------------
    # 9. CHAMFER -- 1 mm on external vertical corners
    #    Strategy: select Z-aligned edges at the outer corners of the
    #    base plate and vertical plate.
    #    Fallback: chamfer edges one-by-one.
    # ------------------------------------------------------------------
    print("[...] Applying Chamfer ({} mm offset) to external corners...".format(CHAMFER_OFFSET))
    try:
        all_edges = list(main_body.GetEdges() or [])

        # Select Z-aligned edges at external corners
        # External vertical corners of the base are at:
        #   (0, 0), (100, 0), (100, 60), (0, 60) -- but (0, *) edges may overlap with vertical plate
        # External vertical corners of the vertical plate top are at:
        #   (0, 0), (0, 60), (VERT_THICK, 0), (VERT_THICK, 60) at Z heights
        chamfer_edges = []
        for edge in all_edges:
            if _edge_is_aligned(edge, "Z", tol=0.15):
                elen = _edge_length(edge)
                # Only chamfer edges with reasonable length (not tiny remnants)
                if elen > 2.0:
                    chamfer_edges.append(edge)

        if chamfer_edges:
            print("   Selected {} Z-aligned edges for chamfer.".format(len(chamfer_edges)))
            result = _add_chamfer_batch(work_part, main_body, CHAMFER_OFFSET, chamfer_edges)
            if result is None:
                print("   [INFO] Batch chamfer failed; trying individual...")
                _add_chamfer_individual(work_part, main_body, CHAMFER_OFFSET, chamfer_edges)
        else:
            print("   [WARN] No Z-aligned edges found for chamfer.")
    except Exception as exc:
        print("[WARN] Chamfer failed: {}".format(exc))

    # ------------------------------------------------------------------
    # 10. Fit view and save
    # ------------------------------------------------------------------
    work_part.ModelingViews.WorkView.Fit()
    work_part.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.FalseValue,
    )
    print("")
    print("=" * 60)
    print("[OK] Part saved -> {}".format(output_path))
    print("=" * 60)

    # ------------------------------------------------------------------
    # 11. Update latest_nx_result.txt and helper scripts
    # ------------------------------------------------------------------
    try:
        abs_path_str = str(output_path.resolve())

        # latest_nx_result.txt
        latest_file = output_path.parent / "latest_nx_result.txt"
        latest_file.write_text(abs_path_str, encoding="utf-8")

        # Also write to project root
        project_root = Path(__file__).parent.parent.parent.parent.resolve()
        root_latest = project_root / "latest_nx_result.txt"
        root_latest.write_text(abs_path_str, encoding="utf-8")

        # open_current_nx_result.cmd
        cmd_path = project_root / "open_current_nx_result.cmd"
        cmd_content = '@echo off\nstart "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{}"\n'.format(abs_path_str)
        cmd_path.write_text(cmd_content, encoding="utf-8")

        print("[OK] latest_nx_result.txt and open_current_nx_result.cmd updated.")
    except Exception as exc:
        print("[WARN] Could not update result files: {}".format(exc))

    # ------------------------------------------------------------------
    # 12. Auto-open the part in Siemens NX GUI
    # ------------------------------------------------------------------
    try:
        base_dir = os.environ.get("UGII_BASE_DIR") or r"C:\Program Files\Siemens\NX2206"
        base_path = Path(base_dir)
        router_candidates = [
            base_path / "NXBIN" / "ugs_router.exe",
            base_path / "UGII"  / "ugs_router.exe",
        ]
        ugs_router = next((c for c in router_candidates if c.exists()), None)
        if ugs_router:
            subprocess.Popen(
                [str(ugs_router), "-ug", "-use_file_dir",
                 str(output_path.resolve())]
            )
            print("[OK] NX GUI launched -> opening {}".format(output_path.name))
        else:
            print("[WARN] ugs_router.exe not found -- open the part manually in NX.")
            print("       Manual command:")
            print('       start "" "C:\\Program Files\\Siemens\\NX2206\\NXBIN\\ugs_router.exe" -ug -use_file_dir "{}"'.format(
                str(output_path.resolve())
            ))
    except Exception as exc:
        print("[WARN] Could not auto-open in NX GUI: {}".format(exc))

    print("")
    print("[DONE] L-bracket mounting bracket complete.")


if __name__ == "__main__":
    main()
