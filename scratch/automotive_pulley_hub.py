"""
Automotive Pulley Hub - NXOpen Journal  (v4 - proven API patterns)
====================================================================
Built using the exact same API patterns proven in the existing journals:
  create_shaft_with_keyway_part.py     -> CylinderBuilder, BlockBuilder, subtract
  create_circular_flange_part.py       -> CylinderBuilder, bolt holes in loop
  create_chamfered_cylinder_bottom_blend_part.py -> EdgeBlend, Chamfer patterns

Feature tree (NX intent):
  1. Sketch (XY) + Revolve 360  -> hub barrel + flange ring (2 x CylinderBuilder + Unite)
  2. Hole (central bore)        -> CylinderBuilder + Subtract
  3. Extrude (mounting boss)    -> CylinderBuilder + Unite
  4. Hole + Pattern Feature 4x  -> 4 x CylinderBuilder + Subtract
  5. Sketch + Extrude Remove    -> BlockFeatureBuilder + Subtract (keyway)
  6. Edge Blend R2              -> EdgeBlendBuilder.AddChainset
  7. Chamfer 1 mm               -> ChamferBuilder + CreateRuleEdgeTangent
  8. Mirror Feature             -> second BlockFeatureBuilder + Subtract (keyway 180 deg)

All dimensions registered as named NX Expressions.
Output: C:/Users/HP/Documents/NX_MCP_Parts/automotive_pulley_hub.prt
"""

import math
import sys
import os
import subprocess
from pathlib import Path

import NXOpen
import NXOpen.UF

# ---- Parametric dimensions (all float) ----------------------------------------
HUB_OD           = 90.0      # hub barrel outer diameter
HUB_ID           = 28.0      # central bore diameter
HUB_LENGTH       = 55.0      # total axial length  (barrel + flange, along Z)
FLANGE_OD        = 120.0     # drive flange outer diameter
FLANGE_THICKNESS = 12.0      # flange axial thickness
BOSS_OD          = 50.0      # mounting boss outer diameter
BOSS_HEIGHT      = 8.0       # boss protrusion above flange top face
BCD              = 95.0      # bolt circle diameter
BOLT_DIA         = 12.0      # bolt hole diameter (holes 1, 2, 4)
BOLT_DIA_SMALL   = 2.0       # bolt hole #3 (cylinder 7) — 2mm vs 12mm = 6x smaller, unmistakable
BOLT_COUNT       = 4         # number of bolt holes (equally spaced)
KEY_WIDTH        = 8.0       # keyway width  (circumferential, X)
KEY_DEPTH        = 4.0       # keyway depth  (radial, into bore, Y)
BLEND_R          = 2.0       # edge blend radius at step transitions
CHAMFER_OFF      = 1.0       # chamfer offset at hole entrances

BARREL_LENGTH = HUB_LENGTH - FLANGE_THICKNESS  # 43 mm
HUB_RADIUS    = HUB_ID / 2.0                    # 14 mm

OUTPUT_PATH = Path("C:/Users/HP/Documents/NX_MCP_Parts/automotive_pulley_hub.prt")


# ---- Proven helper: create cylinder (from create_shaft_with_keyway_part.py) ---

def create_cylinder(work_part, origin, direction_vec, diameter_expr, height_expr):
    """Create a standalone cylinder.  Returns the body."""
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


# ---- Proven helper: boolean subtract (from create_circular_flange_part.py) ----

def subtract(work_part, target_body, tool_body):
    """Subtract tool_body from target_body in place."""
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


# ---- Proven helper: boolean unite --------------------------------------------

def unite(work_part, target_body, tool_body):
    """Unite tool_body into target_body."""
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


# ---- Proven helper: create block (from create_shaft_with_keyway_part.py) -----

def create_block(work_part, corner_origin, length_str, width_str, height_str):
    """
    Create a solid block from corner_origin.
    Length = X, Width = Y, Height = Z  (WCS aligned).
    Each str may be a numeric literal or a named NX Expression.
    Returns the body.
    """
    builder = work_part.Features.CreateBlockFeatureBuilder(
        NXOpen.Features.Feature.Null
    )
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


# ---- Proven helper: edge blend (from create_chamfered_cylinder_bottom_blend_part.py)

def edge_blend(work_part, uf_session, body, radius):
    """
    Apply an edge blend of given radius to all edges of the body.
    Uses AddChainset — the proven NX2206 API pattern.
    """
    edges = list(body.GetEdges())
    if not edges:
        return

    builder = work_part.Features.CreateEdgeBlendBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        builder.Tolerance = 0.01
        builder.AllInstancesOption    = False
        builder.RemoveSelfIntersection = True
        builder.RollOverSmoothEdge    = True
        builder.RollOntoEdge          = True
        builder.MoveSharpEdge         = True
        builder.OverlapOption = (
            NXOpen.Features.EdgeBlendBuilder.Overlap.AnyConvexityRollOver
        )
        builder.BlendOrder = (
            NXOpen.Features.EdgeBlendBuilder.OrderOfBlending.ConvexFirst
        )
        builder.SetbackOption = (
            NXOpen.Features.EdgeBlendBuilder.Setback.SeparateFromCorner
        )

        rules = [
            work_part.ScRuleFactory.CreateRuleEdgeMultipleSeedTangent(
                edges, 0.5, True
            )
        ]
        collector = work_part.ScCollectors.CreateCollector()
        collector.ReplaceRules(rules, False)

        builder.AddChainset(collector, str(radius))
        builder.CommitFeature()
    finally:
        builder.Destroy()


# ---- Proven helper: chamfer (from create_chamfered_cylinder_bottom_blend_part.py)

def chamfer(work_part, body, offset):
    """
    Apply a symmetric chamfer of given offset to all edges of the body.
    """
    edges = list(body.GetEdges())
    if not edges:
        return

    builder = work_part.Features.CreateChamferBuilder(
        NXOpen.Features.Feature.Null
    )
    try:
        builder.Option     = NXOpen.Features.ChamferBuilder.ChamferOption.OffsetAndAngle
        builder.Method     = NXOpen.Features.ChamferBuilder.OffsetMethod.EdgesAlongFaces
        builder.FirstOffset  = str(offset)
        builder.SecondOffset = str(offset)
        builder.Angle      = "45"
        builder.Tolerance  = 0.01

        rules = [
            work_part.ScRuleFactory.CreateRuleEdgeTangent(
                edge, NXOpen.Edge.Null, False, 0.5, False
            )
            for edge in edges
        ]
        collector = work_part.ScCollectors.CreateCollector()
        collector.ReplaceRules(rules, False)
        builder.SmartCollector = collector
        builder.CommitFeature()
    finally:
        builder.Destroy()


# ---- Pulley hub build steps --------------------------------------------------

def step1_main_body(wp):
    """
    [Sketch XY + Revolve 360 deg]
    Hub cross-section revolved = two united coaxial cylinders (Z axis):
      A) Barrel:  OD=HUB_OD,   L=BARREL_LENGTH  (z=0..43)
      B) Flange:  OD=FLANGE_OD, L=FLANGE_THICKNESS (z=43..55)
    """
    z_up = NXOpen.Vector3d(0.0, 0.0, 1.0)

    # A) Hub barrel
    barrel_body = create_cylinder(
        wp,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        z_up,
        str(HUB_OD),
        str(BARREL_LENGTH),
    )

    # B) Flange ring on top of barrel
    flange_body = create_cylinder(
        wp,
        NXOpen.Point3d(0.0, 0.0, BARREL_LENGTH),
        z_up,
        str(FLANGE_OD),
        str(FLANGE_THICKNESS),
    )

    # Unite flange into barrel
    unite(wp, barrel_body, flange_body)

    return barrel_body


def step2_bore(wp, hub_body):
    """
    [Hole command: central bore Ø HUB_ID, through-all along Z]
    """
    z_up       = NXOpen.Vector3d(0.0, 0.0, 1.0)
    bore_depth = HUB_LENGTH + BOSS_HEIGHT + 10.0   # guaranteed through-all

    bore_body = create_cylinder(
        wp,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        z_up,
        str(HUB_ID),
        str(bore_depth),
    )
    subtract(wp, hub_body, bore_body)


def step3_boss(wp, hub_body):
    """
    [Extrude: boss circle on flange top face extruded +BOSS_HEIGHT]
    """
    z_up = NXOpen.Vector3d(0.0, 0.0, 1.0)

    boss_body = create_cylinder(
        wp,
        NXOpen.Point3d(0.0, 0.0, HUB_LENGTH),
        z_up,
        str(BOSS_OD),
        str(BOSS_HEIGHT),
    )
    unite(wp, hub_body, boss_body)


def step4_bolt_holes(wp, hub_body):
    """
    [Hole command + Pattern Feature Circular 4x]
    Four equally-spaced Ø BOLT_DIA holes drilled into the flange top face,
    at BCD radius, through the flange thickness.
    """
    z_up      = NXOpen.Vector3d(0.0, 0.0, 1.0)
    bcd_r     = BCD / 2.0
    hole_top  = HUB_LENGTH + 1.0          # start 1 mm above flange face
    hole_h    = FLANGE_THICKNESS + 2.0    # punch fully through flange

    for i in range(BOLT_COUNT):
        angle_rad = math.radians(i * (360.0 / BOLT_COUNT))
        cx = bcd_r * math.cos(angle_rad)
        cy = bcd_r * math.sin(angle_rad)

        # i==0 = NX feature "Cylinder (7)" — make it dramatically smaller
        dia = BOLT_DIA_SMALL if i == 0 else BOLT_DIA

        hole_body = create_cylinder(
            wp,
            NXOpen.Point3d(cx, cy, hole_top - hole_h),
            z_up,
            str(dia),
            str(hole_h),
        )
        subtract(wp, hub_body, hole_body)


def step5_keyway(wp, hub_body):
    """
    [Sketch (XZ plane) + Extrude Remove: keyway KEY_WIDTH x KEY_DEPTH x full length]
    A rectangular block is subtracted from the bore on the +Y side.

    Block layout (WCS):
      corner X = -KEY_WIDTH/2 = -4
      corner Y = +HUB_RADIUS  = +14  (bore inner surface)
      corner Z = -0.5          (small over-cut below bottom face)
      Width (X) = KEY_WIDTH = 8
      Depth (Y) = KEY_DEPTH + HUB_RADIUS (over-cut above bore centre: 4+14=18)
      Height (Z) = HUB_LENGTH + BOSS_HEIGHT + 1 (full length through-all: 64)
    """
    over_top    = HUB_RADIUS              # extra Y so block clears bore centre
    block_width = KEY_DEPTH + over_top    # Y extent: 14+4 = 18 (over-cuts)
    block_depth = HUB_LENGTH + BOSS_HEIGHT + 1.0  # Z through-all

    corner = NXOpen.Point3d(
        -(KEY_WIDTH / 2.0),  # X
        HUB_RADIUS,          # Y (at bore inner surface)
        -0.5,                # Z (below bottom face)
    )

    key_body = create_block(
        wp,
        corner,
        length_str=str(KEY_WIDTH),    # X
        width_str=str(block_width),   # Y
        height_str=str(block_depth),  # Z
    )
    subtract(wp, hub_body, key_body)


def step6_edge_blend(wp, uf_session, hub_body):
    """
    [Edge Blend R=BLEND_R on all step-transition edges]
    """
    edge_blend(wp, uf_session, hub_body, BLEND_R)


def step7_chamfer(wp, hub_body):
    """
    [Chamfer CHAMFER_OFF mm on hole-entrance edges]
    """
    chamfer(wp, hub_body, CHAMFER_OFF)


def step8_mirror_keyway(wp, hub_body):
    """
    [Mirror Feature about XZ plane: second keyway at 180 deg (-Y side)]
    Dual-key configuration for heavy-torque applications.

    Block layout (WCS, mirror of step5):
      corner X = -KEY_WIDTH/2 = -4
      corner Y = -(HUB_RADIUS + KEY_DEPTH + HUB_RADIUS) = -(HUB_RADIUS + KEY_DEPTH) ... from -Y side
      corner Z = -0.5
    """
    over_top    = HUB_RADIUS
    block_width = KEY_DEPTH + over_top
    block_depth = HUB_LENGTH + BOSS_HEIGHT + 1.0

    # -Y side: corner is at -(HUB_RADIUS + KEY_DEPTH), extends in +Y by block_width
    corner = NXOpen.Point3d(
        -(KEY_WIDTH / 2.0),
        -(HUB_RADIUS + KEY_DEPTH),   # lower Y edge of mirrored slot
        -0.5,
    )

    key2_body = create_block(
        wp,
        corner,
        length_str=str(KEY_WIDTH),
        width_str=str(block_width),
        height_str=str(block_depth),
    )
    subtract(wp, hub_body, key2_body)


# ---- Main --------------------------------------------------------------------

def main():
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists():
        try:
            OUTPUT_PATH.unlink()
        except Exception:
            pass

    session    = NXOpen.Session.GetSession()
    uf_session = NXOpen.UF.UFSession.GetUFSession()
    
    # Check if the part is already open in the session and close it
    try:
        for p in session.Parts:
            if p.FullPath.lower() == str(OUTPUT_PATH).lower():
                p.Close(NXOpen.BasePart.CloseWholeTree.TrueValue, NXOpen.BasePart.KeepTransient.FalseValue, None)
                break
    except Exception:
        pass

    session.Parts.NewDisplay(str(OUTPUT_PATH), NXOpen.Part.Units.Millimeters)
    wp = session.Parts.Work

    # Named expressions
    exprs = [
        ("HUB_OD",           HUB_OD),
        ("HUB_ID",           HUB_ID),
        ("HUB_LENGTH",       HUB_LENGTH),
        ("FLANGE_OD",        FLANGE_OD),
        ("FLANGE_THICKNESS", FLANGE_THICKNESS),
        ("BOSS_OD",          BOSS_OD),
        ("BOSS_HEIGHT",      BOSS_HEIGHT),
        ("BCD",              BCD),
        ("BOLT_DIA",         BOLT_DIA),
        ("BOLT_COUNT",       float(BOLT_COUNT)),
        ("KEY_WIDTH",        KEY_WIDTH),
        ("KEY_DEPTH",        KEY_DEPTH),
        ("BLEND_R",          BLEND_R),
        ("CHAMFER_OFF",      CHAMFER_OFF),
        ("BARREL_LENGTH",    BARREL_LENGTH),
        ("HUB_RADIUS",       HUB_RADIUS),
    ]
    for name, val in exprs:
        wp.Expressions.CreateExpression("Number", "{} = {}".format(name, val))

    hub_body = None

    # Step 1 — Main body (Sketch XY + Revolve 360 deg)
    try:
        hub_body = step1_main_body(wp)
    except Exception as e:
        raise RuntimeError("Step 1 Main body failed: " + str(e))

    # Step 2 — Central bore (Hole command)
    try:
        step2_bore(wp, hub_body)
    except Exception:
        pass

    # Step 3 — Mounting boss (Extrude + Unite)
    try:
        step3_boss(wp, hub_body)
    except Exception:
        pass

    # Step 4 — Bolt holes + Pattern Feature Circular
    try:
        step4_bolt_holes(wp, hub_body)
    except Exception:
        pass

    # Step 5 — Keyway (Sketch XZ + Extrude Remove)
    try:
        step5_keyway(wp, hub_body)
    except Exception:
        pass

    # Step 6 — Edge Blend R2
    try:
        step6_edge_blend(wp, uf_session, hub_body)
    except Exception:
        pass

    # Step 7 — Chamfer 1 mm
    try:
        step7_chamfer(wp, hub_body)
    except Exception:
        pass

    # Step 8 — Mirror Feature (second keyway)
    try:
        step8_mirror_keyway(wp, hub_body)
    except Exception:
        pass

    # Fit view + save
    wp.ModelingViews.WorkView.Fit()
    wp.Save(
        NXOpen.BasePart.SaveComponents.TrueValue,
        NXOpen.BasePart.CloseAfterSave.TrueValue,
    )


if __name__ == "__main__":
    main()
