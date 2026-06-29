import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay("C:\\Users\\HP\\nx-mcp\\scratch\\temp_sketch_inspect.prt", NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    
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
            try:
                setattr(builder, attr, plane_obj)
                break
            except Exception:
                pass
    feat = builder.CommitFeature()
    sketch = feat.Sketch if hasattr(feat, "Sketch") else feat
    builder.Destroy()
    
    print("Instance methods on Sketch object containing Dimension or Constraint:")
    for name in dir(sketch):
        if "Dimension" in name or "Constraint" in name or "Limit" in name:
            print(f"  {name}")

if __name__ == "__main__":
    main()
