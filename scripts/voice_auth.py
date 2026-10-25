#!/usr/bin/env python3
"""Local voice confirmation for an agent workflow, not an OS security boundary."""
import argparse
import getpass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import unicodedata

ROOT = Path(os.environ.get('VOICE_AUTH_HOME',
    str(Path(os.environ.get('HERMES_HOME', str(Path.home() / '.hermes'))) / 'voice-auth'))).expanduser()
MODEL = 'mlx-community/whisper-small-mlx'
THRESHOLD = 0.72
CENTROID_THRESHOLD = 0.68
SESSION_TTL_SECONDS = 600


def private_root():
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(ROOT, 0o700)


def save_json(name, data):
    private_root()
    path = ROOT / name
    # A restrictive creation mode avoids an initial world-readable credential window.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(data, stream, ensure_ascii=False)
        stream.write('\n')


def normalize_phrase(text):
    normalized = unicodedata.normalize('NFKC', text).casefold()
    return ''.join(c for c in normalized if not c.isspace() and not unicodedata.category(c).startswith('P'))


def phrase_matches(text, phrases):
    text = normalize_phrase(text)
    return any(normalize_phrase(p) and normalize_phrase(p) in text for p in phrases)


def load_phrase_config():
    try:
        config = json.loads((ROOT / 'phrase_config.json').read_text(encoding='utf-8'))
        phrases = config['phrases']
        if not isinstance(phrases, list) or not phrases or not all(
            isinstance(p, str) and normalize_phrase(p) for p in phrases
        ):
            raise ValueError('invalid_configuration')
        return config
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise ValueError('not_configured') from exc


def configure(language):
    phrase = getpass.getpass('Choose your private spoken phrase (hidden): ')
    confirmation = getpass.getpass('Repeat the same phrase (hidden): ')
    if not normalize_phrase(phrase) or phrase != confirmation:
        raise ValueError('phrase_confirmation_failed')
    save_json('phrase_config.json', {'phrases': [phrase], 'language': language})
    revoke_session()
    return {'configured': True, 'authorized': False}


def write_session(last_instruction_at):
    payload = {'authorized': True, 'last_instruction_at': last_instruction_at,
               'expires_at': last_instruction_at + SESSION_TTL_SECONDS,
               'ttl_seconds': SESSION_TTL_SECONDS}
    save_json('authorization_session.json', payload)
    return payload


def session_status(touch=False):
    now = time.time()
    try:
        payload = json.loads((ROOT / 'authorization_session.json').read_text(encoding='utf-8'))
        last = float(payload['last_instruction_at'])
        if (payload.get('authorized') is not True or not math.isfinite(last)
                or last > now or payload.get('expires_at') != last + SESSION_TTL_SECONDS
                or payload.get('ttl_seconds') != SESSION_TTL_SECONDS):
            raise ValueError('invalid_session')
    except (OSError, KeyError, TypeError, ValueError):
        return {'authorized': False, 'session_active': False, 'error': 'no_active_session'}
    remaining = SESSION_TTL_SECONDS - (now - last)
    if remaining <= 0:
        return {'authorized': False, 'session_active': False, 'error': 'session_expired'}
    if touch:
        payload = write_session(now)
        remaining = SESSION_TTL_SECONDS
    return {'authorized': True, 'session_active': True, 'touched': touch,
            'remaining_seconds': int(remaining), 'expires_at': payload['expires_at'],
            'ttl_seconds': SESSION_TTL_SECONDS}


def revoke_session():
    (ROOT / 'authorization_session.json').unlink(missing_ok=True)
    return {'authorized': False, 'session_active': False, 'revoked': True}


def audio_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def make_embedding(path):
    from resemblyzer import VoiceEncoder, preprocess_wav
    wav = preprocess_wav(path)
    if len(wav) < 16000 * 2:
        raise ValueError('audio_too_short')
    return VoiceEncoder().embed_utterance(wav)


def transcribe(path, config):
    import mlx_whisper
    result = mlx_whisper.transcribe(str(path), path_or_hf_repo=MODEL,
                                   language=config.get('language'))
    return result.get('text', '')


def load_profile():
    import numpy as np
    try:
        embeddings = np.load(ROOT / 'speaker_embeddings.npy', allow_pickle=False)
        hashes = json.loads((ROOT / 'enrollment_hashes.json').read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise ValueError('not_enrolled') from exc
    embeddings = np.atleast_2d(embeddings)
    if (embeddings.ndim != 2 or not np.isfinite(embeddings).all()
            or len(embeddings) != len(hashes) or not len(hashes)
            or (np.linalg.norm(embeddings, axis=1) == 0).any()):
        raise ValueError('invalid_profile')
    return embeddings, hashes


def enroll(path, append=False):
    import numpy as np
    candidate = make_embedding(path)
    digest = audio_hash(path)
    embeddings, hashes = np.atleast_2d(candidate), [digest]
    if append:
        previous, hashes = load_profile()
        if digest in hashes:
            raise ValueError('duplicate_enrollment_audio')
        embeddings = np.vstack([previous, candidate])
        hashes = hashes + [digest]
    private_root()
    fd = os.open(ROOT / 'speaker_embeddings.npy', os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        np.save(stream, embeddings, allow_pickle=False)
    save_json('enrollment_hashes.json', hashes)
    revoke_session()
    return {'enrolled': True, 'sample_count': len(hashes),
            'authorized': False, 'raw_audio_copied': False}


def verify(path):
    import numpy as np
    # A failed attempt closes a prior window; no old grant survives a failed check.
    revoke_session()
    config = load_phrase_config()
    enrolled, hashes = load_profile()
    replay_ok = audio_hash(path) not in hashes
    phrase_ok = bool(phrase_matches(transcribe(path, config), config['phrases']))
    candidate = make_embedding(path)
    norm = np.linalg.norm(candidate)
    centroid = enrolled.mean(axis=0)
    if not np.isfinite(candidate).all() or norm == 0 or np.linalg.norm(centroid) == 0:
        raise ValueError('invalid_embedding')
    scores = enrolled @ candidate / (np.linalg.norm(enrolled, axis=1) * norm)
    centroid_score = float(np.dot(candidate, centroid) / (norm * np.linalg.norm(centroid)))
    speaker_ok = bool(float(scores.max()) >= THRESHOLD and centroid_score >= CENTROID_THRESHOLD)
    authorized = bool(phrase_ok and speaker_ok and replay_ok)
    result = {'authorized': authorized, 'phrase_ok': phrase_ok,
              'speaker_ok': speaker_ok, 'replay_ok': replay_ok}
    # Do not print transcripts, voice features, recording hashes, or the private phrase.
    if authorized:
        session = write_session(time.time())
        result.update(session_active=True, ttl_seconds=SESSION_TTL_SECONDS,
                      expires_at=session['expires_at'])
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    setup = sub.add_parser('configure', help='Choose the phrase locally using hidden input')
    setup.add_argument('--language', default=None, help='Whisper language code; default auto-detect')
    for mode in ('enroll', 'enroll-add', 'verify'):
        sub.add_parser(mode).add_argument('audio', type=Path)
    for mode in ('status', 'touch', 'revoke'):
        sub.add_parser(mode)
    args = parser.parse_args(argv)
    try:
        if args.mode == 'configure':
            result = configure(args.language)
        elif args.mode in ('status', 'touch'):
            result = session_status(touch=args.mode == 'touch')
        elif args.mode == 'revoke':
            result = revoke_session()
        else:
            if args.mode == 'verify':
                revoke_session()
            path = args.audio.expanduser().resolve()
            if not path.is_file():
                raise ValueError('audio_not_found')
            result = verify(path) if args.mode == 'verify' else enroll(path, args.mode == 'enroll-add')
    except Exception as exc:
        # Fixed error vocabulary avoids echoing a path, phrase, or library secret.
        known = {'not_configured', 'not_enrolled', 'invalid_profile', 'audio_not_found',
                 'audio_too_short', 'invalid_embedding', 'duplicate_enrollment_audio',
                 'phrase_confirmation_failed'}
        error = str(exc) if isinstance(exc, ValueError) and str(exc) in known else 'verification_or_setup_failed'
        result = {'authorized': False, 'error': error}
    print(json.dumps(result))
    return 0 if any(result.get(k) is True for k in ('authorized', 'enrolled', 'configured', 'revoked')) else 1


if __name__ == '__main__':
    raise SystemExit(main())
