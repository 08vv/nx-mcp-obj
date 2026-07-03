import NXOpen

def main():
    session = NXOpen.Session.GetSession()
    filename = "C:/Users/HP/nx-mcp/offset_link_bracket.prt"
    try:
        part = session.Parts.OpenDisplay(filename)
    except Exception as e:
        print(f"Failed to open part: {e}")
        return
        
    work_part = session.Parts.Work
    bodies = list(work_part.Bodies)
    print(f"Loaded {len(bodies)} bodies")
    if len(bodies) < 3:
        print("Need at least 3 bodies")
        return
        
    # In offset_link_bracket.prt:
    # Body 0 (Tag 35284): top arm plate (Z = 53 to 61)
    # Body 1 (Tag 35293): bottom arm plate (Z = 0 to 8)
    # Body 2 (Tag 35258): boss cylinder (Z = 8 to 53)
    #
    # We want to unite Body 1 and Body 2:
    body1 = None
    body2 = None
    for b in bodies:
        if b.Tag == 35293:
            body1 = b
        elif b.Tag == 35258:
            body2 = b
            
    if not body1 or not body2:
        print("Could not find Body 1 or Body 2 by tag")
        return
        
    print(f"Uniting body1 (tag={body1.Tag}) and body2 (tag={body2.Tag})")
    
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        builder.Targets.Add(body1)
        
        collector = work_part.ScCollectors.CreateCollector()
        rule = work_part.ScRuleFactory.CreateRuleBodyDumb([body2], True)
        collector.ReplaceRules([rule], False)
        builder.ToolBodyCollector = collector
        
        feat = builder.CommitFeature()
        print("CommitFeature succeeded! Feature tag = " + str(feat.Tag))
    except Exception as e:
        print("CommitFeature failed: " + str(e))
    finally:
        builder.Destroy()
        
    print(f"Bodies count after commit: {len(list(work_part.Bodies))}")

if __name__ == "__main__":
    main()
