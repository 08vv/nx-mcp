import NXOpen


def main():
    session = NXOpen.Session.GetSession()
    listing_window = session.ListingWindow
    listing_window.Open()

    version = session.GetEnvironmentVariableValue("NX_FULL_VERSION") or "unknown"
    listing_window.WriteLine(f"NX_MCP_VALIDATE_NXOPEN ok version={version}")

    listing_window.Close()


if __name__ == "__main__":
    main()
