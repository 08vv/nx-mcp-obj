import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_pt_feat_test.prt", NXOpen.Part.Units.Millimeters)
        
    try:
        # CreatePointFeatureBuilder expects NXOpen.Features.PointFeature.Null
        pt_builder = part.Features.CreatePointFeatureBuilder(NXOpen.Features.PointFeature.Null)
        print("PointFeatureBuilder members:")
        for m in sorted(dir(pt_builder)):
            if not m.startswith("__"):
                print(f"  {m}: {type(getattr(pt_builder, m))}")
        pt_builder.Destroy()
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    main()
