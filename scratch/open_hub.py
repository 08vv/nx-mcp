"""Force-close any old hub part and reopen the freshly rebuilt one in NX."""
import NXOpen

PRT = r"C:\Users\HP\Documents\NX_MCP_Parts\automotive_pulley_hub.prt"

session = NXOpen.Session.GetSession()

# Close any already-open copy of the hub so we get a fresh load
for p in list(session.Parts):
    try:
        if "automotive_pulley_hub" in p.FullPath.lower():
            p.Close(
                NXOpen.BasePart.CloseWholeTree.TrueValue,
                NXOpen.BasePart.KeepTransient.FalseValue,
                None,
            )
    except Exception:
        pass

# Open the fresh .prt and set it as the display part
part = session.Parts.OpenDisplay(PRT, NXOpen.PartLoadStatus())
work = session.Parts.Work
if work is not None:
    work.ModelingViews.WorkView.Fit()

NXOpen.UI.GetUI().NXMessageBox.Show(
    "Hub Reloaded",
    NXOpen.NXMessageBox.DialogType.Information,
    "Automotive Pulley Hub (updated) loaded!\n\n"
    "Cylinder 7 = Ø2 mm  (the 3rd bolt hole at 180°)\n"
    "Other holes = Ø12 mm\n\n"
    "File: " + PRT,
)
