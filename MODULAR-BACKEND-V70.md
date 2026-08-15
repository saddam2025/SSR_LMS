# V70 Modular Backend — Student Learning Runtime

`app/routers/learning_runtime.py` now owns the legacy browser/mobile learning runtime routes for students. The public HTTP contract is unchanged.

The router currently uses a temporary compatibility bridge to shared helpers in `app.main`. This intentionally avoids duplicating access-control, completion, rendering, and signing logic during the migration. The next modularization step should move those shared helpers into dedicated services (`learning_access`, `assessment`, `playback`) and remove the bridge.
