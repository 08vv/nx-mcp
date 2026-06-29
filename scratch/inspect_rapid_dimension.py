import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    # Create temp part to get work_part
    part = session.Parts.NewDisplay("C:\\Users\\HP\\nx-mcp\\scratch\\temp_inspect.prt", NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    
    # Inspect work_part.Sketches
    print("work_part.Sketches methods:")
    for name in dir(work_part.Sketches):
        if "Dimension" in name or "Builder" in name:
            print(f"  {name}")
            
    # Inspect SketchRapidDimensionBuilder
    builder_class = getattr(NXOpen, "SketchRapidDimensionBuilder", None)
    if builder_class:
        print("\nSketchRapidDimensionBuilder methods:")
        for name in dir(builder_class):
            if not name.startswith("__"):
                print(f"  {name}")

if __name__ == "__main__":
    main()
