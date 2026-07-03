import NXOpen
import NXOpen.UF
import sys

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
    
    with open("C:/Users/HP/nx-mcp/debug_out.txt", "w") as f:
        f.write(f"Number of bodies: {len(bodies)}\n")
        for i, body in enumerate(bodies):
            # Get bounding box
            try:
                bbox = uf_session.Modeling.AskBodyBbox(body.Tag)
                f.write(f"Body {i}: Tag={body.Tag}, BBox={bbox}\n")
            except Exception as e:
                f.write(f"Body {i}: Tag={body.Tag}, BBox failed: {e}\n")
                
            # Test a few points around (66.7, 4.1, Z)
            f.write(f"Containment tests for Body {i}:\n")
            x, y = 66.7236, 4.1042
            for z in [4.0, 8.0, 20.0, 45.0, 52.0, 53.1, 55.0, 60.0, 62.0]:
                pt = [x, y, z]
                try:
                    res = uf_session.Modeling.AskPointContainment(pt, body.Tag)
                    f.write(f"  pt={pt} -> containment={res}\n")
                except Exception as e:
                    f.write(f"  pt={pt} -> failed: {e}\n")

if __name__ == "__main__":
    main()
