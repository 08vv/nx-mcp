import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay("C:\\Users\\HP\\nx-mcp\\scratch\\temp_inspect_dg.prt", NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    
    dg = NXOpen.Sketch.DimensionGeometry()
    print("DimensionGeometry attributes:")
    for name in dir(dg):
        if not name.startswith("__"):
            print(f"  {name}")
            
    cg = NXOpen.Sketch.ConstraintGeometry()
    print("ConstraintGeometry attributes:")
    for name in dir(cg):
        if not name.startswith("__"):
            print(f"  {name}")

if __name__ == "__main__":
    main()
