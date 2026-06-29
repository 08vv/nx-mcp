import NXOpen
import math
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay("C:\\Users\\HP\\nx-mcp\\scratch\\temp_auto_dim.prt", NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    
    # Define expressions
    work_part.Expressions.CreateExpression("Number", "Arm_Length = 120")
    work_part.Expressions.CreateExpression("Number", "Arm_Width = 30")
    work_part.Expressions.CreateExpression("Number", "End_Radius = 15")
    work_part.Expressions.CreateExpression("Number", "Arm_Hole_Diameter = 12")
    
    # Create sketch on XY plane
    plane_obj = work_part.Planes.CreatePlane(
        NXOpen.Point3d(0.0, 0.0, 0.0),
        NXOpen.Vector3d(0.0, 0.0, 1.0),
        NXOpen.SmartObject.UpdateOption.WithinModeling)
        
    factory = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder2", None)
    if factory is None:
        factory = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder", None)
    builder = factory(None)
    for attr in ("PlaneOrFace", "PlaneReference", "PlacementFace"):
        if hasattr(builder, attr):
            try: setattr(builder, attr, plane_obj); break
            except Exception: pass
    feat = builder.Commit()
    sketch = feat.Sketch if hasattr(feat, "Sketch") else feat
    builder.Destroy()
    
    # Activate sketch
    sketch.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    
    # Draw linkage arm curves
    # Dimensions: 120 x 30. Rounded left end (R15), concentric 12 hole.
    # Left center at (15, 0). Right end at X=120.
    p_tl = NXOpen.Point3d(15.0, 15.0, 0.0)
    p_tr = NXOpen.Point3d(120.0, 15.0, 0.0)
    p_br = NXOpen.Point3d(120.0, -15.0, 0.0)
    p_bl = NXOpen.Point3d(15.0, -15.0, 0.0)
    
    l_top = work_part.Curves.CreateLine(p_tl, p_tr)
    l_rt = work_part.Curves.CreateLine(p_tr, p_br)
    l_bot = work_part.Curves.CreateLine(p_br, p_bl)
    
    # Left arc
    center = NXOpen.Point3d(15.0, 0.0, 0.0)
    orientation = work_part.WCS.CoordinateSystem.Orientation
    # Arc from Y=-15 to Y=15 through X=0 (counterclockwise: 90 to 270 deg)
    l_arc = work_part.Curves.CreateArc(center, orientation, 15.0, math.radians(90.0), math.radians(270.0))
    
    # Concentric hole
    l_hole = work_part.Curves.CreateArc(center, orientation, 6.0, 0.0, 2.0 * math.pi)
    
    # Add to sketch
    sketch.AddGeometry(l_top, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    sketch.AddGeometry(l_rt, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    sketch.AddGeometry(l_bot, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    sketch.AddGeometry(l_arc, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    sketch.AddGeometry(l_hole, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    
    # Add geometric constraints
    def _c_geom(curve):
        g = NXOpen.Sketch.ConstraintGeometry()
        g.Geometry = curve
        g.PointType = getattr(NXOpen.Sketch.ConstraintPointType, "None_", getattr(NXOpen.Sketch.ConstraintPointType, "None", None))
        return g
        
    sketch.CreateHorizontalConstraint(_c_geom(l_top))
    sketch.CreateHorizontalConstraint(_c_geom(l_bot))
    sketch.CreateVerticalConstraint(_c_geom(l_rt))
    
    # Auto dimension
    print("Running RunAutoDimension...")
    sketch.RunAutoDimension()
    
    # Deactivate sketch
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    
    # Extrude
    curves = [l_top, l_rt, l_bot, l_arc, l_hole]
    section = work_part.Sections.CreateSection(0.0095, 0.01, 0.5)
    rules = [work_part.ScRuleFactory.CreateRuleCurveDumb([c]) for c in curves]
    section.AddToSection(rules, curves[0], NXOpen.NXObject.Null, NXOpen.NXObject.Null, NXOpen.Point3d(0.0, 0.0, 0.0), NXOpen.Section.Mode.Create, False)
    
    extrude_builder = work_part.Features.CreateExtrudeBuilder(None)
    extrude_builder.Section = section
    extrude_builder.Direction = work_part.Directions.CreateDirection(NXOpen.Point3d(0.0, 0.0, 0.0), z_axis, NXOpen.SmartObject.UpdateOption.WithinModeling)
    extrude_builder.Limits.StartExtend.Value.RightHandSide = "0.0"
    extrude_builder.Limits.EndExtend.Value.RightHandSide = "10.0"
    feat = extrude_builder.CommitFeature()
    extrude_builder.Destroy()
    
    print("Extrude succeeded!")
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print("Part saved.")

if __name__ == "__main__":
    main()
