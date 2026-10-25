"""Verification orchestration uses synthetic vectors, never real voice samples."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    import numpy as np
except ImportError:
    np = None

MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'voice_auth.py'


@unittest.skipIf(np is None, 'Install requirements.txt for vector tests')
class VerificationTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('public_voice_verify', MODULE)
        self.va = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.va)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.va.ROOT = Path(self.temp.name) / 'state'
        self.va.save_json('phrase_config.json', {'phrases': ['my demo phrase'], 'language': 'en'})
        self.audio = Path(self.temp.name) / 'synthetic.bin'
        self.audio.write_bytes(b'synthetic test fixture, not a recording')
        self.addCleanup(patch.stopall)
        patch.object(self.va, 'make_embedding', return_value=np.array([1., 0.])).start()
        patch.object(self.va, 'transcribe', return_value='my demo phrase').start()
        patch.object(self.va, 'load_profile', return_value=(np.array([[1., 0.], [1., 0.]]), ['a', 'b'])).start()

    def test_all_checks_create_window(self):
        result = self.va.verify(self.audio)
        self.assertTrue(all(result[k] is True for k in ('authorized', 'phrase_ok', 'speaker_ok', 'replay_ok')))
        self.assertTrue(self.va.session_status()['session_active'])
        self.assertNotIn('transcript', result)

    def test_wrong_phrase_denies_even_if_speaker_matches(self):
        self.va.transcribe.return_value = 'wrong phrase'
        result = self.va.verify(self.audio)
        self.assertFalse(result['authorized'])
        self.assertTrue(result['speaker_ok'])
        self.assertFalse(self.va.session_status()['authorized'])

    def test_wrong_speaker_denies_even_if_phrase_matches(self):
        self.va.make_embedding.return_value = np.array([0., 1.])
        result = self.va.verify(self.audio)
        self.assertFalse(result['authorized'])
        self.assertTrue(result['phrase_ok'])

    def test_exact_enrollment_replay_denies(self):
        self.va.load_profile.return_value = (np.array([[1., 0.]]), [self.va.audio_hash(self.audio)])
        self.assertFalse(self.va.verify(self.audio)['replay_ok'])
        self.assertFalse(self.va.session_status()['authorized'])

    def test_failed_attempt_revokes_previous_window(self):
        self.va.write_session(self.va.time.time())
        self.va.transcribe.return_value = 'wrong phrase'
        self.va.verify(self.audio)
        self.assertFalse(self.va.session_status()['authorized'])

    def test_short_audio_cannot_leave_prior_grant(self):
        self.va.write_session(self.va.time.time())
        self.va.make_embedding.side_effect = ValueError('audio_too_short')
        with self.assertRaisesRegex(ValueError, 'audio_too_short'):
            self.va.verify(self.audio)
        self.assertFalse(self.va.session_status()['authorized'])

    def test_invalid_vector_fails_closed(self):
        self.va.make_embedding.return_value = np.array([float('nan'), 0.])
        with self.assertRaisesRegex(ValueError, 'invalid_embedding'):
            self.va.verify(self.audio)
        self.assertFalse(self.va.session_status()['authorized'])

    def test_enrollment_does_not_authorize(self):
        result = self.va.enroll(self.audio)
        self.assertTrue(result['enrolled'])
        self.assertFalse(result['authorized'])
        self.assertFalse(self.va.session_status()['authorized'])

    def test_duplicate_enrollment_refused(self):
        self.va.load_profile.return_value = (np.array([[1., 0.]]), [self.va.audio_hash(self.audio)])
        with self.assertRaisesRegex(ValueError, 'duplicate_enrollment_audio'):
            self.va.enroll(self.audio, append=True)

    def test_missing_audio_is_json_denial(self):
        self.va.write_session(self.va.time.time())
        stream = io.StringIO()
        with patch('sys.stdout', stream):
            code = self.va.main(['verify', str(Path(self.temp.name) / 'missing.wav')])
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(stream.getvalue())['error'], 'audio_not_found')
        self.assertFalse(self.va.session_status()['authorized'])


if __name__ == '__main__':
    unittest.main()
