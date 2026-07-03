import NXOpen
import NXOpen.UF

def main():
    session = NXOpen.Session.GetSession()
    uf_session = NXOpen.UF.UFSession.GetUFSession()
    modeling = uf_session.Modeling
    
    attrs = dir(modeling)
    boolean_attrs = [a for a in attrs if "bool" in a.lower()]
    print("Boolean attributes: " + str(boolean_attrs))

if __name__ == "__main__":
    main()
