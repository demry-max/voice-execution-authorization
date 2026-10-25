# Security scope

This project is an experimental **agent-workflow confirmation layer**, not strong biometric identity proof, an OS sandbox, or a mandatory access-control system. Its purpose is to reduce accidental or casual misuse when another person has access to an agent chat window and the agent can modify local files.

## Known limitations

- The model can ignore skill instructions. Alternate tool paths are not automatically intercepted.
- A same-user process can edit the script, phrase, templates, or authorization state.
- A fixed phrase and basic speaker similarity do not establish liveness. Replayed, re-encoded, or synthetic speech may pass.
- The ten-minute window is shared across a state directory, not bound to the current chat or operation. An intruder may act during an active window.
- The prototype has no concurrency locking, tamper-resistant grant store, calibrated speaker-error rate, or independent security audit.
- Transcripts and untrusted audio path strings do not prove identity or trusted message origin.
- Installation is not proof that every filesystem-changing tool or subagent is covered.

For stronger protection, separate the authorization broker from the agent, restrict what the agent can write, and use short-lived, one-use grants bound to a specific operation and trusted session. Keep backups and use recoverable deletion.

## Sensitive material

Never open an issue or attach a pull request containing real audio, voice embeddings, private phrases, enrollment hashes, session grants, credentials, personal paths, or server addresses. Unit tests must use synthetic fixtures. Model weights have their own upstream licenses and are not distributed here.

## Reporting

Use the repository's private vulnerability-reporting feature when available. Otherwise open a minimal issue asking for a private reporting channel; do not include exploit details or sensitive files until a private channel is agreed. Do not test against other people's systems.
