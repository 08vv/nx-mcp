"""Open the automotive pulley hub .prt in NX, set as display, fit view."""
import NXOpen

PRT = r"C:\Users\HP\Documents\NX_MCP_Parts\automotive_pulley_hub.prt"

session = NXOpen.Session.GetSession()
part = session.Parts.OpenDisplay(PRT)
work = session.Parts.Work
if work is not None:
    work.ModelingViews.WorkView.Fit()

NXOpen.UI.GetUI().NXMessageBox.Show(
    "NX MCP",
    NXOpen.NXMessageBox.DialogType.Information,
    "Pulley Hub loaded!\n" + PRT,
)
