"""Samaya-Protokoll v1: Aspekte, Schlüssel, Antwort bauen und prüfen.

Absichtlich winzig: Eine Anfrage (Pfad ``/time``, ohne Nutzdaten), eine Antwort
als MsgPack-Map mit Ganzzahl-Schlüsseln. Ein Client auf einem Mikrocontroller
muss nur Schlüssel 1 lesen (und, falls vorhanden, Schlüssel 4 prüfen).
"""

from dataclasses import dataclass
from typing import Optional

APP_NAME = "samaya"
ASPECTS = ("time",)
REQUEST_PATH = "/time"
VERSION = 1

# Schlüssel der Antwort
K_TIME = 1      # Unix-Zeit in ganzen Sekunden (UTC)
K_MS = 2        # Millisekunden-Anteil 0..999
K_VERSION = 3   # Protokollversion
K_SYNCED = 4    # 1 = Uhr des Servers ist synchronisiert, 0 = nicht (dann fehlt K_TIME)

# Alles vor diesem Zeitpunkt (2026-01-01) ist keine gültige Unix-Zeit.
MIN_VALID = 1_767_225_600
# Alles nach 2100-01-01 ebenfalls nicht.
MAX_VALID = 4_102_444_800


class SamayaError(Exception):
    """Fehler mit Klartext."""


@dataclass
class Reading:
    unix: int
    ms: int
    version: int
    synced: Optional[bool]

    @property
    def seconds(self) -> float:
        return self.unix + self.ms / 1000.0


def build_response(now: float, synced: Optional[bool]) -> dict:
    """Antwort des Servers. Ist die Uhr nachweislich nicht synchronisiert, wird keine Zeit geliefert."""
    if synced is False:
        return {K_VERSION: VERSION, K_SYNCED: 0}
    whole = int(now)
    body = {K_TIME: whole, K_MS: int((now - whole) * 1000), K_VERSION: VERSION}
    if synced is True:
        body[K_SYNCED] = 1
    return body


def parse_response(obj) -> Reading:
    """Prüft eine Antwort und liefert die Zeit oder wirft SamayaError."""
    if not isinstance(obj, dict):
        raise SamayaError("Antwort ist keine Map")
    if obj.get(K_SYNCED) == 0:
        raise SamayaError("Der Zeitserver hat selbst keine synchronisierte Uhr")
    unix = obj.get(K_TIME)
    if isinstance(unix, bool) or not isinstance(unix, int):
        raise SamayaError("Antwort enthält keine Zeit")
    if not MIN_VALID <= unix <= MAX_VALID:
        raise SamayaError("Zeit %r liegt außerhalb des gültigen Bereichs" % unix)
    ms = obj.get(K_MS, 0)
    if isinstance(ms, bool) or not isinstance(ms, int) or not 0 <= ms <= 999:
        raise SamayaError("Millisekunden ungültig")
    synced = None if K_SYNCED not in obj else bool(obj[K_SYNCED])
    return Reading(unix=unix, ms=ms, version=int(obj.get(K_VERSION, 1)), synced=synced)
