# Agent instructions

- How work flows, who does what, and where the owner is asked: `docs/WORKFLOW.md`.
- Roles: the Git agent (`.claude/agents/git-agent.md`) carries out every git and GitHub
  operation on instruction; the coding agent (`.claude/agents/coding-agent.md`) builds one task at
  a time and hands back for review. Agents execute what they are told; the orchestrator (the owner
  and Claude in his planning chat) decides and reviews.
- Never push to `main`, never rewrite pushed history.
- This repository is public. Never commit or write into issues, PRs or reports any private
  documents, photos of real documents, names, addresses, card or account numbers. Private data
  lives outside the repo (`OCR_PRIVATE_DATA`); held-out documents are never read by agents, only
  scored.
- Licences: code Apache 2.0; every model, dataset and dependency must allow commercial use and
  redistribution without revenue caps or non-commercial clauses (docs/DECISIONS.md O4).
- Free only: no paid services, no cloud OCR or AI API in the engine (O5).
- Decisions and architecture: docs/DECISIONS.md, docs/MODULES.md.
