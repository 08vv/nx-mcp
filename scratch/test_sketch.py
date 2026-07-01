import NXOpen
import NXOpen.UF

def main():
    session = NXOpen.Session.GetSession()
    work_part = session.Parts.Work
    if work_part is None:
        work_part = session.Parts.NewDisplay("C:/Users/HP/nx-mcp/scratch/temp.prt", NXOpen.Part.Units.Millimeters)

    y_coord = -20.0
    
    # Create point object for sketch origin
    pt_s2 = work_part.Points.CreatePoint(NXOpen.Point3d(0.0, y_coord, 0.0))
    
    # Orientation matrix
    matrix = NXOpen.Matrix3x3()
    matrix.Xx = 1.0; matrix.Xy = 0.0; matrix.Xz = 0.0
    matrix.Yx = 0.0; matrix.Yy = 0.0; matrix.Yz = 1.0
    matrix.Zx = 0.0; matrix.Zy = 1.0; matrix.Zz = 0.0
    
    nx_matrix = work_part.NXMatrices.Create(matrix)
    
    # Try passing Point object
    try:
        csys = work_part.CoordinateSystems.CreateCoordinateSystem(pt_s2, nx_matrix, True)
        print("Success! Created coordinate system with Point object.")
    except Exception as e:
        print(f"Failed to create coordinate system with Point object: {e}")
        return

    factory = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder2", None)
    if factory is None:
        factory = getattr(work_part.Sketches, "CreateSketchInPlaceBuilder", None)
    builder = factory(None)
    
    builder.Csystem = csys
            
    commit = getattr(builder, "CommitFeature", None) or getattr(builder, "Commit", None)
    feat = commit()
    sk2 = feat.Sketch if hasattr(feat, "Sketch") else feat
    builder.Destroy()

    print("Sketch S2 created.")
    print(f"  Origin: {sk2.Origin.X}, {sk2.Origin.Y}, {sk2.Origin.Z}")

if __name__ == "__main__":
    main()
