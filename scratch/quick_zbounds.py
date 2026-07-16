
import NXOpen
session = NXOpen.Session.GetSession()
part, _ = session.Parts.Open(r'c:\Users\HP\nx-mcp\Toothpaste_Tube.prt')
for b in list(part.Bodies):
    zvals = []
    for e in list(b.GetEdges()):
        try:
            verts = e.GetVertices()
            for v in verts:
                zvals.append(float(v.Z))
        except: pass
    if zvals:
        print('{}: Z={:.3f} to {:.3f}'.format(b.Name, min(zvals), max(zvals)))
