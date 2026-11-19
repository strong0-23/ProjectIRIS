@AGENTS.md

# Start here

Read `docs/WORKFLOW.md`. Tasks are GitHub issues labelled `wo`, assigned by the orchestrator.

- Given a task: act as the coding agent (`.claude/agents/coding-agent.md`), build it and hand back.
  Don't commit or push; the Git agent does that after review.
- Given a git or GitHub instruction: act as the Git agent (`.claude/agents/git-agent.md`).
