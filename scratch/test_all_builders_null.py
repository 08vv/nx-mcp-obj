import NXOpen
import sys

def main():
    session = NXOpen.Session.GetSession()
    part = session.Parts.Work
    if part is None:
        part = session.Parts.NewDisplay(r"C:\Users\HP\nx-mcp\scratch\temp_builders_test.prt", NXOpen.Part.Units.Millimeters)

    # 1. Test SplitBodyBuilder
    try:
        builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.SplitBody.Null)
        print("[OK] CreateSplitBodyBuilder succeeded with SplitBody.Null")
        builder.Destroy()
    except Exception as e:
        print("[FAIL] CreateSplitBodyBuilder with SplitBody.Null:", e)
        
    try:
        builder = part.Features.CreateSplitBodyBuilder(NXOpen.Features.Feature.Null)
        print("[OK] CreateSplitBodyBuilder succeeded with Feature.Null")
        builder.Destroy()
    except Exception as e:
        print("[FAIL] CreateSplitBodyBuilder with Feature.Null:", e)

    # 2. Test OffsetFaceBuilder
    try:
        builder = part.Features.CreateOffsetFaceBuilder(NXOpen.Features.OffsetFace.Null)
        print("[OK] CreateOffsetFaceBuilder succeeded with OffsetFace.Null")
        builder.Destroy()
    except Exception as e:
        print("[FAIL] CreateOffsetFaceBuilder with OffsetFace.Null:", e)

    try:
        builder = part.Features.CreateOffsetFaceBuilder(NXOpen.Features.Feature.Null)
        print("[OK] CreateOffsetFaceBuilder succeeded with Feature.Null")
        builder.Destroy()
    except Exception as e:
        print("[FAIL] CreateOffsetFaceBuilder with Feature.Null:", e)

    # 3. Test ShellBuilder
    # In NX, the shell feature might be named 'Shell' or 'ShellFeature' or 'BodyFeature'
    for null_name in ["Shell", "ShellFeature", "Feature"]:
        try:
            null_class = getattr(NXOpen.Features, null_name, None)
            if null_class is not None:
                builder = part.Features.CreateShellBuilder(null_class.Null)
                print(f"[OK] CreateShellBuilder succeeded with {null_name}.Null")
                builder.Destroy()
        except Exception as e:
            print(f"[FAIL] CreateShellBuilder with {null_name}.Null:", e)

    # 4. Test DatumPlaneBuilder
    for null_name in ["DatumPlane", "Feature"]:
        try:
            null_class = getattr(NXOpen.Features, null_name, None)
            if null_class is not None:
                builder = part.Features.CreateDatumPlaneBuilder(null_class.Null)
                print(f"[OK] CreateDatumPlaneBuilder succeeded with {null_name}.Null")
                builder.Destroy()
        except Exception as e:
            print(f"[FAIL] CreateDatumPlaneBuilder with {null_name}.Null:", e)

if __name__ == "__main__":
    main()
