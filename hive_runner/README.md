# HIVE Local Runner

The HIVE Local Runner is a small, standalone service you run on **your own
computer**. It connects outbound to the HIVE backend over a WebSocket and
performs **real** file operations, strictly limited to one workspace folder you
approve. The HIVE web app never touches your filesystem directly.

## What it can do (MVP)
- List / read files
- Create & edit files
- Create directories
- Move / rename / copy files
- Inspect Git status/diff (read-only)

Everything is sandboxed to the approved workspace. It cannot access files
outside that folder, credentials, cookies, or system files, and it never runs
arbitrary shell commands.

## Run it
```bash
pip install websockets
python runner.py \
  --server wss://YOUR-HIVE-HOST/api/runner/ws \
  --code   YOUR-PAIRING-CODE \
  --workspace /absolute/path/to/your/project
```

In the HIVE web app: **Connect Workspace → generate a pairing code**, run the
command above, then **Approve** the requested permissions. You're connected.

Environment variable fallbacks: `HIVE_RUNNER_SERVER`, `HIVE_RUNNER_CODE`,
`HIVE_RUNNER_WORKSPACE`.
