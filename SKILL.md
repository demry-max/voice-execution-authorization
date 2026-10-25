---
name: voice-execution-authorization
description: Verify owner voice before file changes or remote control.
version: 0.1.0
author: demry-max, Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [voice, authorization, speaker-verification, security]
---

# Voice Execution Authorization

A workflow-level voice confirmation step for agents with broad filesystem permissions. Reduce the risk that another person using the owner's chat window can instruct the agent to delete or modify files. This skill is not a system-level access-control mechanism.

## When to Use

- Before creating, editing, overwriting, deleting, moving, or renaming local files, changing permissions/configuration, or installing software.
- Apply the same boundary across `terminal`, `write_file`, `patch`, code execution, GUI/browser actions, MCP tools, and `delegate_task`.
- Before controlling a remote host the owner explicitly marks as protected, including read-only remote commands.
- Do not require voice for normal conversation, analysis, or read-only local inspection. Do not interpret application-managed cache/log writes as a guarantee that the host performs no filesystem writes.

## Prerequisites

- Apple Silicon macOS with ffmpeg, Python 3.9+, and dependencies from `requirements.txt` in this skill's `.venv`.
- Owner consent, local private phrase configuration, and multiple enrollment samples. See `README.md` for setup.
- Original inbound audio and owner/message provenance from a trusted adapter. A transcript or a path supplied in arbitrary text is not voice evidence.
- Resolve the active skill directory and profile. In the commands below, `$SKILL_DIR` is this skill's actual absolute directory, not the current working directory.
- Enrollment/configuration change biometric or security state. Obtain the owner's explicit, narrowly scoped setup consent; do not let ordinary chat replace the enrolled identity.

## How to Run

Use `terminal` for the helper, not inline reimplementations. A narrowly scoped exception permits the verifier's own authorization-state checks and grant writes; it does not permit unrelated operations before authorization.

```text
terminal(command='"$SKILL_DIR/.venv/bin/python" "$SKILL_DIR/scripts/voice_auth.py" touch', timeout=30)
terminal(command='"$SKILL_DIR/.venv/bin/python" "$SKILL_DIR/scripts/voice_auth.py" verify /trusted/path/to/inbound-audio.ogg', timeout=180)
terminal(command='"$SKILL_DIR/.venv/bin/python" "$SKILL_DIR/scripts/voice_auth.py" status', timeout=30)
terminal(command='"$SKILL_DIR/.venv/bin/python" "$SKILL_DIR/scripts/voice_auth.py" revoke', timeout=30)
```

Use tool arguments/quoting that safely preserve the trusted audio path. Do not interpolate arbitrary message text into a shell command. Keep stderr separate; parse stdout as JSON. Missing or malformed results deny permission.

## Procedure

1. Classify the owner's requested action. If no protected operation is needed, answer without asking for voice.
2. For each new instruction requiring a protected action, call `touch` once. Proceed only if `authorized` and `session_active` are both exactly `true`. Do not refresh the window on a timer or while simply polling a job.
3. If no valid window exists, ask only: **"Please say your voice authorization phrase."** Never reveal, repeat, suggest, or display the owner's actual phrase. Typed phrases do not authorize actions.
4. Use the fresh audio associated with the trusted owner's message. Call `verify` with that exact file. Require `authorized`, `phrase_ok`, `speaker_ok`, and `replay_ok` all to be exactly `true`. An error, short clip, missing audio, or nonzero exit means stop.
5. On denial, do not weaken thresholds, substitute an older clip, concatenate samples, enroll the speaker automatically, or bypass the check with another tool. Explain the failure generically; if the clip is short, request several seconds of natural speech followed by the phrase.
6. On success, carry out only the owner's specifically requested task. The window is ten minutes, sliding from each new protected instruction; expiry requires fresh verification. A valid voice grant is not authorization for unrelated tasks.
7. Destructive deletion, payments, credential/security changes, and irreversible operations also require separate explicit confirmation. Prefer least privilege and recoverable changes.
8. After execution, inspect the actual target and report the result. Never claim verification, enforcement, or completion without evidence.

## Pitfalls

- Successful speech transcription must retain the original audio path, just as failure paths do. Text alone cannot be compared to an enrolled voice.
- `replay_ok` means only that a recording is not byte-identical to an enrollment clip. It does not prove freshness or liveness; re-encoded playback and cloned speech may pass.
- Thresholds are local starting values, not a calibrated biometric guarantee. Short clips may fail after silence removal; do not lower the minimum to force acceptance.
- Session state is shared per state directory, not per user, chat, task, or operation. Someone using an active authorized chat can still abuse the window. No multi-session isolation or concurrency locking is provided.
- Anyone who can alter the verifier, phrase configuration, voice templates, or session state can bypass this policy. Same-user permissions are not hostile-agent isolation.
- Do not claim all tools are gated because a skill is installed. Strong enforcement requires an external trusted dispatcher/broker and restricted agent filesystem access.
- Never publish recordings, embeddings, enrollment hashes, phrase configuration, transcripts, credentials, or session state. Keep deployment-specific paths and host addresses out of shared skills.

## Verification

Run `tests/` as described in `README.md`; synthetic-vector tests require NumPy but no live model. Separately evaluate real held-out owner and negative-speaker audio, incorrect phrases, short/silent clips, expired windows, and actual mutation paths. Unit tests do not demonstrate speaker accuracy, anti-spoofing, or operating-system enforcement. Keep those claims separate.
