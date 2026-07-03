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
    if len(bodies) < 2:
        print("Need at least 2 bodies")
        return
        
    target_body = bodies[0]
    tool_body = bodies[1]
    print(f"Target body: Tag={target_body.Tag}, Tool body: Tag={tool_body.Tag}")
    
    builder = work_part.Features.CreateBooleanBuilder(NXOpen.Features.BooleanFeature.Null)
    try:
        builder.Operation = NXOpen.Features.Feature.BooleanType.Unite
        builder.Targets.Add(target_body)
        
        collector = work_part.ScCollectors.CreateCollector()
        rule = work_part.ScRuleFactory.CreateRuleBodyDumb([tool_body], True)
        collector.ReplaceRules([rule], False)
        builder.ToolBodyCollector = collector
        
        feat = builder.CommitFeature()
        print("CommitFeature succeeded! Feature tag = " + str(feat.Tag))
    except Exception as e:
        print("CommitFeature failed: " + str(e))
    finally:
        builder.Destroy()
        
    # Check number of bodies now
    bodies_after = list(work_part.Bodies)
    print(f"Number of bodies after commit: {len(bodies_after)}")

if __name__ == "__main__":
    main()
