import sys
from pathlib import Path
import math

sys.path.insert(0, r"c:\Users\HP\nx-mcp\src")

import NXOpen
import NXOpen.UF

def main():
    output_path = Path(r"c:\Users\HP\nx-mcp\scratch\test_cyl.prt")
    if output_path.exists():
        output_path.unlink()
        
    session = NXOpen.Session.GetSession()
    session.Parts.NewDisplay(str(output_path), NXOpen.Part.Units.Millimeters)
    work_part = session.Parts.Work
    
    # Define expressions
    work_part.Expressions.CreateExpression("Number", "ARM_THICKNESS = 8")
    work_part.Expressions.CreateExpression("Number", "ARM_WIDTH = 22")
    work_part.Expressions.CreateExpression("Number", "HOLE_DIAMETER = 10")
    
    # Coordinates
    rise_rad = math.radians(45.0)
    sin_r = math.sin(rise_rad)
    cos_r = math.cos(rise_rad)
    c45 = math.cos(math.radians(45.0))
    s45 = math.sin(math.radians(45.0))
    
    # Direction vectors
    u_len_x = sin_r * c45
    u_len_y = sin_r * s45
    u_len_z = cos_r
    
    u_thk_x = -cos_r * c45
    u_thk_y = -cos_r * s45
    u_thk_z = sin_r
    
    px, py, pz = 0.0, 0.0, 28.0
    ARM_LENGTH = 110.0
    
    tip_x = px + ARM_LENGTH * u_len_x
    tip_y = py + ARM_LENGTH * u_len_y
    tip_z = pz + ARM_LENGTH * u_len_z
    tip = NXOpen.Point3d(tip_x, tip_y, tip_z)
    
    u_thk_vec = NXOpen.Vector3d(u_thk_x, u_thk_y, u_thk_z)
    
    # Create cylinder
    builder = work_part.Features.CreateCylinderBuilder(NXOpen.Features.Feature.Null)
    direction = work_part.Directions.CreateDirection(
        tip, u_thk_vec, NXOpen.SmartObject.UpdateOption.WithinModeling)
    builder.Diameter.RightHandSide = "ARM_WIDTH"
    builder.Height.RightHandSide   = "ARM_THICKNESS"
    builder.Axis.Point.SetCoordinates(tip)
    builder.Axis.Direction = direction
    feat = builder.Commit()
    body = feat.GetBodies()[0]
    
    # Let's inspect the body properties or box
    box = body.GetBoundingBox()
    print(f"Cylinder min: ({box.Min.X}, {box.Min.Y}, {box.Min.Z})")
    print(f"Cylinder max: ({box.Max.X}, {box.Max.Y}, {box.Max.Z})")
    
    # Save/close
    work_part.Save(NXOpen.BasePart.SaveComponents.TrueValue, NXOpen.BasePart.CloseAfterSave.FalseValue)
    
if __name__ == "__main__":
    main()
