"""Samaya-Server: eine RNS-Destination ``samaya.time`` mit Request-Handler ``/time``."""

import os
import subprocess
import threading
import time

from . import __version__
from .protocol import APP_NAME, ASPECTS, REQUEST_PATH, build_response


def clock_synchronized():
    """True/False, wenn das System seine Uhr als (nicht) synchronisiert meldet, sonst None (unbekannt)."""
    try:
        out = subprocess.run(
            ["timedatectl", "show", "-p", "NTPSynchronized", "--value"],
            capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    value = out.stdout.strip().lower()
    if value == "yes":
        return True
    if value == "no":
        return False
    return None


def load_or_create_identity(RNS, path):
    if os.path.exists(path):
        identity = RNS.Identity.from_file(path)
        if identity is None:
            raise SystemExit("Identity-Datei nicht lesbar: %s" % path)
        return identity
    os.makedirs(os.path.dirname(os.path.abspath(path)), mode=0o700, exist_ok=True)
    identity = RNS.Identity()
    identity.to_file(path)
    os.chmod(path, 0o600)
    return identity


class SamayaServer:
    def __init__(self, RNS, identity, announce_interval=7200, require_sync=True, sync_check=clock_synchronized,
                 clock=time.time):
        self.RNS = RNS
        self.identity = identity
        self.announce_interval = announce_interval
        self.require_sync = require_sync
        self._sync_check = sync_check
        self._clock = clock
        self._stop = threading.Event()
        self.served = 0
        self.destination = RNS.Destination(identity, RNS.Destination.IN, RNS.Destination.SINGLE, APP_NAME, *ASPECTS)
        self.destination.register_request_handler(
            REQUEST_PATH, response_generator=self._on_request, allow=RNS.Destination.ALLOW_ALL
        )
        self.destination.set_default_app_data(self.announce_payload)

    @property
    def hash_hex(self):
        return self.destination.hash.hex()

    @property
    def public_key_hex(self):
        return self.identity.get_public_key().hex()

    def _on_request(self, path, data, request_id, link_id, remote_identity, requested_at):
        synced = self._sync_check() if self.require_sync else None
        self.served += 1
        return build_response(self._clock(), synced)

    def announce_payload(self):
        """App-Data jedes Announces: dieselbe Map wie die Antwort auf /time (MsgPack).

        Auch Pfadantworten (Reticulum ruft announce() dafür selbst auf) laufen über
        den Default-App-Data-Callback und tragen damit die Zeit der Aussendung.
        Ist die Serveruhr nachweislich nicht synchronisiert, entfällt die Zeit
        (nur Version und synced=0), Clients verwerfen das.
        """
        synced = self._sync_check() if self.require_sync else None
        return self.RNS.vendor.umsgpack.packb(build_response(self._clock(), synced))

    def announce(self):
        self.destination.announce()
        self.RNS.log("samaya: Announce gesendet (%s)" % self.hash_hex, self.RNS.LOG_NOTICE)

    def _announce_loop(self):
        while not self._stop.wait(self.announce_interval):
            try:
                self.announce()
            except Exception as exc:  # Dienst soll weiterlaufen
                self.RNS.log("samaya: Announce fehlgeschlagen: %s" % exc, self.RNS.LOG_ERROR)

    def start(self, announce_delay=8.0):
        threading.Timer(announce_delay, self.announce).start()
        if self.announce_interval:
            threading.Thread(target=self._announce_loop, name="samaya-announce", daemon=True).start()

    def stop(self):
        self._stop.set()
