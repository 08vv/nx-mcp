"""Open the flange .prt in the current NX session, set it as display, fit view."""
import NXOpen

PRT = r"C:\Users\HP\Documents\NX_MCP_Parts\circular_flange_120_50_15.prt"

session = NXOpen.Session.GetSession()

# Open and make display part
part = session.Parts.OpenDisplay(PRT)
work = session.Parts.Work
if work is not None:
    work.ModelingViews.WorkView.Fit()

NXOpen.UI.GetUI().NXMessageBox.Show(
    "NX MCP",
    NXOpen.NXMessageBox.DialogType.Information,
    "Flange loaded!\n" + PRT
)
