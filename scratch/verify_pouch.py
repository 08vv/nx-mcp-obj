import NXOpen
import sys
import os
import glob

def read_latest_syslog():
    """Read the most recently modified syslog file from Temp."""
    temp_dir = os.environ.get("TEMP", r"C:\Users\HP\AppData\Local\Temp")
    pattern = os.path.join(temp_dir, "HP*.syslog")
    files = glob.glob(pattern)
    if not files:
        return ""
    latest = max(files, key=os.path.getmtime)
    try:
        with open(latest, "r", errors="replace") as f:
            return f.read()[-4000:]   # last 4000 chars
    except Exception:
        return ""

def test_update(the_session, part, name, new_val):
    expr = part.Expressions.FindObject(name)
    orig = expr.RightHandSide
    print("  Testing {} -> {} (orig={})".format(name, new_val, orig))
    expr.RightHandSide = str(new_val)
    try:
        mark = the_session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "Test")
        the_session.UpdateManager.DoUpdate(mark)
        print("  [OK] Update succeeded!")
        result = True
    except Exception as e:
        print("  [FAIL] Update failed: {}".format(e))
        log = read_latest_syslog()
        # Print lines containing 'fail' or 'error' or 'undo' or feature names
        for line in log.splitlines():
            if any(kw in line.lower() for kw in ("fail", "error", "undo", "crimp", "through", "boolean", "pattern")):
                print("  SYSLOG: {}".format(line.strip()))
        result = False
    finally:
        expr.RightHandSide = orig
        try:
            m2 = the_session.SetUndoMark(NXOpen.Session.MarkVisibility.Invisible, "Reset")
            the_session.UpdateManager.DoUpdate(m2)
        except Exception:
            pass
    return result

def main():
    the_session = NXOpen.Session.GetSession()
    part_path = r"C:\Users\HP\nx-mcp\Pouch_Model.prt"
    base_part, load_status = the_session.Parts.OpenActiveDisplay(
        part_path, NXOpen.DisplayPartOption.AllowAdditional
    )
    load_status.Dispose()
    part = the_session.Parts.Work
    print("[OK] Opened: {}".format(part.Leaf))

    solid_bodies = [b for b in list(part.Bodies) if b.IsSolidBody]
    print("Solid bodies: {}".format(len(solid_bodies)))
    for b in solid_bodies:
        print("  '{}' ({})".format(b.Name, b.JournalIdentifier))

    any_failed = False

    # Test small increments first, then larger ones
    tests = [
        ("Overall_Height", 202.0),
        ("Overall_Height", 210.0),
        ("Overall_Height", 220.0),
        ("Overall_Width",  122.0),
        ("Overall_Width",  130.0),
        ("Fill_Bulge_Depth", 40.0),
    ]

    for name, val in tests:
        ok = test_update(the_session, part, name, val)
        if not ok:
            any_failed = True

    if any_failed:
        print("\n[RESULT] Some updates FAILED.")
        sys.exit(1)
    else:
        print("\n[RESULT] All updates PASSED!")

if __name__ == "__main__":
    main()
