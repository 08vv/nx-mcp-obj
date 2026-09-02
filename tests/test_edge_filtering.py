import sys
from unittest.mock import MagicMock

def test_resolve_edges_outer_filter(monkeypatch):
    mock_nxopen = MagicMock()
    mock_uf_session = MagicMock()
    mock_nxopen.UF.UFSession.GetUFSession.return_value = mock_uf_session
    mock_nxopen.Session.GetSession.return_value = MagicMock()
    
    orig_nxopen = sys.modules.get("NXOpen")
    orig_nxopen_uf = sys.modules.get("NXOpen.UF")
    
    sys.modules["NXOpen"] = mock_nxopen
    sys.modules["NXOpen.UF"] = mock_nxopen.UF
    
    try:
        from nx_mcp.bridge import nx_bridge
        
        mock_body = MagicMock()
        mock_edge1 = MagicMock()
        mock_edge1.Tag = 101
        mock_edge2 = MagicMock()
        mock_edge2.Tag = 102
        
        mock_body.GetEdges.return_value = [mock_edge1, mock_edge2]
        
        mock_face1 = MagicMock()
        mock_face1.Tag = 201
        mock_face2 = MagicMock()
        mock_face2.Tag = 202
        
        mock_edge1.GetFaces.return_value = [mock_face1]
        mock_edge2.GetFaces.return_value = [mock_face1, mock_face2]
        
        def fake_ask_face_data(tag):
            if tag == 201:
                return (21, [0,0,0], [0,0,1], [0,0,0,0,0,0], 0.0, [], 1)
            elif tag == 202:
                return (16, [40,15,0], [0,0,1], [0,0,0,0,0,0], 3.0, [], -1)
            return (21, [0,0,0], [0,0,1], [0,0,0,0,0,0], 0.0, [], 1)
            
        mock_uf_session.Modeling.AskFaceData = fake_ask_face_data
        monkeypatch.setattr(nx_bridge, "_resolve_body", lambda ref: mock_body)
        
        res = nx_bridge._resolve_edges("last", "outer_edges")
        assert len(res) == 2
        
        res_all = nx_bridge._resolve_edges("last", "all_edges")
        assert res_all == [mock_edge1, mock_edge2]
        
    finally:
        if orig_nxopen:
            sys.modules["NXOpen"] = orig_nxopen
        else:
            sys.modules.pop("NXOpen", None)
        if orig_nxopen_uf:
            sys.modules["NXOpen.UF"] = orig_nxopen_uf
        else:
            sys.modules.pop("NXOpen.UF", None)


def test_feature_scoped_edge_selection_delta_tracking(monkeypatch):
    mock_nxopen = MagicMock()
    mock_uf_session = MagicMock()
    mock_nxopen.UF.UFSession.GetUFSession.return_value = mock_uf_session
    mock_nxopen.Session.GetSession.return_value = MagicMock()

    orig_nxopen = sys.modules.get("NXOpen")
    orig_nxopen_uf = sys.modules.get("NXOpen.UF")

    sys.modules["NXOpen"] = mock_nxopen
    sys.modules["NXOpen.UF"] = mock_nxopen.UF

    try:
        from nx_mcp.bridge import nx_bridge

        nx_bridge._state.clear()
        nx_bridge._state.update({
            "features": {},
            "bodies": {},
            "last_feature": None,
            "last_body": None,
            "pre_body_edges": set(),
            "pre_body_faces": set(),
        })

        # Feature 1: cylinder_a (additive)
        edge_a1, edge_a2 = MagicMock(), MagicMock()
        edge_a1.Tag, edge_a2.Tag = 101, 102
        body_a = MagicMock()
        body_a.GetEdges.return_value = [edge_a1, edge_a2]
        body_a.GetFaces.return_value = []

        feat_a = MagicMock()
        feat_a.GetFeatureName.return_value = "cylinder_a"
        feat_a.JournalIdentifier = "cylinder_a"
        feat_a.GetBodies.return_value = [body_a]
        feat_a.GetEntities.return_value = []

        monkeypatch.setattr(nx_bridge, "_resolve_body", lambda ref: body_a)
        nx_bridge._remember_feature(feat_a)

        assert set(nx_bridge._state["features"]["cylinder_a"]["edge_tags"]) == {101, 102}

        # Feature 2: cylinder_b (additive at identical Z height)
        edge_b1, edge_b2 = MagicMock(), MagicMock()
        edge_b1.Tag, edge_b2.Tag = 201, 202
        body_b = MagicMock()
        body_b.GetEdges.return_value = [edge_a1, edge_a2, edge_b1, edge_b2]
        body_b.GetFaces.return_value = []

        feat_b = MagicMock()
        feat_b.GetFeatureName.return_value = "cylinder_b"
        feat_b.JournalIdentifier = "cylinder_b"
        feat_b.GetBodies.return_value = [body_b]
        feat_b.GetEntities.return_value = []

        monkeypatch.setattr(nx_bridge, "_resolve_body", lambda ref: body_b)
        nx_bridge._remember_feature(feat_b)

        # Confirm delta tracking isolated cylinder_b's edges without leaking cylinder_a's edges
        assert set(nx_bridge._state["features"]["cylinder_b"]["edge_tags"]) == {201, 202}

        # Boolean Unite: A and B are united into merged_body by feat_unite
        seam_edge = MagicMock()
        seam_edge.Tag = 301
        merged_body = MagicMock()
        merged_body.GetEdges.return_value = [edge_a1, edge_a2, edge_b1, edge_b2, seam_edge]
        merged_body.GetFaces.return_value = []

        feat_unite = MagicMock()
        feat_unite.GetFeatureName.return_value = "unite_1"
        feat_unite.JournalIdentifier = "unite_1"
        feat_unite.GetBodies.return_value = [merged_body]
        feat_unite.GetEntities.return_value = []

        monkeypatch.setattr(nx_bridge, "_resolve_body", lambda ref: merged_body)
        nx_bridge._remember_feature(feat_unite)

        # Confirm post-union edge resolution by feature name returns scoped edges on merged body
        resolved_a = nx_bridge._resolve_edges("last", "cylinder_a")
        assert resolved_a == [edge_a1, edge_a2]

        resolved_b = nx_bridge._resolve_edges("last", "cylinder_b")
        assert resolved_b == [edge_b1, edge_b2]

        # Feature 3: hole_1 (cut feature)
        hole_edge1, hole_edge2 = MagicMock(), MagicMock()
        hole_edge1.Tag, hole_edge2.Tag = 401, 402
        cut_body = MagicMock()
        cut_body.GetEdges.return_value = [edge_a1, edge_a2, edge_b1, edge_b2, seam_edge, hole_edge1, hole_edge2]
        cut_body.GetFaces.return_value = []

        feat_hole = MagicMock()
        feat_hole.GetFeatureName.return_value = "hole_1"
        feat_hole.JournalIdentifier = "hole_1"
        feat_hole.GetBodies.return_value = [cut_body]
        feat_hole.GetEntities.return_value = []

        monkeypatch.setattr(nx_bridge, "_resolve_body", lambda ref: cut_body)
        nx_bridge._remember_feature(feat_hole)

        # Confirm newly exposed cut edges are isolated for hole_1
        assert set(nx_bridge._state["features"]["hole_1"]["edge_tags"]) == {401, 402}

        resolved_hole = nx_bridge._resolve_edges("last", "hole_1")
        assert resolved_hole == [hole_edge1, hole_edge2]

    finally:
        if orig_nxopen:
            sys.modules["NXOpen"] = orig_nxopen
        else:
            sys.modules.pop("NXOpen", None)
        if orig_nxopen_uf:
            sys.modules["NXOpen.UF"] = orig_nxopen_uf
        else:
            sys.modules.pop("NXOpen.UF", None)


def test_spatial_edge_resolution_composite_and_errors(monkeypatch):
    mock_nxopen = MagicMock()
    mock_uf_session = MagicMock()
    mock_nxopen.UF.UFSession.GetUFSession.return_value = mock_uf_session
    mock_nxopen.Session.GetSession.return_value = MagicMock()

    orig_nxopen = sys.modules.get("NXOpen")
    orig_nxopen_uf = sys.modules.get("NXOpen.UF")

    sys.modules["NXOpen"] = mock_nxopen
    sys.modules["NXOpen.UF"] = mock_nxopen.UF

    try:
        from nx_mcp.bridge import nx_bridge

        def make_mock_edge(tag, p1, p2):
            e = MagicMock()
            e.Tag = tag
            v1, v2 = MagicMock(), MagicMock()
            v1.X, v1.Y, v1.Z = p1
            v2.X, v2.Y, v2.Z = p2
            e.GetVertices.return_value = [v1, v2]
            e.GetLength.return_value = sum((b - a) ** 2 for a, b in zip(p1, p2)) ** 0.5
            return e

        # Composite body mock with 3 Z-bands (Z=0..6, Z=39..45)
        top_edge = make_mock_edge(1, (0, 0, 45), (10, 0, 45))
        bot_edge1 = make_mock_edge(2, (0, 0, 0), (20, 0, 0))
        bot_edge2 = make_mock_edge(3, (0, 0, 0), (0, 15, 0))
        vert_edge1 = make_mock_edge(4, (0, 0, 0), (0, 0, 6))
        vert_edge2 = make_mock_edge(5, (10, 5, 39), (10, 5, 45))

        body = MagicMock()
        body.GetEdges.return_value = [top_edge, bot_edge1, bot_edge2, vert_edge1, vert_edge2]
        monkeypatch.setattr(nx_bridge, "_resolve_body", lambda ref: body)

        # 1. Top edges (Z=45)
        res_top = nx_bridge._resolve_edges("last", "top_edges")
        assert res_top == [top_edge]

        # 2. Bottom edges (Z=0)
        res_bot = nx_bridge._resolve_edges("last", "bottom_edges")
        assert res_bot == [bot_edge1, bot_edge2]

        # 3. Vertical edges
        res_vert = nx_bridge._resolve_edges("last", "vertical_edges")
        assert res_vert == [vert_edge1, vert_edge2]

        # 4. X aligned edges
        res_x = nx_bridge._resolve_edges("last", "x_edges")
        assert res_x == [top_edge, bot_edge1]

        # 5. Y aligned edges
        res_y = nx_bridge._resolve_edges("last", "y_edges")
        assert res_y == [bot_edge2]

        # 6. Unrecognized reference raises SelectionError
        import pytest
        with pytest.raises(nx_bridge.SelectionError, match="Unrecognized or unsupported"):
            nx_bridge._resolve_edges("last", "invalid_edge_ref")

    finally:
        if orig_nxopen:
            sys.modules["NXOpen"] = orig_nxopen
        else:
            sys.modules.pop("NXOpen", None)
        if orig_nxopen_uf:
            sys.modules["NXOpen.UF"] = orig_nxopen_uf
        else:
            sys.modules.pop("NXOpen.UF", None)

