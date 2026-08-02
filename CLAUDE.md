@AGENTS.md

## Claude Code

The imported file above is the full instruction set and applies here in its entirety. It is written
addressing Codex, but every rule in it — product boundary, profile isolation, persistence, secrets,
medical safety, the necessity ladder, coding standards, and the testing policy — binds Claude
equally. Nothing is restated below, so there is no summary that can drift out of sync with it.

The one place Claude differs is delegation.

`AGENTS.md` §7 names six agents in `.codex/agents/`. Those belong to Codex and are spawned when
Codex is the orchestrator. Claude cannot invoke them by name: the `codex` MCP tool exposes no agent
parameter, so a Claude-initiated Codex call expresses the same intent through `model`, `sandbox`,
and the prompt instead. Route work the way §7 describes even though the mechanism differs — in
particular, anything touching profile isolation, exports, AI health context, FHIR patient
attachment, or destructive database behavior warrants the high-assurance treatment §7 reserves for
`privacy_safety_reviewer`.

The §7 delegation limits apply unchanged to Claude's own subagents: prefer zero for small tasks, at
most three unless the work is genuinely independent, and never let a subagent spawn another.
