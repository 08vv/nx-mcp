"""
create_clevis_mount_bracket_part.py
====================================
NX Journal that creates a parametric clevis mount bracket.
All dimensions and coordinates are stored as named NX Expressions.
Uses Sketch and Extrude features matching the exact build order.
"""

import sys
import os
import math
from pathlib import Path

# Support running in mock mode for local testing
if os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1":
    project_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(project_root / "src"))
    import nx_mcp.testing.mock_nxopen as NXOpen
    from unittest.mock import MagicMock
    class MockExpression:
        def __init__(self, name, formula):
            self.Name = name
            self.RightHandSide = formula
            self.Value = 1.0  # mock numeric value
            try:
                # Try evaluating simple numbers
                self.Value = float(formula)
            except Exception:
                pass
    class MockExpressionsCollection:
        def __init__(self):
            self._exprs = {}
        def CreateExpression(self, type_str, expr_str):
            name, formula = expr_str.split("=", 1)
            name = name.strip()
            formula = formula.strip()
            self._exprs[name] = MockExpression(name, formula)
        def FindObject(self, name):
            if name in self._exprs:
                return self._exprs[name]
            mock_expr = MagicMock()
            mock_expr.Value = 1.0
            return mock_expr
        def __iter__(self):
            return iter(self._exprs.values())
    
    orig_init = NXOpen._WorkPart.__init__
    def patched_init(self):
        orig_init(self)
        self.Expressions = MockExpressionsCollection()
        self.Planes = MagicMock()
        self.Points = MagicMock()
        self.Sections = MagicMock()
        self.ScRuleFactory = MagicMock()
        self.Directions = MagicMock()
        self.CoordinateSystems = MagicMock()
        self.NXMatrices = MagicMock()
        self.Scalars = MagicMock()
        self.WCS = MagicMock()
        self.ModelingViews = MagicMock()
        self.Save = MagicMock()
    NXOpen._WorkPart.__init__ = patched_init

    NXOpen.SmartObject = MagicMock()
    NXOpen.SketchDimensionOption = MagicMock()
    NXOpen.Sketch = MagicMock()
    NXOpen.BasePart = MagicMock()
    NXOpen.SketchConstraintPointType = MagicMock()
    NXOpen.SketchAssocType = MagicMock()
    NXOpen.SketchConstraintType = MagicMock()
    NXOpen.GeometricUtilities = MagicMock()
    NXOpen.NXObject = MagicMock()
    NXOpen.Section = MagicMock()
    NXOpen.Features = MagicMock()
    NXOpen.Matrix3x3 = MagicMock
    NXOpen.Scalar = MagicMock()

    class MockUFSession:
        @staticmethod
        def GetUFSession():
            mock_uf = MagicMock()
            call_count = [0]
            def ask_face_data_mock(face_tag):
                call_count[0] += 1
                cnt = call_count[0]
                if cnt == 1:
                    return (1, [0.0, -20.0, 5.0], [0.0, -1.0, 0.0], [0,0,0,0,0,0], 0.0, False, False)
                elif cnt == 2:
                    return (1, [0.0, 20.0, 5.0], [0.0, 1.0, 0.0], [0,0,0,0,0,0], 0.0, False, False)
                elif cnt == 3:
                    return (1, [0.0, -20.0, 5.0], [0.0, -1.0, 0.0], [0,0,0,0,0,0], 0.0, False, False)
                elif cnt == 4:
                    return (1, [0.0, 20.0, 5.0], [0.0, 1.0, 0.0], [0,0,0,0,0,0], 0.0, False, False)
                elif cnt == 5:
                    return (1, [-25.0, 0.0, 32.5], [-1.0, 0.0, -0.1], [0,0,0,0,0,0], 0.0, False, False)
                else:
                    return (1, [25.0, 0.0, 32.5], [1.0, 0.0, -0.1], [0,0,0,0,0,0], 0.0, False, False)
            mock_uf.Modeling.AskFaceData = ask_face_data_mock
            return mock_uf
    class MockUF:
        UFSession = MockUFSession
    NXOpen.UF = MockUF
else:
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


# Helpers for sketch constraints
def _dim_geom(curve, assoc_type=None):
    geom = NXOpen.Sketch.DimensionGeometry()
    geom.Geometry = curve
    if assoc_type is None:
        assoc_type = NXOpen.SketchAssocType.NotSet
    geom.AssocType = assoc_type
    return geom


def _con_geom(curve, point_type=None):
    geom = NXOpen.Sketch.ConstraintGeometry()
    geom.Geometry = curve
    if point_type is None:
        point_type = NXOpen.SketchConstraintPointType.NotSet
    geom.PointType = point_type
    return geom


def _apply_dim(sketch, dim_type, geom1, geom2, origin, expr):
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
    factory2 = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder2", None)
    builder = None
    if factory2 is not None:
        try:
            builder = factory2(None)
        except Exception as e:
            print("[INFO] CreateSketchInPlaceBuilder2 failed: {}. Falling back to CreateNewSketchInPlaceBuilder.".format(e))
    if builder is None:
        factory = getattr(work_part.Sketches, "CreateNewSketchInPlaceBuilder", None)
        if factory is None:
            factory = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder", None)
        builder = factory(None)
    try:
        for attr in ("PlaneOrFace", "PlaneReference", "PlacementFace"):
            if hasattr(builder, attr):
                try:
                    setattr(builder, attr, plane_obj)
                    break
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


def _create_sketch_on_csys(work_part, origin, x_vec, y_vec, z_vec, sketch_name):
    matrix = NXOpen.Matrix3x3()
    matrix.Xx = x_vec.X; matrix.Xy = x_vec.Y; matrix.Xz = x_vec.Z
    matrix.Yx = y_vec.X; matrix.Yy = y_vec.Y; matrix.Yz = y_vec.Z
    matrix.Zx = z_vec.X; matrix.Zy = z_vec.Y; matrix.Zz = z_vec.Z
    
    nx_matrix = work_part.NXMatrices.Create(matrix)
    csys = work_part.CoordinateSystems.CreateCoordinateSystem(origin, nx_matrix, True)

    factory2 = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder2", None)
    builder = None
    if factory2 is not None:
        try:
            builder = factory2(None)
        except Exception as e:
            print("[INFO] CreateSketchInPlaceBuilder2 failed: {}. Falling back to CreateNewSketchInPlaceBuilder.".format(e))
    if builder is None:
        factory = getattr(work_part.Sketches, "CreateNewSketchInPlaceBuilder", None)
        if factory is None:
            factory = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder", None)
        builder = factory(None)
    try:
        builder.Csystem = csys
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


def _extrude_curves(work_part, curves, dir_vec, start_expr, end_expr, feature_name, boolean_type=None, target_body=None):
    if boolean_type is None:
        try:
            boolean_type = NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
        except AttributeError:
            boolean_type = "Create"

    section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
    rules = [work_part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    section.AddToSection(
        rules, curves[0],
        NXOpen.NXObject.Null, NXOpen.NXObject.Null,
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Section.Mode.Create, False)

    builder = work_part.Features.CreateExtrudeBuilder(NXOpen.Features.Feature.Null)
    try:
        builder.Section = section
        nx_dir = work_part.Directions.CreateDirection(
            NXOpen.Point3d(0.0, 0.0, 0.0),
            dir_vec,
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        builder.Direction = nx_dir
        builder.Limits.StartExtend.Value.RightHandSide = start_expr
        builder.Limits.EndExtend.Value.RightHandSide = end_expr
        
        if target_body is not None:
            builder.BooleanOperation.SetBooleanOperationAndBody(boolean_type, target_body)
        else:
            builder.BooleanOperation.Type = boolean_type
            
        feat = builder.CommitFeature()
    finally:
        builder.Destroy()
    try:
        feat.SetName(feature_name)
    except Exception:
        pass
    body = feat.GetBodies()[0]
    if os.environ.get("NX_MCP_USE_MOCK_NXOPEN") == "1":
        from unittest.mock import MagicMock
        body.GetFaces = MagicMock(return_value=[MagicMock(Tag=1), MagicMock(Tag=2)])
    return feat, body


def _create_parametric_point(work_part, x_name, y_name, z_name):
    expr_x = work_part.Expressions.FindObject(x_name)
    expr_y = work_part.Expressions.FindObject(y_name)
    expr_z = work_part.Expressions.FindObject(z_name)
    
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
    return work_part.Points.CreatePoint(
        csys, x_scalar, y_scalar, z_scalar,
        NXOpen.SmartObject.UpdateOption.WithinModeling,
    )


def _add_hole_feature(work_part, target_body, x_expr, y_expr, z_expr, dir_vec, dia_expr_name, depth_expr_name, feature_name):
    point = _create_parametric_point(work_part, x_expr, y_expr, z_expr)
    
    # Try using HoleBuilder
    builder_factory = getattr(work_part.Features, "CreateHoleBuilder", None)
    if callable(builder_factory):
        builder = builder_factory(NXOpen.Features.Feature.Null)
        try:
            for attr in ("Type", "HoleType"):
                if hasattr(builder, attr):
                    try:
                        type_enum = getattr(builder, attr + "s", None) or getattr(builder, attr)
                        simple = getattr(type_enum, "Simple", getattr(type_enum, "GeneralHole", None))
                        if simple is not None:
                            setattr(builder, attr, simple)
                        break
                    except Exception:
                        pass
            
            builder.Diameter.RightHandSide = dia_expr_name
            for depth_attr in ("Depth", "HoleDepth", "TipDepth"):
                if hasattr(builder, depth_attr):
                    try:
                        getattr(builder, depth_attr).RightHandSide = depth_expr_name
                        break
                    except Exception:
                        pass
            
            if hasattr(builder, "Position"):
                try:
                    builder.Position = point
                except Exception:
                    pass
            if hasattr(builder, "Direction"):
                try:
                    nx_dir = work_part.Directions.CreateDirection(
                        point, dir_vec,
                        NXOpen.SmartObject.UpdateOption.WithinModeling)
                    builder.Direction = nx_dir
                except Exception:
                    pass
            for attr in ("Target", "TargetBody", "BooleanOperation"):
                if hasattr(builder, attr):
                    try:
                        setattr(builder, attr, target_body)
                        break
                    except Exception:
                        pass
            feat = builder.CommitFeature()
            try:
                feat.SetName(feature_name)
            except Exception:
                pass
            return feat, target_body
        except Exception as e:
            print("[WARN] HoleBuilder failed, falling back to cylinder-subtract: {}".format(e))
        finally:
            builder.Destroy()
            
    # Fallback to cylinder subtract
    cyl_builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    try:
        nx_dir = work_part.Directions.CreateDirection(
            point.Coordinates, dir_vec,
            NXOpen.SmartObject.UpdateOption.WithinModeling)
        cyl_builder.Diameter.RightHandSide = dia_expr_name
        cyl_builder.Height.RightHandSide = depth_expr_name
        cyl_builder.Axis.Point = point
        cyl_builder.Axis.Direction = nx_dir
        feat = cyl_builder.Commit()
        tool_body = feat.GetBodies()[0]
    finally:
        cyl_builder.Destroy()
        
    _perform_subtract(work_part, target_body, tool_body)
    return feat, target_body


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

    # 1. Register Expressions and Derived Formulas
    expressions = [
        ("BASE_WIDTH", "40.0"),
        ("BASE_THICK", "10.0"),
        ("WALL_HEIGHT", "45.0"),
        ("WALL_THICK", "10.0"),
        ("WALL_TOP_OFFSET", "4.0"),
        ("INNER_GAP", "30.0"),
        ("BOSS_DIA", "24.0"),
        ("BOSS_LENGTH", "12.0"),
        ("HOLE_DIA", "10.0"),
        
        # Formulas
        ("BASE_W_HALF", "BASE_WIDTH / 2.0"),
        ("GAP_HALF", "INNER_GAP / 2.0"),
        ("LEG_OUTER", "INNER_GAP / 2.0 + WALL_THICK"),
        ("WALL_H_HALF", "WALL_HEIGHT / 2.0"),
        
        ("L_WALL", "sqrt(WALL_HEIGHT^2 + WALL_TOP_OFFSET^2)"),
        ("NZ_X_L", "-WALL_HEIGHT / L_WALL"),
        ("NZ_Z_L", "-WALL_TOP_OFFSET / L_WALL"),
        ("NZ_X_R", "WALL_HEIGHT / L_WALL"),
        ("NZ_Z_R", "-WALL_TOP_OFFSET / L_WALL"),
        
        ("LEFT_BOSS_X", "-INNER_GAP / 2.0 - WALL_THICK - WALL_TOP_OFFSET / 2.0"),
        ("LEFT_BOSS_Y", "0.0"),
        ("LEFT_BOSS_Z", "BASE_THICK + WALL_HEIGHT / 2.0"),
        
        ("RIGHT_BOSS_X", "INNER_GAP / 2.0 + WALL_THICK + WALL_TOP_OFFSET / 2.0"),
        ("RIGHT_BOSS_Y", "0.0"),
        ("RIGHT_BOSS_Z", "BASE_THICK + WALL_HEIGHT / 2.0"),
        
        ("LEFT_HOLE_START_X", "LEFT_BOSS_X + NZ_X_L * BOSS_LENGTH"),
        ("LEFT_HOLE_START_Y", "0.0"),
        ("LEFT_HOLE_START_Z", "LEFT_BOSS_Z + NZ_Z_L * BOSS_LENGTH"),
        
        ("RIGHT_HOLE_START_X", "RIGHT_BOSS_X + NZ_X_R * BOSS_LENGTH"),
        ("RIGHT_HOLE_START_Y", "0.0"),
        ("RIGHT_HOLE_START_Z", "RIGHT_BOSS_Z + NZ_Z_R * BOSS_LENGTH"),
        
        ("HOLE_DEPTH", "BOSS_LENGTH + WALL_THICK + 5.0"),
    ]

    for name, formula in expressions:
        work_part.Expressions.CreateExpression("Number", f"{name} = {formula}")

    # 2. Base Sketch S1 on XY plane
    xy_plane = work_part.Planes.CreatePlane(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        NXOpen.SmartObject.UpdateOption.WithinModeling)

    feat_s1, sk1 = _create_sketch_on_plane(work_part, xy_plane, "S1_Base")
    sk1.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    leg_outer_val = work_part.Expressions.FindObject("LEG_OUTER").Value
    gap_half_val = work_part.Expressions.FindObject("GAP_HALF").Value
    base_w_half_val = work_part.Expressions.FindObject("BASE_W_HALF").Value
    wall_thick_val = work_part.Expressions.FindObject("WALL_THICK").Value
    
    p1 = NXOpen.Point3d(-leg_outer_val, -base_w_half_val, 0.0)
    p2 = NXOpen.Point3d(leg_outer_val, -base_w_half_val, 0.0)
    p3 = NXOpen.Point3d(leg_outer_val, base_w_half_val, 0.0)
    p4 = NXOpen.Point3d(gap_half_val, base_w_half_val, 0.0)
    p5 = NXOpen.Point3d(gap_half_val, -base_w_half_val + wall_thick_val, 0.0)
    p6 = NXOpen.Point3d(-gap_half_val, -base_w_half_val + wall_thick_val, 0.0)
    p7 = NXOpen.Point3d(-gap_half_val, base_w_half_val, 0.0)
    p8 = NXOpen.Point3d(-leg_outer_val, base_w_half_val, 0.0)

    l1 = work_part.Curves.CreateLine(p1, p2)
    l2 = work_part.Curves.CreateLine(p2, p3)
    l3 = work_part.Curves.CreateLine(p3, p4)
    l4 = work_part.Curves.CreateLine(p4, p5)
    l5 = work_part.Curves.CreateLine(p5, p6)
    l6 = work_part.Curves.CreateLine(p6, p7)
    l7 = work_part.Curves.CreateLine(p7, p8)
    l8 = work_part.Curves.CreateLine(p8, p1)

    infer = NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints
    for curve in (l1, l2, l3, l4, l5, l6, l7, l8):
        sk1.AddGeometry(curve, infer)

    # Geometric constraints
    sk1.CreateHorizontalConstraint(_con_geom(l1))
    sk1.CreateVerticalConstraint(_con_geom(l2))
    sk1.CreateHorizontalConstraint(_con_geom(l3))
    sk1.CreateVerticalConstraint(_con_geom(l4))
    sk1.CreateHorizontalConstraint(_con_geom(l5))
    sk1.CreateVerticalConstraint(_con_geom(l6))
    sk1.CreateHorizontalConstraint(_con_geom(l7))
    sk1.CreateVerticalConstraint(_con_geom(l8))

    # Center coincident with origin
    pt_origin = work_part.Points.CreatePoint(NXOpen.Point3d(0.0, 0.0, 0.0))
    sk1.AddGeometry(pt_origin, infer)
    sk1.CreateFixedConstraint(_con_geom(pt_origin))

    CT = NXOpen.SketchConstraintType
    
    # Horizontal dimension: origin to l8 -> LEG_OUTER
    _apply_dim(sk1, CT.HorizontalDim,
               _dim_geom(pt_origin),
               _dim_geom(l8, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(-leg_outer_val/2.0, -base_w_half_val - 5.0, 0.0),
               work_part.Expressions.FindObject("LEG_OUTER"))

    # Horizontal dimension: origin to l2 -> LEG_OUTER
    _apply_dim(sk1, CT.HorizontalDim,
               _dim_geom(pt_origin),
               _dim_geom(l2, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(leg_outer_val/2.0, -base_w_half_val - 5.0, 0.0),
               work_part.Expressions.FindObject("LEG_OUTER"))

    # Horizontal dimension: origin to l6 -> GAP_HALF
    _apply_dim(sk1, CT.HorizontalDim,
               _dim_geom(pt_origin),
               _dim_geom(l6, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(-gap_half_val/2.0, base_w_half_val/2.0, 0.0),
               work_part.Expressions.FindObject("GAP_HALF"))

    # Horizontal dimension: origin to l4 -> GAP_HALF
    _apply_dim(sk1, CT.HorizontalDim,
               _dim_geom(pt_origin),
               _dim_geom(l4, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(gap_half_val/2.0, base_w_half_val/2.0, 0.0),
               work_part.Expressions.FindObject("GAP_HALF"))

    # Vertical dimension: origin to l1 -> BASE_W_HALF
    _apply_dim(sk1, CT.VerticalDim,
               _dim_geom(pt_origin),
               _dim_geom(l1, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(-leg_outer_val - 5.0, -base_w_half_val/2.0, 0.0),
               work_part.Expressions.FindObject("BASE_W_HALF"))

    # Vertical dimension: origin to l3 -> BASE_W_HALF
    _apply_dim(sk1, CT.VerticalDim,
               _dim_geom(pt_origin),
               _dim_geom(l3, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(-leg_outer_val - 5.0, base_w_half_val/2.0, 0.0),
               work_part.Expressions.FindObject("BASE_W_HALF"))

    # Vertical dimension: l1 to l5 -> WALL_THICK
    _apply_dim(sk1, CT.VerticalDim,
               _dim_geom(l1, NXOpen.SketchAssocType.StartPoint),
               _dim_geom(l5, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(0.0, -base_w_half_val + wall_thick_val/2.0, 0.0),
               work_part.Expressions.FindObject("WALL_THICK"))

    sk1.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # 3. Base block extrusion F4
    feat_f4, base_body = _extrude_curves(
        work_part, [l1, l2, l3, l4, l5, l6, l7, l8],
        NXOpen.Vector3d(0.0, 0.0, 1.0), "0.0", "BASE_THICK",
        "F4_Base_Extrude",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Create
    )

    # Find the face_min_y and face_max_y on F4
    base_faces = base_body.GetFaces()
    face_min_y = None
    face_max_y = None
    for face in base_faces:
        face_type, origin, direction, bbox, radius, flag1, flag2 = uf_session.Modeling.AskFaceData(face.Tag)
        if abs(direction[0]) < 0.001 and abs(direction[2]) < 0.001:
            if direction[1] < -0.9:
                face_min_y = face
            elif direction[1] > 0.9:
                face_max_y = face

    # 4. Sketch S2 (Left Wall) on face_min_y using coordinate system orientation
    face_type, origin_l, direction_l, bbox_l, radius_l, flag1_l, flag2_l = uf_session.Modeling.AskFaceData(face_min_y.Tag)
    y_coord = origin_l[1]
    print(f"S2 Face Y-coordinate: {y_coord}")

    feat_s2, sk2 = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, y_coord, 0.0),
        NXOpen.Vector3d(1.0, 0.0, 0.0),  # local X
        NXOpen.Vector3d(0.0, 0.0, 1.0),  # local Y
        NXOpen.Vector3d(0.0, -1.0, 0.0), # local Z (normal)
        "S2_Left_Wall"
    )
    sk2.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    thick_val = work_part.Expressions.FindObject("BASE_THICK").Value
    height_val = work_part.Expressions.FindObject("WALL_HEIGHT").Value
    wall_thick_val = work_part.Expressions.FindObject("WALL_THICK").Value
    gap_val = work_part.Expressions.FindObject("INNER_GAP").Value
    offset_val = work_part.Expressions.FindObject("WALL_TOP_OFFSET").Value

    p1 = NXOpen.Point3d(-gap_val/2.0 - wall_thick_val, y_coord, thick_val)
    p2 = NXOpen.Point3d(-gap_val/2.0, y_coord, thick_val)
    p3 = NXOpen.Point3d(-gap_val/2.0 - offset_val, y_coord, thick_val + height_val)
    p4 = NXOpen.Point3d(-gap_val/2.0 - wall_thick_val - offset_val, y_coord, thick_val + height_val)

    l1 = work_part.Curves.CreateLine(p1, p2)
    l2 = work_part.Curves.CreateLine(p2, p3)
    l3 = work_part.Curves.CreateLine(p3, p4)
    l4 = work_part.Curves.CreateLine(p4, p1)

    for curve in (l1, l2, l3, l4):
        sk2.AddGeometry(curve, infer)

    # Geometric constraints
    sk2.CreateHorizontalConstraint(_con_geom(l1))
    sk2.CreateHorizontalConstraint(_con_geom(l3))

    pt_ref = work_part.Points.CreatePoint(NXOpen.Point3d(0.0, y_coord, 0.0))
    sk2.AddGeometry(pt_ref, infer)
    sk2.CreateFixedConstraint(_con_geom(pt_ref))

    # Dimensional constraints:
    # Height of l1 from origin -> BASE_THICK
    _apply_dim(sk2, CT.VerticalDim,
               _dim_geom(pt_ref),
               _dim_geom(l1, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(-gap_val/2.0, y_coord, thick_val/2.0),
               work_part.Expressions.FindObject("BASE_THICK"))

    # X distance of p2 from origin -> GAP_HALF
    _apply_dim(sk2, CT.HorizontalDim,
               _dim_geom(pt_ref),
               _dim_geom(l2, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(-gap_val/4.0, y_coord, thick_val + 5.0),
               work_part.Expressions.FindObject("GAP_HALF"))

    # Horizontal width of bottom edge l1 -> WALL_THICK
    _apply_dim(sk2, CT.HorizontalDim,
               _dim_geom(l1, NXOpen.SketchAssocType.StartPoint),
               _dim_geom(l1, NXOpen.SketchAssocType.EndPoint),
               NXOpen.Point3d(-gap_val/2.0 - wall_thick_val/2.0, y_coord, thick_val - 5.0),
               work_part.Expressions.FindObject("WALL_THICK"))

    # Horizontal width of top edge l3 -> WALL_THICK
    _apply_dim(sk2, CT.HorizontalDim,
               _dim_geom(l3, NXOpen.SketchAssocType.StartPoint),
               _dim_geom(l3, NXOpen.SketchAssocType.EndPoint),
               NXOpen.Point3d(-gap_val/2.0 - offset_val - wall_thick_val/2.0, y_coord, thick_val + height_val + 5.0),
               work_part.Expressions.FindObject("WALL_THICK"))

    # Height of wall -> WALL_HEIGHT
    _apply_dim(sk2, CT.VerticalDim,
               _dim_geom(l1, NXOpen.SketchAssocType.StartPoint),
               _dim_geom(l3, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(-gap_val/2.0 - wall_thick_val - offset_val - 10.0, y_coord, thick_val + height_val/2.0),
               work_part.Expressions.FindObject("WALL_HEIGHT"))

    # Offset distance: horizontal distance from p2 to p3 -> WALL_TOP_OFFSET
    _apply_dim(sk2, CT.HorizontalDim,
               _dim_geom(l2, NXOpen.SketchAssocType.StartPoint),
               _dim_geom(l2, NXOpen.SketchAssocType.EndPoint),
               NXOpen.Point3d(-gap_val/2.0 - offset_val/2.0, y_coord, thick_val + height_val/2.0 + 10.0),
               work_part.Expressions.FindObject("WALL_TOP_OFFSET"))

    sk2.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # 5. Extrude Left Wall F7
    # Note: Sketch normal points along -Y, so we extrude in the +Y direction (start=0, end=BASE_WIDTH)
    feat_f7, left_wall_body = _extrude_curves(
        work_part, [l1, l2, l3, l4],
        NXOpen.Vector3d(0.0, 1.0, 0.0), "0.0", "BASE_WIDTH",
        "F7_Left_Wall_Extrude",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        base_body
    )

    # 6. Sketch S3 (Right Wall) on face_max_y using coordinate system orientation
    face_type, origin_r, direction_r, bbox_r, radius_r, flag1_r, flag2_r = uf_session.Modeling.AskFaceData(face_max_y.Tag)
    y_coord_max = origin_r[1]
    print(f"S3 Face Y-coordinate: {y_coord_max}")

    feat_s3, sk3 = _create_sketch_on_csys(
        work_part,
        NXOpen.Point3d(0.0, y_coord_max, 0.0),
        NXOpen.Vector3d(-1.0, 0.0, 0.0), # local X
        NXOpen.Vector3d(0.0, 0.0, 1.0),  # local Y
        NXOpen.Vector3d(0.0, 1.0, 0.0),  # local Z (normal)
        "S3_Right_Wall"
    )
    sk3.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    p1_r = NXOpen.Point3d(gap_val/2.0, y_coord_max, thick_val)
    p2_r = NXOpen.Point3d(gap_val/2.0 + wall_thick_val, y_coord_max, thick_val)
    p3_r = NXOpen.Point3d(gap_val/2.0 + wall_thick_val + offset_val, y_coord_max, thick_val + height_val)
    p4_r = NXOpen.Point3d(gap_val/2.0 + offset_val, y_coord_max, thick_val + height_val)

    l1_r = work_part.Curves.CreateLine(p1_r, p2_r)
    l2_r = work_part.Curves.CreateLine(p2_r, p3_r)
    l3_r = work_part.Curves.CreateLine(p3_r, p4_r)
    l4_r = work_part.Curves.CreateLine(p4_r, p1_r)

    for curve in (l1_r, l2_r, l3_r, l4_r):
        sk3.AddGeometry(curve, infer)

    # Geometric constraints
    sk3.CreateHorizontalConstraint(_con_geom(l1_r))
    sk3.CreateHorizontalConstraint(_con_geom(l3_r))

    pt_ref_r = work_part.Points.CreatePoint(NXOpen.Point3d(0.0, y_coord_max, 0.0))
    sk3.AddGeometry(pt_ref_r, infer)
    sk3.CreateFixedConstraint(_con_geom(pt_ref_r))

    # Dimensional constraints:
    # Height of l1_r from origin -> BASE_THICK
    _apply_dim(sk3, CT.VerticalDim,
               _dim_geom(pt_ref_r),
               _dim_geom(l1_r, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(gap_val/2.0, y_coord_max, thick_val/2.0),
               work_part.Expressions.FindObject("BASE_THICK"))

    # X distance of p1_r from origin -> GAP_HALF
    _apply_dim(sk3, CT.HorizontalDim,
               _dim_geom(pt_ref_r),
               _dim_geom(l4_r, NXOpen.SketchAssocType.EndPoint),
               NXOpen.Point3d(gap_val/4.0, y_coord_max, thick_val + 5.0),
               work_part.Expressions.FindObject("GAP_HALF"))

    # Horizontal width of bottom edge l1_r -> WALL_THICK
    _apply_dim(sk3, CT.HorizontalDim,
               _dim_geom(l1_r, NXOpen.SketchAssocType.StartPoint),
               _dim_geom(l1_r, NXOpen.SketchAssocType.EndPoint),
               NXOpen.Point3d(gap_val/2.0 + wall_thick_val/2.0, y_coord_max, thick_val - 5.0),
               work_part.Expressions.FindObject("WALL_THICK"))

    # Horizontal width of top edge l3_r -> WALL_THICK
    _apply_dim(sk3, CT.HorizontalDim,
               _dim_geom(l3_r, NXOpen.SketchAssocType.StartPoint),
               _dim_geom(l3_r, NXOpen.SketchAssocType.EndPoint),
               NXOpen.Point3d(gap_val/2.0 + offset_val + wall_thick_val/2.0, y_coord_max, thick_val + height_val + 5.0),
               work_part.Expressions.FindObject("WALL_THICK"))

    # Height of wall -> WALL_HEIGHT
    _apply_dim(sk3, CT.VerticalDim,
               _dim_geom(l1_r, NXOpen.SketchAssocType.StartPoint),
               _dim_geom(l3_r, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(gap_val/2.0 + wall_thick_val + offset_val + 10.0, y_coord_max, thick_val + height_val/2.0),
               work_part.Expressions.FindObject("WALL_HEIGHT"))

    # Offset distance: horizontal distance from p1_r to p4_r -> WALL_TOP_OFFSET
    _apply_dim(sk3, CT.HorizontalDim,
               _dim_geom(l4_r, NXOpen.SketchAssocType.EndPoint),
               _dim_geom(l4_r, NXOpen.SketchAssocType.StartPoint),
               NXOpen.Point3d(gap_val/2.0 + offset_val/2.0, y_coord_max, thick_val + height_val/2.0 + 10.0),
               work_part.Expressions.FindObject("WALL_TOP_OFFSET"))

    sk3.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # 7. Extrude Right Wall F10
    # Note: Sketch normal points along +Y, so we extrude in the -Y direction (start=0, end=BASE_WIDTH)
    feat_f10, main_body = _extrude_curves(
        work_part, [l1_r, l2_r, l3_r, l4_r],
        NXOpen.Vector3d(0.0, -1.0, 0.0), "0.0", "BASE_WIDTH",
        "F10_Right_Wall_Extrude",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        left_wall_body
    )

    # Find outer faces of Left and Right walls on main_body
    faces = main_body.GetFaces()
    face_outer_left = None
    face_outer_right = None
    for face in faces:
        face_type, origin, direction, bbox, radius, flag1, flag2 = uf_session.Modeling.AskFaceData(face.Tag)
        if abs(direction[1]) < 0.001:
            # Inclined outer faces point left/right (X) and slightly down (-Z)
            if direction[0] < -0.05 and direction[2] < -0.05:
                if origin[0] < 0:
                    face_outer_left = face
            elif direction[0] > 0.05 and direction[2] < -0.05:
                if origin[0] > 0:
                    face_outer_right = face

    # 8. Sketch S4 (Left Boss) on face_outer_left
    face_type, origin_l, direction_l, bbox_l, radius_l, flag1_l, flag2_l = uf_session.Modeling.AskFaceData(face_outer_left.Tag)
    nz_x, nz_y, nz_z = direction_l
    
    z_center_val = thick_val + height_val / 2.0
    x_center_val = origin_l[0] - (z_center_val - origin_l[2]) * nz_z / nz_x
    center_left = NXOpen.Point3d(x_center_val, 0.0, z_center_val)
    
    matrix_left = NXOpen.Matrix3x3()
    matrix_left.Xx = 0.0; matrix_left.Xy = 1.0; matrix_left.Xz = 0.0
    matrix_left.Yx = -nz_z; matrix_left.Yy = 0.0; matrix_left.Yz = nz_x
    matrix_left.Zx = nz_x; matrix_left.Zy = nz_y; matrix_left.Zz = nz_z
    nx_matrix_left = work_part.NXMatrices.Create(matrix_left)

    feat_s4, sk4 = _create_sketch_on_csys(
        work_part,
        center_left,
        NXOpen.Vector3d(0.0, 1.0, 0.0),       # local X
        NXOpen.Vector3d(-nz_z, 0.0, nz_x),    # local Y
        NXOpen.Vector3d(nz_x, 0.0, nz_z),     # local Z (normal)
        "S4_Left_Boss"
    )
    sk4.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    boss_r_val = work_part.Expressions.FindObject("BOSS_DIA").Value / 2.0
    circle_left = work_part.Curves.CreateArc(
        center_left, nx_matrix_left, boss_r_val, 0.0, 2.0 * math.pi
    )
    sk4.AddGeometry(circle_left, infer)

    pt_c_l = work_part.Points.CreatePoint(center_left)
    sk4.AddGeometry(pt_c_l, infer)
    sk4.CreateFixedConstraint(_con_geom(pt_c_l))

    _apply_dim(sk4, CT.DiameterDim,
               _dim_geom(circle_left), None,
               NXOpen.Point3d(x_center_val, boss_r_val + 2.0, z_center_val + boss_r_val + 2.0),
               work_part.Expressions.FindObject("BOSS_DIA"))

    sk4.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # 9. Extrude Left Boss F13
    feat_f13, main_body = _extrude_curves(
        work_part, [circle_left],
        NXOpen.Vector3d(nz_x, nz_y, nz_z), "0.0", "BOSS_LENGTH",
        "F13_Left_Boss_Extrude",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        main_body
    )

    # 10. Sketch S5 (Right Boss) on face_outer_right
    face_type, origin_r, direction_r, bbox_r, radius_r, flag1_r, flag2_r = uf_session.Modeling.AskFaceData(face_outer_right.Tag)
    nz_x_r, nz_y_r, nz_z_r = direction_r
    
    x_center_val_r = origin_r[0] - (z_center_val - origin_r[2]) * nz_z_r / nz_x_r
    center_right = NXOpen.Point3d(x_center_val_r, 0.0, z_center_val)
    
    matrix_right = NXOpen.Matrix3x3()
    matrix_right.Xx = 0.0; matrix_right.Xy = 1.0; matrix_right.Xz = 0.0
    matrix_right.Yx = -nz_z_r; matrix_right.Yy = 0.0; matrix_right.Yz = nz_x_r
    matrix_right.Zx = nz_x_r; matrix_right.Zy = nz_y_r; matrix_right.Zz = nz_z_r
    nx_matrix_right = work_part.NXMatrices.Create(matrix_right)

    feat_s5, sk5 = _create_sketch_on_csys(
        work_part,
        center_right,
        NXOpen.Vector3d(0.0, 1.0, 0.0),         # local X
        NXOpen.Vector3d(-nz_z_r, 0.0, nz_x_r),  # local Y
        NXOpen.Vector3d(nz_x_r, 0.0, nz_z_r),   # local Z (normal)
        "S5_Right_Boss"
    )
    sk5.Activate(NXOpen.Sketch.ViewReorient.TrueValue)

    circle_right = work_part.Curves.CreateArc(
        center_right, nx_matrix_right, boss_r_val, 0.0, 2.0 * math.pi
    )
    sk5.AddGeometry(circle_right, infer)

    pt_c_r = work_part.Points.CreatePoint(center_right)
    sk5.AddGeometry(pt_c_r, infer)
    sk5.CreateFixedConstraint(_con_geom(pt_c_r))

    _apply_dim(sk5, CT.DiameterDim,
               _dim_geom(circle_right), None,
               NXOpen.Point3d(x_center_val_r, boss_r_val + 2.0, z_center_val + boss_r_val + 2.0),
               work_part.Expressions.FindObject("BOSS_DIA"))

    sk5.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)

    # 11. Extrude Right Boss F16
    feat_f16, main_body = _extrude_curves(
        work_part, [circle_right],
        NXOpen.Vector3d(nz_x_r, nz_y_r, nz_z_r), "0.0", "BOSS_LENGTH",
        "F16_Right_Boss_Extrude",
        NXOpen.GeometricUtilities.BooleanOperation.BooleanType.Unite,
        main_body
    )

    # 12. Create Left Concentric Hole F17
    dir_left_hole = NXOpen.Vector3d(-nz_x, -nz_y, -nz_z)
    feat_f17, main_body = _add_hole_feature(
        work_part, main_body,
        "LEFT_HOLE_START_X", "LEFT_HOLE_START_Y", "LEFT_HOLE_START_Z",
        dir_left_hole, "HOLE_DIA", "HOLE_DEPTH", "F17_Left_Hole"
    )

    # 13. Create Right Concentric Hole F18
    dir_right_hole = NXOpen.Vector3d(-nz_x_r, -nz_y_r, -nz_z_r)
    feat_f18, main_body = _add_hole_feature(
        work_part, main_body,
        "RIGHT_HOLE_START_X", "RIGHT_HOLE_START_Y", "RIGHT_HOLE_START_Z",
        dir_right_hole, "HOLE_DIA", "HOLE_DEPTH", "F18_Right_Hole"
    )

    # 14. Fit View and Save F19
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
