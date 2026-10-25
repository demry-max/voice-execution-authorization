"""Deterministic policy tests; no microphone, network, or voice model required."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'voice_auth.py'


class PolicyTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('voice_auth_public', MODULE)
        self.va = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.va)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.va.ROOT = Path(self.temp.name) / 'private-state'

    def test_missing_session_denies(self):
        self.assertFalse(self.va.session_status()['authorized'])

    def test_fresh_session_allows(self):
        with patch.object(self.va.time, 'time', return_value=1000):
            self.va.write_session(1000)
            self.assertTrue(self.va.session_status()['session_active'])

    def test_touch_extends_active_session(self):
        self.va.write_session(1000)
        with patch.object(self.va.time, 'time', return_value=1050):
            result = self.va.session_status(touch=True)
        self.assertTrue(result['authorized'])
        self.assertEqual(result['expires_at'], 1650)

    def test_expired_touch_cannot_revive_session(self):
        self.va.write_session(1000)
        with patch.object(self.va.time, 'time', return_value=1600):
            self.assertFalse(self.va.session_status(touch=True)['authorized'])

    def test_corrupt_session_denies(self):
        self.va.ROOT.mkdir()
        (self.va.ROOT / 'authorization_session.json').write_text('{broken')
        self.assertFalse(self.va.session_status()['authorized'])

    def test_future_timestamp_denies(self):
        self.va.write_session(2000)
        with patch.object(self.va.time, 'time', return_value=1000):
            self.assertFalse(self.va.session_status()['authorized'])

    def test_nonfinite_timestamp_denies(self):
        self.va.write_session(float('inf'))
        self.assertFalse(self.va.session_status()['authorized'])

    def test_unauthorized_session_flag_denies(self):
        self.va.write_session(1000)
        p = self.va.ROOT / 'authorization_session.json'
        d = json.loads(p.read_text())
        d['authorized'] = False
        p.write_text(json.dumps(d))
        with patch.object(self.va.time, 'time', return_value=1001):
            self.assertFalse(self.va.session_status()['authorized'])

    def test_revoke_ends_session(self):
        self.va.write_session(1000)
        self.va.revoke_session()
        self.assertFalse(self.va.session_status()['authorized'])

    @unittest.skipUnless(os.name == 'posix', 'POSIX mode bits')
    def test_private_state_permissions(self):
        self.va.write_session(1000)
        self.assertEqual(self.va.ROOT.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.va.ROOT / 'authorization_session.json').stat().st_mode & 0o777, 0o600)

    def test_phrase_normalizes_case_spaces_and_punctuation(self):
        self.assertTrue(self.va.phrase_matches('My, demo phrase!', ['my demo phrase']))

    def test_phrase_rejects_incorrect_words(self):
        self.assertFalse(self.va.phrase_matches('different words', ['my demo phrase']))

    def test_empty_phrase_denies(self):
        self.assertFalse(self.va.phrase_matches('anything', ['  ']))

    def test_longer_speech_may_contain_phrase(self):
        self.assertTrue(self.va.phrase_matches('I authorize this: my demo phrase.', ['my demo phrase']))

    def test_no_configuration_fails_closed(self):
        with self.assertRaises(ValueError):
            self.va.load_phrase_config()


if __name__ == '__main__':
    unittest.main()
