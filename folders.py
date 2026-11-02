#!/usr/bin/env python3
"""herdr-folders: drag herdr agents into folders and collapse the folders you are not using. Agents keep running.

`folders.py ui` is the popup (mouse and keys), `apply` re-tags agents and reinstalls the Agents view (run at startup and
when an agent appears), `open` opens the popup. Standard library only.

How it shows up in herdr: each agent pane carries a `folder` token, the Agents panel is sorted by it, and agents in a
collapsed folder are hidden there, except while you are in their workspace or one is blocked or done. The Goto
picker, notifications and attention counts still see every agent.
"""
import curses, json, os, socket, subprocess, sys

SOURCE = "plugin:" + os.environ.get("HERDR_PLUGIN_ID", "herdr-folders")
STATE = os.path.join(os.environ.get("HERDR_PLUGIN_STATE_DIR", "."), "folders.json")
HERDR = os.environ.get("HERDR_BIN_PATH", "herdr")
ICON = {"working": "●", "blocked": "!", "done": "✓", "idle": "○"}


# --- herdr ------------------------------------------------------------------------------------------------------

def call(method, params):
    with socket.socket(socket.AF_UNIX) as s:
        s.connect(os.environ["HERDR_SOCKET_PATH"])
        s.sendall((json.dumps({"id": "folders", "method": method, "params": params}) + "\n").encode())
        resp = json.loads(s.makefile().readline())
    if "error" in resp:
        raise RuntimeError(f"{method}: {resp['error']}")
    return resp["result"]


def agents():
    return call("agent.list", {})["agents"]


def labels():
    return {w["workspace_id"]: w.get("label") or w["workspace_id"] for w in call("workspace.list", {})["workspaces"]}


# --- state: {"folders": {name: collapsed}, "members": {agent key: folder}} ----------------------------------------

def load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {"folders": {}, "members": {}}


def save(state):
    with open(STATE + ".tmp", "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    os.replace(STATE + ".tmp", STATE)


def keys(agent):
    """Pane ids change on restart, so membership is kept by the agent's session and its terminal."""
    k = []
    if (agent.get("agent_session") or {}).get("value"):
        k.append("s:" + agent["agent_session"]["value"])
    if agent.get("terminal_id"):
        k.append("t:" + agent["terminal_id"])
    return k or ["p:" + agent["pane_id"]]


def folder_of(state, agent):
    for k in keys(agent):
        f = state["members"].get(k)
        if f in state["folders"]:
            return f
    return None


def put(state, agent, folder):
    # ponytail: members is never pruned; a few bytes per agent ever filed, prune if the file ever matters.
    for k in keys(agent):
        if folder:
            state["members"][k] = folder
        else:
            state["members"].pop(k, None)


def view(state):
    """The Agents panel: grouped by folder; collapsed folders hidden unless here or waiting for you."""
    collapsed = sorted(n for n, c in state["folders"].items() if c)
    v = {"source": SOURCE, "label": "folders" + (f" · {len(collapsed)} collapsed" if collapsed else ""),
         "sort": [{"field": {"token": "folder"}, "order": "asc"}, {"field": "workspace_order", "order": "asc"},
                  {"field": "pane_order", "order": "asc"}]}
    if collapsed:
        v["filter"] = {"op": "any", "filters": [
            {"op": "not", "filter": {"op": "in", "field": {"token": "folder"}, "values": collapsed}},
            {"op": "eq", "field": "workspace_id", "value": {"context": "current_workspace_id"}},
            {"op": "in", "field": "status", "values": ["blocked", "done"]},
        ]}
    return v


def apply(state, live=None):
    live = agents() if live is None else live
    for a in live:
        f = folder_of(state, a)
        if (a.get("tokens") or {}).get("folder") != f:
            call("pane.report_metadata", {"pane_id": a["pane_id"], "source": SOURCE, "tokens": {"folder": f}})
    if any(folder_of(state, a) for a in live):
        call("agent.view.set", view(state))
    else:
        call("agent.view.clear", {"source": SOURCE})


# --- the popup ----------------------------------------------------------------------------------------------------

def rows(state, live, names):
    """Screen lines: ("folder", name) headers, each followed by its agents unless collapsed; unfiled agents last."""
    out = []
    groups = {}
    for a in live:
        groups.setdefault(folder_of(state, a), []).append(a)
    for name in sorted(state["folders"]):
        out.append(("folder", name))
        if not state["folders"][name]:
            out += [("agent", a) for a in groups.get(name, [])]
    out.append(("folder", None))
    out += [("agent", a) for a in groups.get(None, [])]
    return out


def owner(lines, i):
    """The folder a screen line belongs to: the nearest header at or above it."""
    for kind, x in reversed(lines[:i + 1]):
        if kind == "folder":
            return x
    return None


def text(state, live, line, names, width):
    kind, x = line
    if kind == "folder":
        if x is None:
            return "  Unfiled"
        n = sum(folder_of(state, a) == x for a in live)
        return f"{'▸' if state['folders'][x] else '▾'} {x} ({n})"
    title = x.get("terminal_title_stripped") or x.get("cwd", "")
    return f"    {ICON.get(x.get('agent_status'), '?')} {names.get(x['workspace_id'], x['workspace_id'])}  {title}"[:width]


HELP = "drag agent→folder · click folder: fold · enter: go · n new · r rename · d delete · m move · u unfile · q quit"


def prompt(scr, label, initial=""):
    h, w = scr.getmaxyx()
    curses.curs_set(1)
    s = initial
    while True:
        scr.move(h - 1, 0)
        scr.clrtoeol()
        scr.addstr(h - 1, 0, (label + s)[:w - 1])
        c = scr.get_wch()
        if c in ("\n", "\r", curses.KEY_ENTER):
            break
        if c == "\x1b":
            s = ""
            break
        if c in (curses.KEY_BACKSPACE, "\x7f", "\b"):
            s = s[:-1]
        elif isinstance(c, str) and c.isprintable():
            s += c
    curses.curs_set(0)
    return s.strip()[:40]


def ui(scr):
    curses.curs_set(0)
    curses.use_default_colors()
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    curses.mouseinterval(0)  # separate press and release, so a drag is press here, release there
    scr.timeout(2000)  # pick up new agents and status changes
    state, sel, drag, msg = load(), 1, None, ""

    def change():
        save(state)
        apply(state, live)

    while True:
        live, names = agents(), labels()
        lines = rows(state, live, names)
        sel = max(0, min(sel, len(lines) - 1))
        h, w = scr.getmaxyx()
        top = 2
        scr.erase()
        scr.addstr(0, 0, "herdr folders"[:w - 1], curses.A_BOLD)
        scr.addstr(1, 0, HELP[:w - 1], curses.A_DIM)
        for i, line in enumerate(lines[:h - top - 1]):
            attr = curses.A_REVERSE if i == sel else 0
            if line[0] == "folder":
                attr |= curses.A_BOLD
            if drag is not None and i == drag:
                attr |= curses.A_UNDERLINE
            scr.addstr(top + i, 0, text(state, live, line, names, w - 1), attr)
        if msg:
            scr.addstr(h - 1, 0, msg[:w - 1], curses.A_DIM)
        scr.refresh()

        try:
            c = scr.get_wch()
        except curses.error:
            continue  # timeout: refresh
        msg = ""
        kind, x = lines[sel]
        if c == curses.KEY_MOUSE:
            try:
                _, mx, my, _, b = curses.getmouse()
            except curses.error:
                continue
            i = my - top
            if not 0 <= i < len(lines):
                drag = None
                continue
            if b & curses.BUTTON1_PRESSED:
                sel, drag = i, i
            elif b & (curses.BUTTON1_RELEASED | curses.BUTTON1_CLICKED) and drag is not None:
                src, drag = lines[drag], None
                if i == sel and src[0] == "folder" and src[1] is not None:
                    state["folders"][src[1]] ^= True
                    change()
                elif src[0] == "agent" and owner(lines, i) != folder_of(state, src[1]):
                    put(state, src[1], owner(lines, i))
                    change()
                    msg = f"moved to {owner(lines, i) or 'Unfiled'}"
            elif b & curses.BUTTON4_PRESSED:
                sel -= 1
            elif b & getattr(curses, "BUTTON5_PRESSED", 0):
                sel += 1
        elif c in ("q", "\x1b"):
            return
        elif c in ("j", curses.KEY_DOWN):
            sel += 1
        elif c in ("k", curses.KEY_UP):
            sel -= 1
        elif c in (" ", "\n", "\r", curses.KEY_ENTER) and kind == "folder" and x is not None:
            state["folders"][x] ^= True
            change()
        elif c in ("\n", "\r", curses.KEY_ENTER) and kind == "agent":
            subprocess.run([HERDR, "agent", "focus", x["pane_id"]], capture_output=True)
            return
        elif c == "n":
            name = prompt(scr, "new folder: ")
            if name:
                state["folders"].setdefault(name, False)
                if kind == "agent":
                    put(state, x, name)
                change()
        elif c == "m" and kind == "agent":
            name = prompt(scr, "move to folder (new ok, empty = unfile): ", folder_of(state, x) or "")
            if name:
                state["folders"].setdefault(name, False)
            put(state, x, name or None)
            change()
        elif c == "u" and kind == "agent":
            put(state, x, None)
            change()
        elif c == "r" and kind == "folder" and x is not None:
            name = prompt(scr, "rename to: ", x)
            if name and name not in state["folders"]:
                state["folders"][name] = state["folders"].pop(x)
                state["members"] = {k: name if f == x else f for k, f in state["members"].items()}
                change()
        elif c == "d" and kind == "folder" and x is not None:
            if prompt(scr, f"delete folder {x}? its agents become unfiled (y/N) ").lower() == "y":
                del state["folders"][x]
                state["members"] = {k: f for k, f in state["members"].items() if f != x}
                change()


def main(cmd):
    if cmd == "apply":
        apply(load())
    elif cmd == "ui":
        curses.wrapper(ui)
    elif cmd == "open":
        call("plugin.pane.open", {"plugin_id": os.environ["HERDR_PLUGIN_ID"], "entrypoint": "ui", "focus": True})
    else:
        sys.exit("usage: folders.py ui|apply|open")


if __name__ == "__main__":
    try:
        main(sys.argv[1] if len(sys.argv) > 1 else "")
    except RuntimeError as e:
        sys.exit(f"herdr-folders: {e}")
