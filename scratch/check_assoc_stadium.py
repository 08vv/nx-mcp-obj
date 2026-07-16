import NXOpen

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.NewDisplay("temp.prt", NXOpen.Part.Units.Millimeters)
    
    factory = part.ScRuleFactory
    # List all methods containing 'curve' or 'rule'
    methods = [m for m in dir(factory) if not m.startswith('_')]
    curve_methods = [m for m in methods if 'curve' in m.lower() or 'Curve' in m]
    print("ScRuleFactory curve methods:")
    for m in curve_methods:
        print("  {}".format(m))

if __name__ == "__main__":
    main()
