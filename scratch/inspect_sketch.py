import NXOpen
import sys

def main():
    print("\nNXOpen.SketchConstraintPointType:")
    if hasattr(NXOpen, "SketchConstraintPointType"):
        for name in dir(NXOpen.SketchConstraintPointType):
            if not name.startswith("__"):
                print(f"  {name}")
            
    print("\nNXOpen.SketchDimensionOption:")
    if hasattr(NXOpen, "SketchDimensionOption"):
        for name in dir(NXOpen.SketchDimensionOption):
            if not name.startswith("__"):
                print(f"  {name}")
            
    print("\nNXOpen.SketchAssocType:")
    if hasattr(NXOpen, "SketchAssocType"):
        for name in dir(NXOpen.SketchAssocType):
            if not name.startswith("__"):
                print(f"  {name}")


if __name__ == "__main__":
    main()
