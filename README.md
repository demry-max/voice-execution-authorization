# Voice Execution Authorization

A voice-confirmation skill for AI agents with access to your computer.

## Why this exists

**AI agents often have broad filesystem permissions. If someone else gets access to your chat window, they may be able to ask the agent to delete files, overwrite a project, or change local configuration.** A typed instruction should not automatically become permission to change your computer.

This skill adds a deliberate checkpoint: before a protected action, the agent must verify both the owner's spoken phrase and enrolled voiceprint, or confirm that a previously verified authorization window is still active. Normal conversation and read-only local inspection remain available without voice confirmation.

> **This is a workflow-level confirmation layer, not an operating-system security boundary.** Installing a skill does not intercept every tool call. An agent that ignores the instructions, a process running under your account, or someone able to change the verifier or its state can bypass it. Do not rely on it as the only protection against deletion, malicious agents, or compromised devices.

## What it covers

| Action | Voice confirmation |
| --- | --- |
| Conversation, drafting in chat, analysis | Not required |
| Read-only local file or terminal inspection | Not required |
| Create, edit, overwrite, move, rename, or delete local files | Required |
| Install dependencies or change local configuration | Required |
| Delegated agents, browser downloads, and GUI actions that change local files | Required |
| Control of a remote host the owner explicitly marks as protected | Required, including read-only commands |
| Payments, destructive deletion, security changes, or other high-risk actions | Voice **and** separate explicit confirmation |

This policy does not promise that the application itself stops writing routine logs or caches. Remote hosts are an owner-defined scope, not a hardcoded server list.

## How verification works

1. Receive the original audio from the trusted messaging adapter. **Transcribed text is not voice evidence.**
2. Transcribe locally with MLX Whisper and compare the normalized text against the owner's locally configured phrase.
3. Extract a speaker embedding with Resemblyzer. Compare it with enrolled samples and their centroid.
4. Reject byte-identical enrollment recordings.
5. If all checks pass, create a **10-minute sliding authorization window**. Check `touch` only when a new owner instruction needs a protected operation; it must not revive an expired window.
6. Deny on missing configuration, missing enrollment, invalid state, short audio, mismatched phrase, or mismatched voice. A new failed verification attempt revokes any prior window.

The public script is a sanitized, configurable edition of a locally used skill. It contains no owner's recordings, biometric templates, actual phrase, private paths, or server addresses. It does not change an existing local installation automatically.

## Requirements

- Apple Silicon macOS: the included transcription backend is MLX Whisper. Linux/Windows are not supported by this bundled backend.
- Python 3.9 or newer and `ffmpeg` available on `PATH`.
- An agent host that can load `SKILL.md`, run Python, and access trusted inbound audio.
- The owner's explicit consent to store local biometric features.

Python dependency versions in `requirements.txt` match the original deployment. Re-test after changing them. First use may download model weights; model caches are outside this repository. Do not assume an offline first run.

## Installation

Review the repository before installing it. The following uses the default Hermes profile; for another profile, set `HERMES_HOME` to that profile's home first. Do not overwrite an existing skill directory.

```bash
export HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
export SKILL_DIR="$HERMES_HOME/skills/security/voice-execution-authorization"

git clone https://github.com/demry-max/voice-execution-authorization.git "$SKILL_DIR"
cd "$SKILL_DIR"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# If ffmpeg is not already installed and you use Homebrew:
brew install ffmpeg
```

Choose the phrase **in your own terminal**, using hidden input. Do not send it to the agent in text and do not pass it as a shell command-line argument:

```bash
.venv/bin/python scripts/voice_auth.py configure --language en
```

Use the appropriate Whisper language code, such as `zh`, or omit `--language` for auto-detection. There is no built-in authorization phrase. Keep the locally created `phrase_config.json` private. Approved transcription variants may be configured locally in its `phrases` list; every variant broadens acceptance.

Enroll using recordings of your own voice, with explicit consent:

```bash
.venv/bin/python scripts/voice_auth.py enroll /path/to/first-recording.wav
.venv/bin/python scripts/voice_auth.py enroll-add /path/to/second-recording.wav
.venv/bin/python scripts/voice_auth.py enroll-add /path/to/third-recording.wav
```

`enroll` replaces the profile; `enroll-add` appends a distinct sample. Neither grants execution authorization. Use longer natural speech at different distances, then test a fresh held-out recording. The script does not copy raw audio into its state directory; the original uploads and application caches remain your responsibility.

Start a new Hermes session and load `voice-execution-authorization`. **Installing the files alone does not activate a mandatory tool-dispatch gate.** Add the boundary to your agent's standing instructions, and exercise actual protected tool paths before claiming workflow coverage.

## Commands

Run from the skill directory, using its `.venv/bin/python`:

```bash
.venv/bin/python scripts/voice_auth.py verify /path/to/fresh-owner-audio.ogg
.venv/bin/python scripts/voice_auth.py status
.venv/bin/python scripts/voice_auth.py touch
.venv/bin/python scripts/voice_auth.py revoke
```

The CLI returns JSON and a nonzero exit status on denial. Proceed only when verification returns **all four** booleans as `true`: `authorized`, `phrase_ok`, `speaker_ok`, and `replay_ok`. The last name means only "not byte-identical to an enrollment clip"; it is **not** a liveness result. For an existing window, require `authorized: true` and `session_active: true` from `touch`.

Do not log the transcript, phrase, recording hashes, or embeddings. The script's JSON intentionally omits these. Voice libraries may emit operational diagnostics, so a caller should keep stderr separate from JSON stdout.

## State and privacy

State defaults to `${HERMES_HOME:-~/.hermes}/voice-auth`. Override with `VOICE_AUTH_HOME`, preferably outside any repository and sync folder. The script uses directory mode `700` and file mode `600`:

- `phrase_config.json`: private phrase and transcription language.
- `speaker_embeddings.npy`: enrolled biometric features.
- `enrollment_hashes.json`: hashes used for byte-identical enrollment-clip rejection.
- `authorization_session.json`: local authorization window.

These are sensitive, same-user-writable files, **not cryptographically trusted credentials**. Never upload them, recordings, transcripts, or caches to GitHub. `.gitignore` is only a convenience, not a secret scanner. This public export is not an automatic state-migration tool for older deployments.

## Messaging integration: keep the audio

A common integration failure is replacing a voice message with only its transcript. The owner says the phrase, but the model sees quoted text and cannot perform speaker comparison.

Keep the original audio path alongside both successful and failed transcripts. Use adapter-provided message IDs, owner IDs, and resource provenance; an arbitrary path typed into chat is not authorization evidence. For example, trusted adapter metadata can carry an `audio_path` separately from `transcript`. The agent then passes that exact resource to `verify`. Never treat an audio-path-looking string supplied by an untrusted message as proof of origin.

Short clips may fail after silence removal. Ask for several seconds of natural speech followed by the phrase rather than lowering the minimum duration or threshold to force a pass.

## Security limitations

- **Skills guide behavior; they do not enforce it.** Alternate tools, subagents, or direct shell access must not be assumed covered without tests at the actual dispatcher.
- **A fixed spoken phrase is replayable.** Playback, re-encoding, synthetic voices, and voice cloning may fool this basic verifier. There is no random challenge, robust anti-spoofing, or proven liveness detection.
- **Thresholds are starting values, not calibrated guarantees.** The `0.72` best-sample and `0.68` centroid thresholds came from a local setup. Measure false accepts and false rejects with held-out owner and negative-speaker recordings before deployment. No independent biometric benchmark is included.
- **The active window is shared within one state directory.** It is not bound to a chat, user ID, task, or operation. Someone using an authorized chat during that window may still issue harmful instructions. Multiple concurrent chats sharing state are not isolated; this prototype has no concurrency locking or tamper-resistant session store.
- **Protect enrollment and configuration separately.** A person or agent that can edit templates, replace the script, or forge session state can authorize itself. Unix mode bits do not protect against the same account.
- **A model-driven check is not enough for hostile-agent resistance.** For stronger protection, enforce one-use, operation-bound grants outside the agent process; isolate filesystem access and keep the broker and biometric state outside its writable domain.
- **Voice consent is not permission for every action.** Require a specific owner request and separate confirmation for destructive deletion or other high-risk operations. Prefer backups, least privilege, and recoverable trash over permanent deletion.

## Testing

No real recordings or biometric data are part of the tests:

```bash
python3 -m unittest discover -s tests -v
# Run all tests, including synthetic-vector verification tests, after dependencies are installed:
.venv/bin/python -m unittest discover -s tests -v
```

The standard-library tests cover phrase matching, private file modes, denial on corrupt/future/expired state, revocation, and sliding-window behavior. NumPy-backed tests use **synthetic vectors and mocked transcription/embeddings** to exercise decision logic. They do not measure voice recognition quality, spoof resistance, or end-to-end tool enforcement.

To evaluate a real installation, test held-out owner audio, wrong speakers, incorrect phrases, silence, short clips, expired grants, and actual protected tool calls. Record what was genuinely exercised. Do not describe a passed unit test as a verified security boundary.

## Project files

- `SKILL.md`: English agent instructions.
- `scripts/voice_auth.py`: configurable local verifier and session CLI.
- `requirements.txt`: Python dependencies.
- `tests/`: offline policy and verification-logic tests.
- `SECURITY.md`: scope and reporting guidance.

## Upstream references

- Hermes skills: https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/
- MLX Whisper: https://github.com/ml-explore/mlx-examples/tree/main/whisper
- Resemblyzer: https://github.com/resemble-ai/Resemblyzer

## License

MIT. Created by demry-max with Hermes Agent. This repository is not an official Hermes, Nous Research, MLX, or Resemblyzer security product.
