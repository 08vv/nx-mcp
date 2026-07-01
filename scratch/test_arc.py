import NXOpen

def main():
    session = NXOpen.Session.GetSession()
    work_part = session.Parts.Work
    if work_part is None:
        work_part = session.Parts.NewDisplay("C:/Users/HP/nx-mcp/scratch/temp.prt", NXOpen.Part.Units.Millimeters)

    try:
        # Intentionally fail to print overloads
        work_part.Curves.CreateArc("dummy")
    except Exception as e:
        print("CreateArc overloads exception:")
        print(str(e))

if __name__ == "__main__":
    main()
