import NXOpen
session = NXOpen.Session.GetSession()
session.Parts.NewDisplay("C:/Users/HP/nx-mcp/test.prt", NXOpen.Part.Units.Millimeters)
print("OK: Part created")
