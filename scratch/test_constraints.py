import NXOpen
import sys
from pathlib import Path

def main():
    output_path = Path(r"c:\Users\HP\nx-mcp\scratch\test_constraints.prt")
    if output_path.exists():
        try: output_path.unlink()
        except: pass
        
    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    
    # Create expression
    expr = work_part.Expressions.CreateExpression("Number", "MY_LEN = 120")
    expr_rad = work_part.Expressions.CreateExpression("Number", "MY_RAD = 15")
    
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
            except: pass
    feat = builder.Commit()
    sketch = feat.Sketch if hasattr(feat, "Sketch") else feat
    builder.Destroy()
    
    sketch.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    
    # Add horizontal line
    p1 = NXOpen.Point3d(0.0, 0.0, 0.0)
    p2 = NXOpen.Point3d(100.0, 0.0, 0.0)
    line = work_part.Curves.CreateLine(p1, p2)
    sketch.AddGeometry(line, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    
    # Add Arc
    center = NXOpen.Point3d(0.0, 0.0, 0.0)
    orientation = work_part.WCS.CoordinateSystem.Orientation
    import math
    arc = work_part.Curves.CreateArc(center, orientation, 15.0, math.radians(0.0), math.radians(180.0))
    sketch.AddGeometry(arc, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    
    # Geometric constraints
    # Create a horizontal constraint on the line
    geom_line = NXOpen.Sketch.ConstraintGeometry()
    geom_line.Geometry = line
    geom_line.PointType = NXOpen.SketchConstraintPointType.NotSet
    sketch.CreateHorizontalConstraint(geom_line)
    print("Horizontal constraint succeeded")
    
    # Try to dimension the line
    try:
        geom_dim1 = NXOpen.Sketch.DimensionGeometry()
        geom_dim1.Geometry = line
        geom_dim1.AssocType = NXOpen.SketchAssocType.StartPoint
        
        geom_dim2 = NXOpen.Sketch.DimensionGeometry()
        geom_dim2.Geometry = line
        geom_dim2.AssocType = NXOpen.SketchAssocType.EndPoint
        
        origin = NXOpen.Point3d(50.0, 10.0, 0.0)
        
        # We can call CreateHorizontalDim or CreateDimension
        print("Trying CreateDimension for HorizontalDim between StartPoint and EndPoint...")
        dim = sketch.CreateDimension(
            NXOpen.SketchConstraintType.HorizontalDim,
            geom_dim1,
            geom_dim2,
            origin,
            expr,
            NXOpen.SketchDimensionOption.CreateAsDriving
        )
        print("CreateDimension for horizontal dim succeeded")
    except Exception as e:
        print(f"CreateDimension for horizontal dim failed: {e}")
        
    # Try to dimension the arc radius
    try:
        geom_arc = NXOpen.Sketch.DimensionGeometry()
        geom_arc.Geometry = arc
        geom_arc.AssocType = NXOpen.SketchAssocType.NotSet
        
        empty_geom2 = NXOpen.Sketch.DimensionGeometry()
        origin_arc = NXOpen.Point3d(10.0, 10.0, 0.0)
        
        print("Trying CreateDimension for RadiusDim...")
        dim_r = sketch.CreateDimension(
            NXOpen.SketchConstraintType.RadiusDim,
            geom_arc,
            empty_geom2,
            origin_arc,
            expr_rad,
            NXOpen.SketchDimensionOption.CreateAsDriving
        )
        print("CreateDimension for RadiusDim succeeded")
    except Exception as e:
        print(f"CreateDimension for RadiusDim failed: {e}")
        
    # Try to dimension a full circle diameter
    try:
        # Create circle (full arc from 0 to 2*pi)
        circle = work_part.Curves.CreateArc(center, orientation, 6.0, 0.0, 2.0 * math.pi)
        sketch.AddGeometry(circle, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
        
        geom_circle = NXOpen.Sketch.DimensionGeometry()
        geom_circle.Geometry = circle
        geom_circle.AssocType = NXOpen.SketchAssocType.NotSet
        
        empty_geom3 = NXOpen.Sketch.DimensionGeometry()
        origin_circle = NXOpen.Point3d(-10.0, -10.0, 0.0)
        
        expr_dia = work_part.Expressions.CreateExpression("Number", "MY_DIA = 12")
        
        print("Trying CreateDimension for DiameterDim...")
        dim_d = sketch.CreateDimension(
            NXOpen.SketchConstraintType.DiameterDim,
            geom_circle,
            empty_geom3,
            origin_circle,
            expr_dia,
            NXOpen.SketchDimensionOption.CreateAsDriving
        )
        print("CreateDimension for DiameterDim succeeded")
    except Exception as e:
        print(f"CreateDimension for DiameterDim failed: {e}")
        
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    
    part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    print("Test complete and saved.")

if __name__ == "__main__":
    main()
