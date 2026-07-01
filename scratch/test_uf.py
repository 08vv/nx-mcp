import NXOpen
import NXOpen.UF

def main():
    uf_session = NXOpen.UF.UFSession.GetUFSession()
    print("Modl methods with 'Face':")
    for attr in dir(uf_session.Modl):
        if "face" in attr.lower():
            print(f"  {attr}")
            
    print("\nModeling methods with 'Face':")
    for attr in dir(uf_session.Modeling):
        if "face" in attr.lower():
            print(f"  {attr}")

if __name__ == "__main__":
    main()
