import unittest

from samaya import protocol as P


class ProtocolTest(unittest.TestCase):
    NOW = 1_793_000_000.25

    def test_roundtrip_synced(self):
        r = P.parse_response(P.build_response(self.NOW, True))
        self.assertEqual(r.unix, 1_793_000_000)
        self.assertEqual(r.ms, 250)
        self.assertIs(r.synced, True)

    def test_roundtrip_unknown_sync(self):
        body = P.build_response(self.NOW, None)
        self.assertNotIn(P.K_SYNCED, body)
        self.assertIsNone(P.parse_response(body).synced)

    def test_unsynced_server_delivers_no_time(self):
        body = P.build_response(self.NOW, False)
        self.assertNotIn(P.K_TIME, body)
        with self.assertRaises(P.SamayaError):
            P.parse_response(body)

    def test_rejects_garbage(self):
        for bad in (None, [], "x", {}, {P.K_TIME: "1"}, {P.K_TIME: True},
                    {P.K_TIME: 5}, {P.K_TIME: P.MAX_VALID + 1},
                    {P.K_TIME: P.MIN_VALID, P.K_MS: 1000},
                    {P.K_TIME: P.MIN_VALID, P.K_MS: -1}):
            with self.assertRaises(P.SamayaError, msg=repr(bad)):
                P.parse_response(bad)

    def test_bounds_inclusive(self):
        self.assertEqual(P.parse_response({P.K_TIME: P.MIN_VALID}).unix, P.MIN_VALID)
        self.assertEqual(P.parse_response({P.K_TIME: P.MAX_VALID}).unix, P.MAX_VALID)


if __name__ == "__main__":
    unittest.main()
