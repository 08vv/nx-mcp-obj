import NXOpen
import NXOpen.UF

def main():
    session = NXOpen.Session.GetSession()
    uf_session = NXOpen.UF.UFSession.GetUFSession()
    work_part = session.Parts.Work
    if work_part is None:
        print("No work part")
        return
        
    bodies = list(work_part.Bodies.ToArray() or [])
    if not bodies:
        print("No bodies")
        return
        
    body = bodies[0]
    # Test point containment
    pt_inside = [0.0, 0.0, 4.0]
    try:
        res = uf_session.Modeling.AskPointContainment(pt_inside, body.Tag)
        print("Containment of inside point: " + str(res))
    except Exception as e:
        print("Failed AskPointContainment: " + str(e))

if __name__ == "__main__":
    main()
