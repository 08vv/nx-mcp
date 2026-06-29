import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay("C:\\Users\\HP\\nx-mcp\\scratch\\temp_inspect_mo.prt", NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    
    builder = work_part.BaseFeatures.CreateMoveObjectBuilder(NXOpen.Features.MoveObject.Null)
    print("MoveObjectBuilder attributes:")
    for name in dir(builder):
        if not name.startswith("__"):
            print(f"  {name}")
            
    print("\nModlMotion.Options:")
    if hasattr(NXOpen.GeometricUtilities, "ModlMotion"):
        if hasattr(NXOpen.GeometricUtilities.ModlMotion, "Options"):
            for name in dir(NXOpen.GeometricUtilities.ModlMotion.Options):
                if not name.startswith("__"):
                    print(f"  {name}")

if __name__ == "__main__":
    main()

