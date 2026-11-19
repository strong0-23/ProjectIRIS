# Workflow

How work moves from a decision to merged code: who does what, and where the owner is asked.

## Roles

| Role | Who | Does | Never does |
|---|---|---|---|
| **Orchestrator** | The owner and Claude in his planning chat | Decides what to build, writes each task, tells the agents what to do, reviews every result, decides what gets merged | — |
| **Git agent** | `.claude/agents/git-agent.md` | Every git and GitHub operation, on instruction: repos, branches, commits, pushes, PRs, merges, issues, releases | Make project decisions, write code |
| **Coding agent** | Claude Code, `.claude/agents/coding-agent.md` | Builds one task at a time: code, tests, docs, report. Hands back for review | Commit, push, merge, touch GitHub |
| *Test agent* | planned | Evaluation set, test suites, scoring runs, trying to break things | — |
| *Design agent* | planned | Interfaces, document model, demo app UI, docs | — |

The agents execute; the orchestrator decides and reviews. Within the orchestrator, Claude does the
detailed review and brings the owner a short summary of every finished task. The owner can step in
on any of them.

## The cycle

```
1. Orchestrator   decide the next task; Claude writes it as a GitHub issue (scope, folders,
                  checks, acceptance line)
2. Git agent      create the issue and the task branch / worktree
3. Coding agent   build it, run the checks, write the report, hand back
4. Git agent      commit and push the branch, open the PR (Closes #n)
5. Orchestrator   review: Claude re-runs the checks, reads the diff, checks scope, licences (O4),
                  privacy and the acceptance line, then sends the owner a short review
6. Orchestrator   decision: merge, or send back with changes (back to step 3)
7. Git agent      merge as instructed; tag or release when told
```

## When the owner decides

- **Every new milestone** (a set of tasks with a goal) before work starts.
- **Every finished task**: the owner receives a short review. Routine tasks inside an approved
  milestone are merged on Claude's call unless the owner says otherwise.
- **Gated tasks** are merged only on the owner's yes. A task is gated when it:
  - changes the document model or another interface something already uses;
  - adds a model, dataset or dependency with a licence the decisions don't already cover;
  - adds a material dependency (a runtime, a framework, a model over 50 MB);
  - touches branch protection, secrets, CI permissions or release publishing;
  - lowers a check, a security control or an acceptance line.
- **Any "Decision needed"** an agent raises that recorded decisions don't settle.
- **Never**: anything that costs money (O5), anything that would publish private data.

## Where work is tracked

- **GitHub issues** are the task list: one issue per task, label `wo`, a status label
  (`status:ready`, `status:in-progress`, `status:in-review`, `status:blocked`), and the milestone.
- **PRs** close their issue. The full report lives in `docs/reports/`.
- **`docs/DECISIONS.md`** records every decision; **`docs/MODULES.md`** the architecture.
- The repository is public: nothing private ever goes into an issue, PR, comment or commit.

## Standing rules for every agent

1. Act on instructions; when one is unclear or breaks a rule, stop and ask.
2. Never push to `main` directly; never rewrite pushed history.
3. Nothing private in the repository, issues, PRs or reports (AGENTS.md).
4. Held-out evaluation documents are never read by any agent, only scored.
5. Licences under O4; free only under O5.
6. Measure on unseen documents; nothing shaped around one example (E2). Never silent (E3).
7. Never claim a check that was not run.

## Guardrails on GitHub

Instructions are not enforcement, so `main` is protected on GitHub: changes only through a PR,
required checks must pass once CI exists, no force-pushes. All agents share one set of GitHub
credentials, so roles rest on these instructions plus branch protection.
