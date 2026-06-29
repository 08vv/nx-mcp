import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay("C:\\Users\\HP\\nx-mcp\\scratch\\temp_inspect_mm.prt", NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    
    builder = work_part.BaseFeatures.CreateMoveObjectBuilder(NXOpen.Features.MoveObject.Null)
    tm = builder.TransformMotion
    
    print("TransformMotion attributes:")
    for name in dir(tm):
        if not name.startswith("__"):
            print(f"  {name}")
            
    # Set to Distance
    tm.Option = NXOpen.GeometricUtilities.ModlMotion.Options.Distance
    print("\nDistance attributes:")
    if hasattr(tm, "Distance"):
        for name in dir(tm.Distance):
            if not name.startswith("__"):
                print(f"  {name}")
                
    # Set to TranslateDelta
    tm.Option = NXOpen.GeometricUtilities.ModlMotion.Options.TranslateDelta
    print("\nDelta attributes:")
    for attr in ("DeltaX", "DeltaY", "DeltaZ", "TranslationVector", "Distance"):
        if hasattr(tm, attr):
            val = getattr(tm, attr)
            print(f"  {attr}: type={type(val)}")
            if val is not None:
                for name in dir(val):
                    if not name.startswith("__"):
                        print(f"    {attr}.{name}")

if __name__ == "__main__":
    main()
