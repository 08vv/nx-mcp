import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay("C:\\Users\\HP\\nx-mcp\\scratch\\temp_dim_test.prt", NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    
    # 1. Create expression
    expr = work_part.Expressions.CreateExpression("Number", "MY_VAL = 100")
    
    # 2. Create sketch on XY plane
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
    
    # 3. Add geometry to sketch
    sketch.Activate(NXOpen.Sketch.ViewReorient.TrueValue)
    
    p1 = NXOpen.Point3d(0.0, 0.0, 0.0)
    p2 = NXOpen.Point3d(100.0, 0.0, 0.0)
    line = work_part.Curves.CreateLine(p1, p2)
    sketch.AddGeometry(line, NXOpen.Sketch.InferConstraintsOption.InferCoincidentConstraints)
    
    # 4. Try to add horizontal constraint
    geom = NXOpen.Sketch.ConstraintGeometry()
    geom.Geometry = line
    none_type = getattr(NXOpen.Sketch.ConstraintPointType, "None_", None)
    if none_type is None:
        none_type = getattr(NXOpen.Sketch.ConstraintPointType, "None")
    geom.PointType = none_type
    
    sketch.CreateHorizontalConstraint(geom)
    
    # 5. Try to add dimensional constraint (horizontal dimension)
    print("Trying CreateDimension...")
    try:
        # Define geometry for dimension (just the line itself or endpoints)
        dim_geom1 = NXOpen.Sketch.DimensionGeometry()
        dim_geom1.Geometry = line
        dim_geom1.PointType = none_type
        
        # In NX, vertical/horizontal dim can be between start and end of line
        dim_geom2 = NXOpen.Sketch.DimensionGeometry()
        
        origin = NXOpen.Point3d(50.0, 10.0, 0.0)
        
        dim_opt = getattr(NXOpen.Sketch.DimensionOption, "CreateAsAutomatic", None)
        if dim_opt is None:
            dim_opt = getattr(NXOpen.Sketch.DimensionOption, "Automatic", None)
            
        dim = sketch.CreateDimension(
            NXOpen.Sketch.ConstraintType.HorizontalDim,
            dim_geom1,
            dim_geom2,
            origin,
            expr,
            dim_opt
        )
        print("CreateDimension succeeded!")
    except Exception as e:
        print(f"CreateDimension failed: {e}")
        
    sketch.Deactivate(NXOpen.Sketch.ViewReorient.TrueValue, NXOpen.Sketch.UpdateLevel.Model)
    print("Done")

if __name__ == "__main__":
    main()
