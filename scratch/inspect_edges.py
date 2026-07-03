import NXOpen

def main():
    session = NXOpen.Session.GetSession()
    # Open the part
    part_path = r"C:\Users\HP\nx-mcp\mounting_plate_v6.prt"
    try:
        base_part = session.Parts.OpenDisplay(part_path)
    except Exception as e:
        print(f"Failed to open part: {e}")
        return
    work_part = session.Parts.Work
    if work_part is None:
        print("No active work part.")
        return
        
    print("Listing edges of base plate...")
    # Find base plate body
    bodies = work_part.Bodies
    for body in bodies:
        print(f"Body: {body.JournalIdentifier}")
        edges = body.GetEdges()
        print(f"Number of edges: {len(edges)}")
        for i, edge in enumerate(edges):
            try:
                v1, v2 = edge.GetVertices()
                p1 = v1.GetCoordinates()
                p2 = v2.GetCoordinates()
                print(f"Edge {i}: p1=({p1.X:.2f}, {p1.Y:.2f}, {p1.Z:.2f}), p2=({p2.X:.2f}, {p2.Y:.2f}, {p2.Z:.2f})")
            except Exception as e:
                print(f"Edge {i}: failed GetVertices: {e}")

if __name__ == "__main__":
    main()
