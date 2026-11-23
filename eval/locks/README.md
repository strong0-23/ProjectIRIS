# Lock files

`<dataset>.lock.json` (schema `iris-lock/1`) is written by `eval/fetch_pack.py` on the first run
and verified on every later run. It holds, for every file the fetch wrote under
`eval/.data/raw/<dataset>/`, its size and sha256, and for every remote source its URL, size and
ETag (or figshare file id). File names are page IDs, which the frozen splits in `eval/splits/`
already list. No content: safe to commit.

A lock changes only by adding files (`--update-lock`) or by an orchestrator decision when a
source changed.
