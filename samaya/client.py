"""Samaya-Client (Python): holt die Zeit von einem Server, dessen öffentlicher Schlüssel bekannt ist.

Der Schlüssel (64 Byte, 128 Hex-Zeichen) ersetzt den Announce: Die Destination
wird daraus berechnet, ein Announce des Servers muss nie gehört worden sein.
Die Antwort kommt über einen Link, ist also an den Server-Schlüssel gebunden.
"""

import threading
import time

from .protocol import APP_NAME, ASPECTS, REQUEST_PATH, SamayaError, parse_response


def destination_from_key(RNS, public_key_hex):
    try:
        key = bytes.fromhex(public_key_hex)
    except ValueError:
        raise SamayaError("Schlüssel ist kein Hex")
    if len(key) != RNS.Identity.KEYSIZE // 8:
        raise SamayaError("Schlüssel muss %d Byte (%d Hex-Zeichen) lang sein" % (RNS.Identity.KEYSIZE // 8, RNS.Identity.KEYSIZE // 4))
    identity = RNS.Identity(create_keys=False)
    identity.load_public_key(key)
    return RNS.Destination(identity, RNS.Destination.OUT, RNS.Destination.SINGLE, APP_NAME, *ASPECTS)


def fetch_time(RNS, public_key_hex, timeout=60.0):
    """Gibt dict zurück: unix (float, um halbe Laufzeit korrigiert), raw, rtt, offset (gegen die lokale Uhr)."""
    dest = destination_from_key(RNS, public_key_hex)
    deadline = time.time() + timeout

    if not RNS.Transport.has_path(dest.hash):
        RNS.Transport.request_path(dest.hash)
        while not RNS.Transport.has_path(dest.hash):
            if time.time() > deadline:
                raise SamayaError("Kein Pfad zum Zeitserver %s" % dest.hash.hex())
            time.sleep(0.1)

    up, down = threading.Event(), threading.Event()
    link = RNS.Link(dest, established_callback=lambda _l: up.set(), closed_callback=lambda _l: down.set())
    while not up.is_set():
        if down.is_set() or time.time() > deadline:
            raise SamayaError("Link zum Zeitserver kam nicht zustande")
        time.sleep(0.05)

    done, box = threading.Event(), {}
    t_send = time.time()
    link.request(
        REQUEST_PATH,
        data=None,
        response_callback=lambda r: (box.update(response=r.response, t=time.time()), done.set()),
        failed_callback=lambda r: (box.update(failed=True), done.set()),
        timeout=max(1.0, deadline - time.time()),
    )
    done.wait(max(1.0, deadline - time.time()) + 5)
    try:
        link.teardown()
    except Exception:
        pass
    if box.get("failed") or "response" not in box:
        raise SamayaError("Keine Antwort vom Zeitserver")

    reading = parse_response(box["response"])
    rtt = box["t"] - t_send
    corrected = reading.seconds + rtt / 2.0
    return {
        "unix": corrected,
        "raw": reading.seconds,
        "rtt": rtt,
        "offset": corrected - box["t"],
        "synced": reading.synced,
        "destination": dest.hash.hex(),
    }


def fetch_time_announce(RNS, public_key_hex, timeout=90.0, retry=20.0):
    """Announce-Modus: Pfadanfrage senden, den Announce des Servers abwarten, Zeit aus der App-Data lesen.

    Kein Link. So arbeitet auch die Firmware. Die Zeit ist die der Aussendung (bei einer Antwort
    aus dem Cache eines Transportknotens entsprechend älter), eine Laufzeitkorrektur gibt es nicht.
    """
    dest = destination_from_key(RNS, public_key_hex)
    want = dest.identity.hash
    done, box = threading.Event(), {}

    class Handler:
        aspect_filter = "%s.%s" % (APP_NAME, ".".join(ASPECTS))
        receive_path_responses = True

        def received_announce(self, destination_hash, announced_identity, app_data,
                              announce_packet_hash=None, is_path_response=None):
            if announced_identity is None or announced_identity.hash != want or box:
                return
            try:
                reading = parse_response(RNS.vendor.umsgpack.unpackb(app_data))
            except SamayaError as exc:
                box["error"] = str(exc)
                done.set()
                return
            except Exception:
                return  # kein Samaya-Format, weiterwarten
            box.update(reading=reading, t=time.time(), path_response=is_path_response)
            done.set()

    handler = Handler()
    RNS.Transport.register_announce_handler(handler)
    deadline = time.time() + timeout
    try:
        while not done.is_set():
            if time.time() > deadline:
                raise SamayaError("Kein Announce des Zeitservers %s innerhalb %.0f s" % (dest.hash.hex(), timeout))
            RNS.Transport.request_path(dest.hash)
            done.wait(min(retry, max(0.1, deadline - time.time())))
    finally:
        RNS.Transport.deregister_announce_handler(handler)
    if "error" in box:
        raise SamayaError(box["error"])
    reading = box["reading"]
    return {
        "unix": reading.seconds,
        "raw": reading.seconds,
        "rtt": None,
        "offset": reading.seconds - box["t"],
        "synced": reading.synced,
        "destination": dest.hash.hex(),
        "mode": "announce",
        "path_response": box.get("path_response"),
        "hops": RNS.Transport.hops_to(dest.hash),
    }
