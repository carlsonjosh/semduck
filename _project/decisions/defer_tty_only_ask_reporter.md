# Design Decision: Defer TTY-Only Ask Reporter

## Status

Accepted.

## Context

`semduck ask` now emits one-line stage updates to `stderr` while work is in progress. That solves
the immediate usability problem where the CLI appeared to hang during longer planner or summary
steps.

There is a natural follow-on improvement for interactive terminals:

- replace line-based status messages with a TTY-only reporter
- render a spinner or in-place status line for live sessions
- keep non-interactive runs line-oriented and log-friendly

That would improve the experience for users watching an interactive terminal, especially during
long planner runs.

At the same time, a TTY-aware reporter adds complexity that the current change does not need:

- terminal capability detection
- carriage-return or screen-control behavior
- cleanup on success, failure, or interruption
- interaction with redirected output, schedulers, and shell wrappers

## Decision

Keep the current default reporter as plain one-line `stderr` status messages and defer a TTY-only
reporter to future work.

The current boundary is:

- pipeline code emits progress events through a simple callback
- the CLI prints stable line-oriented messages to `stderr`
- final results remain on `stdout`

If we revisit live terminal UX later, it should be implemented as a different CLI-side reporter
that reuses the same progress callback API rather than changing the `ask` pipeline again.

## Why

This gives immediate progress visibility with minimal risk:

- works in interactive and non-interactive runs
- keeps JSON and text result output clean on `stdout`
- behaves well with shell redirection and logs
- avoids terminal-control bugs while the new staged ask pipeline is still settling

It also preserves the right extension point for future work. Because progress is already reported
through a callback, a later TTY-only reporter can swap in at the CLI boundary without changing the
semantic request planner, execution flow, or summary flow.

## Consequences

Current supported progress behavior:

- line-oriented `stderr` status messages for every `semduck ask` run

Deferred behavior:

- interactive spinner or in-place status rendering for TTY sessions

## What It Would Take To Add Later

If we add a TTY-only reporter later, it should:

1. activate only when attached to a live terminal
2. render on `stderr`, not `stdout`
3. suppress line-by-line status output while the spinner is active
4. fall back to the current line-based reporter when not in a TTY
5. preserve clean behavior for JSON output, redirected runs, and failures
