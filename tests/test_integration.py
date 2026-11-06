"""Server und Client als getrennte Prozesse über ein TCP-Interface auf 127.0.0.1 (echtes RNS)."""

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest

try:
    import RNS  # noqa: F401
    HAVE_RNS = True
except ImportError:
    HAVE_RNS = False

CONFIG = """[reticulum]
  enable_transport = No
  share_instance = No
  panic_on_interface_error = No

[logging]
  loglevel = 2

[interfaces]
{iface}
"""
SERVER_IFACE = """  [[Loopback Server]]
    type = TCPServerInterface
    enabled = yes
    listen_ip = 127.0.0.1
    listen_port = {port}
"""
CLIENT_IFACE = """  [[Loopback Client]]
    type = TCPClientInterface
    enabled = yes
    target_host = 127.0.0.1
    target_port = {port}
"""


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def write_config(directory, iface):
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "config"), "w") as fh:
        fh.write(CONFIG.format(iface=iface))


@unittest.skipUnless(HAVE_RNS, "rns nicht installiert")
class IntegrationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.port = free_port()
        self.srv_cfg = os.path.join(self.tmp.name, "srv")
        self.cli_cfg = os.path.join(self.tmp.name, "cli")
        self.ident = os.path.join(self.tmp.name, "identity")
        write_config(self.srv_cfg, SERVER_IFACE.format(port=self.port))
        write_config(self.cli_cfg, CLIENT_IFACE.format(port=self.port))
        self.proc = None

    def tearDown(self):
        if self.proc:
            self.proc.stdout.close()
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.tmp.cleanup()

    def _py(self, *args, **kw):
        return [sys.executable, "-m", "samaya", *args]

    def _start_server(self):
        self.proc = subprocess.Popen(
            self._py("serve", "--rns-config", self.srv_cfg, "--identity", self.ident,
                     "--no-sync-check", "--announce-interval", "0", "--announce-delay", "0.5"),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        key = None
        for line in self.proc.stdout:
            if line.startswith("public_key:"):
                key = line.split()[1]
                break
        self.assertIsNotNone(key, "Server hat keinen Schlüssel ausgegeben")
        time.sleep(1.5)  # TCP-Interface braucht einen Moment
        return key

    def test_get_time_over_link(self):
        key = self._start_server()
        t0 = time.time()
        out = subprocess.run(
            self._py("get", key, "--rns-config", self.cli_cfg, "--timeout", "40", "--json"),
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        res = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertLess(abs(res["unix"] - t0), 30)
        self.assertGreaterEqual(res["rtt"], 0)

    def test_get_time_via_announce(self):
        key = self._start_server()
        t0 = time.time()
        out = subprocess.run(
            self._py("get", key, "--announce", "--rns-config", self.cli_cfg, "--timeout", "40", "--json"),
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stderr)
        res = json.loads(out.stdout.strip().splitlines()[-1])
        self.assertEqual(res["mode"], "announce")
        self.assertLess(abs(res["unix"] - t0), 30)
        self.assertIsNone(res["rtt"])

    def test_wrong_key_fails(self):
        self._start_server()
        wrong = "00" * 64
        out = subprocess.run(
            self._py("get", wrong, "--rns-config", self.cli_cfg, "--timeout", "6"),
            capture_output=True, text=True, timeout=40,
        )
        self.assertNotEqual(out.returncode, 0)

    def test_bad_key_format(self):
        out = subprocess.run(
            self._py("get", "abcd", "--rns-config", self.cli_cfg, "--timeout", "3"),
            capture_output=True, text=True, timeout=30,
        )
        self.assertNotEqual(out.returncode, 0)


if __name__ == "__main__":
    unittest.main()
