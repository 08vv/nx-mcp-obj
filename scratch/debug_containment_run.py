import NXOpen
import NXOpen.UF

def main():
    session = NXOpen.Session.GetSession()
    uf_session = NXOpen.UF.UFSession.GetUFSession()
    filename = "C:/Users/HP/nx-mcp/offset_link_bracket.prt"
    try:
        part = session.Parts.OpenDisplay(filename)
    except Exception as e:
        print(f"Failed to open part: {e}")
        return
        
    work_part = session.Parts.Work
    bodies = list(work_part.Bodies)
    print(f"Loaded {len(bodies)} bodies")
    
    with open("C:/Users/HP/nx-mcp/debug_containment_run_out.txt", "w") as f:
        for i, body in enumerate(bodies):
            f.write(f"Body {i}: Tag={body.Tag}\n")
            # Print bounding box or bounds
            # Since AskBodyBbox failed because of attribute error, let's find the correct name:
            # Let's inspect dir(uf_session.Modeling) for bbox methods:
            bbox_methods = [a for a in dir(uf_session.Modeling) if "bbox" in a.lower()]
            f.write(f"BBox methods: {bbox_methods}\n")
            
            # Let's try uf_session.Modeling.AskBodyBoundaries or AskBodyBbox
            # Wait, in the previous run: AttributeError: 'NXOpen.UF.Modeling' object has no attribute 'AskBodyBbox'
            # Let's check how body bounds are fetched in nx_bridge.py line 256:
            # In nx_bridge.py, _body_bounds(body) does:
            # bbox = uf_session.Modeling.AskBodyBoundaries(body.Tag) or similar?
            # Let's check:
            # In NXOpen, we can get bbox from body.GetBounds() or similar!
            try:
                # Test containment along local centerline of top arm:
                # The top arm center line goes from (78, 0) at 160 degrees.
                # Let's print containment along this line at Z = 55.0 (middle of top arm plate)
                f.write(f"Top arm centerline containment at Z=55.0:\n")
                import math
                for dist in [0.0, 12.0, 30.0, 50.0, 66.0, 78.0, 90.0]:
                    x = 78.0 + dist * math.cos(math.radians(160.0))
                    y = dist * math.sin(math.radians(160.0))
                    res = uf_session.Modeling.AskPointContainment([x, y, 55.0], body.Tag)
                    f.write(f"  dist={dist} (x={x:.3f}, y={y:.3f}) -> containment={res}\n")
            except Exception as e:
                f.write(f"  Error: {e}\n")

if __name__ == "__main__":
    main()
