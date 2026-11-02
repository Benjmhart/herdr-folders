# herdr-folders

A [herdr](https://herdr.dev) plugin: drag your agents into folders, and collapse the folders you are not using.
Collapsed agents keep running; they just leave the Agents panel until you need them.

```
herdr folders
drag agent→folder · click folder: fold · enter: go · n new · r rename · d delete · m move · u unfile · q quit
▸ side-projects (3)
▾ work (2)
    ● api        Refactor auth middleware
    ○ frontend   Fix the login form
  Unfiled
    ○ scratch    ~/tmp
```

## Install

```sh
herdr plugin install Benjmhart/herdr-folders
```

Needs herdr 0.9.3 or later and `python3` (standard library only). Linux and macOS.

Bind a key to open the popup, in `~/.config/herdr/config.toml`:

```toml
[[keys.command]]
key = "prefix+g"
type = "plugin_action"
command = "benjmhart.folders.open"
description = "agent folders"
```

Optionally show each agent's folder in the sidebar (`$folder`):

```toml
[ui.sidebar.agents]
rows = [
  ["state_icon", "workspace", "tab", { token = "$folder", dim = true }],
  ["agent"],
]
```

## Use

- **Drag** an agent onto a folder (its header or any agent in it) to move it there; drop it under *Unfiled* to unfile it.
- **Click** a folder to collapse or expand it.
- Keys: `j`/`k` select, `space`/`enter` fold a folder, `enter` on an agent jumps to it, `n` new folder (the selected
  agent goes into it), `m` move to a folder by name, `u` unfile, `r` rename, `d` delete a folder (its agents become
  unfiled), `q` close.

## What it does in herdr

- Every agent in a folder carries a `folder` pane token. The Agents panel is sorted by folder, so folders stay together.
- Agents in a collapsed folder are hidden from the Agents panel, **except** while you are in their workspace and while
  one is blocked or done (waiting for you). The Goto picker, notifications and attention counts still see every agent.
- This uses herdr's single plugin Agent view (`agent.view.set`). Another plugin that sets the Agent view will replace
  this one's until the next change here or the next restart.
- Folders are kept in `$HERDR_PLUGIN_STATE_DIR/folders.json`, by each agent's session id and terminal id (pane ids
  change on restart), and reapplied at startup and whenever herdr detects an agent. An agent that starts a fresh
  session in a new terminal starts unfiled.

## Development

```sh
herdr plugin link .        # run from this checkout
python3 test_folders.py    # the folder logic, no herdr needed
```

MIT licensed.
