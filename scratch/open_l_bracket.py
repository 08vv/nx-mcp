"""Open the L-bracket .prt in the current NX session, set it as display, fit view."""
import NXOpen

PRT = r"C:\Users\HP\nx-mcp\src\nx_mcp\journals\l_bracket_mounting.prt"

session = NXOpen.Session.GetSession()

# Open and make display part
part = session.Parts.OpenDisplay(PRT)
work = session.Parts.Work
if work is not None:
    work.ModelingViews.WorkView.Fit()

NXOpen.UI.GetUI().NXMessageBox.Show(
    "NX MCP",
    NXOpen.NXMessageBox.DialogType.Information,
    "L-Bracket loaded!\n" + PRT
)
