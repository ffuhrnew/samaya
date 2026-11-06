import unittest
from types import SimpleNamespace

from RNS.vendor import umsgpack

from samaya import protocol as P
from samaya.server import SamayaServer

NOW = 1_793_000_000.5


def payload(synced_check, require_sync=True):
    fake = SimpleNamespace(
        RNS=SimpleNamespace(vendor=SimpleNamespace(umsgpack=umsgpack)),
        require_sync=require_sync, _sync_check=synced_check, _clock=lambda: NOW,
    )
    return SamayaServer.announce_payload(fake)


class AnnouncePayloadTest(unittest.TestCase):
    def test_synced_server_announces_time(self):
        r = P.parse_response(umsgpack.unpackb(payload(lambda: True)))
        self.assertEqual((r.unix, r.ms, r.synced), (1_793_000_000, 500, True))

    def test_unknown_sync_still_announces_time(self):
        r = P.parse_response(umsgpack.unpackb(payload(lambda: None)))
        self.assertEqual(r.unix, 1_793_000_000)

    def test_unsynced_server_announces_no_time(self):
        body = umsgpack.unpackb(payload(lambda: False))
        self.assertNotIn(P.K_TIME, body)
        with self.assertRaises(P.SamayaError):
            P.parse_response(body)

    def test_sync_check_can_be_disabled(self):
        r = P.parse_response(umsgpack.unpackb(payload(lambda: False, require_sync=False)))
        self.assertEqual(r.unix, 1_793_000_000)

    def test_payload_is_small(self):
        self.assertLessEqual(len(payload(lambda: True)), 16)


class IdentityCommandTest(unittest.TestCase):
    def test_identity_without_running_reticulum(self):
        import os, subprocess, sys, tempfile
        with tempfile.TemporaryDirectory() as d:
            ident = os.path.join(d, "id")
            out = subprocess.run([sys.executable, "-m", "samaya", "identity", "--identity", ident],
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(out.returncode, 0, out.stderr)
            lines = dict(l.split(None, 1) for l in out.stdout.strip().splitlines())
            self.assertEqual(len(lines["destination:"].strip()), 32)
            self.assertEqual(len(lines["public_key:"].strip()), 128)
            again = subprocess.run([sys.executable, "-m", "samaya", "identity", "--identity", ident],
                                   capture_output=True, text=True, timeout=60)
            self.assertEqual(out.stdout, again.stdout)  # stabil: Datei wird wiederverwendet


if __name__ == "__main__":
    unittest.main()
