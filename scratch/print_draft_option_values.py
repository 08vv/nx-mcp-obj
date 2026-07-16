import NXOpen
import sys

def main():
    print("Checking MultiDraft and SimpleDraftTypeMemberType...")
    
    try:
        print("MultiDraft.Types:", NXOpen.GeometricUtilities.MultiDraft.Types)
        print("MultiDraft.Types members:", dir(NXOpen.GeometricUtilities.MultiDraft.Types))
    except Exception as e:
        print("Error accessing MultiDraft.Types:", e)
        
    try:
        # Let's see if we can instantiate or check SimpleDraftSimpleDraftTypeMemberType values
        # Sometimes we can get it via NXOpen.GeometricUtilities.MultiDraft.SimpleDraftType
        print("SimpleDraftType:", NXOpen.GeometricUtilities.MultiDraft.SimpleDraftType)
        print("SimpleDraftType members:", dir(NXOpen.GeometricUtilities.MultiDraft.SimpleDraftType))
    except Exception as e:
        print("Error accessing SimpleDraftType:", e)

if __name__ == "__main__":
    main()
