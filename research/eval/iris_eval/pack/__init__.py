"""Sample-only download of evaluation data ("data packs"), used by ``eval/fetch_pack.py``.

Every module in this subpackage uses the Python standard library only, so the owner can run the
fetch on a fresh Windows, macOS or Linux machine before installing anything. A test checks this
by importing ``eval/fetch_pack.py`` with site-packages disabled.

- ``safepath``: archive member names to safe, portable relative paths (Windows rules included).
- ``remote``: HTTP downloads with retries, and ``RemoteFile``, a seekable file over HTTP range
  requests so ``zipfile`` can read one member of a remote archive without fetching the rest.
- ``lock``: ``eval/locks/<dataset>.lock.json`` (sizes and sha256 of every file fetched).
- ``sources``: opening a manifest source (whole file, remote zip, per-file URL, figshare item).
- ``planners``: per-dataset rules that list a dataset's pages (IDs, categories, groups) from
  archive directories or index files, and name the files each page needs.
- ``fetch``: the run: licence gate, page list, split rule, frozen split check, fetch, lock,
  ``raw/<dataset>/pack.json`` and the summary.
"""
