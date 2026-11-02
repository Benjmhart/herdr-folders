"""python3 test_folders.py: the folder logic without a running herdr."""
import folders as F

a = {"pane_id": "w1:p1", "terminal_id": "term_a", "agent_session": {"value": "sess-a"}, "workspace_id": "w1"}
b = {"pane_id": "w2:p1", "terminal_id": "term_b", "workspace_id": "w2"}
s = {"folders": {"work": False, "games": True}, "members": {}}

F.put(s, a, "games")
assert F.folder_of(s, a) == "games" and F.folder_of(s, b) is None
# after a restart the pane id and terminal change but the session is the same
assert F.folder_of(s, dict(a, pane_id="w9:p1", terminal_id="term_new")) == "games"

lines = F.rows(s, [a, b], {})
assert lines == [("folder", "games"), ("folder", "work"), ("folder", None), ("agent", b)]  # games is collapsed
assert F.owner(lines, 3) is None and F.owner(lines, 1) == "work"

v = F.view(s)
assert v["filter"]["filters"][0]["filter"]["values"] == ["games"]
s["folders"]["games"] = False
assert "filter" not in F.view(s)
assert ("agent", a) in F.rows(s, [a, b], {})

F.put(s, a, None)
assert F.folder_of(s, a) is None and not s["members"]
print("ok")
