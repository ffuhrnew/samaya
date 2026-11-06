import argparse
import json
import os
import sys
import time

from . import __version__
from .protocol import SamayaError

DEFAULT_ID = os.path.expanduser("~/.samaya/identity")


def _rns(config):
    import RNS

    RNS.Reticulum(configdir=config)
    return RNS


def cmd_identity(args):
    import RNS
    from .server import load_or_create_identity

    ident = load_or_create_identity(RNS, args.identity)
    # Nur den Hash berechnen: eine Destination anzulegen setzt eine laufende Reticulum-Instanz voraus.
    print("destination: %s" % RNS.Destination.hash(ident, "samaya", "time").hex())
    print("public_key:  %s" % ident.get_public_key().hex())
    return 0


def cmd_serve(args):
    from .server import SamayaServer, load_or_create_identity

    RNS = _rns(args.rns_config)
    ident = load_or_create_identity(RNS, args.identity)
    server = SamayaServer(RNS, ident, announce_interval=args.announce_interval, require_sync=not args.no_sync_check)
    print("samaya %s bereit" % __version__, flush=True)
    print("destination: %s" % server.hash_hex, flush=True)
    print("public_key:  %s" % server.public_key_hex, flush=True)
    server.start(announce_delay=0.5 if args.announce_delay is None else args.announce_delay)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


def cmd_get(args):
    from .client import fetch_time, fetch_time_announce

    RNS = _rns(args.rns_config)
    try:
        if args.announce:
            res = fetch_time_announce(RNS, args.public_key, args.timeout)
        else:
            res = fetch_time(RNS, args.public_key, args.timeout)
    except SamayaError as exc:
        print("Fehler:", exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(res))
    else:
        print("Zeit:      %.3f (Unix)" % res["unix"])
        if res["rtt"] is None:
            print("Modus:     Announce (%s, %s Hops)" % (
                "Pfadantwort" if res.get("path_response") else "reguläre Aussendung", res.get("hops")))
        else:
            print("Laufzeit:  %.2f s" % res["rtt"])
        print("Abweichung der lokalen Uhr: %+.3f s" % -res["offset"])
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(prog="samaya", description="Zeitdienst für Reticulum (समय)")
    p.add_argument("--version", action="version", version="samaya " + __version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="Zeitserver starten")
    s.add_argument("--rns-config", help="Reticulum-Config-Verzeichnis (Standard: ~/.reticulum, Shared Instance)")
    s.add_argument("--identity", default=DEFAULT_ID, help="Identity-Datei (wird angelegt)")
    s.add_argument("--announce-interval", type=int, default=7200, help="Sekunden zwischen Announces (0 = nur beim Start)")
    s.add_argument("--announce-delay", type=float, help="Sekunden bis zum ersten Announce (Standard 0,5)")
    s.add_argument("--no-sync-check", action="store_true", help="timedatectl-Prüfung der Systemuhr abschalten")
    s.set_defaults(fn=cmd_serve)

    i = sub.add_parser("identity", help="Hash und öffentlichen Schlüssel des Servers anzeigen")
    i.add_argument("--identity", default=DEFAULT_ID)
    i.set_defaults(fn=cmd_identity)

    g = sub.add_parser("get", help="Zeit von einem Server holen (Test)")
    g.add_argument("public_key", help="öffentlicher Schlüssel des Servers (128 Hex-Zeichen)")
    g.add_argument("--rns-config", help="Reticulum-Config-Verzeichnis")
    g.add_argument("--timeout", type=float, default=60.0)
    g.add_argument("--announce", action="store_true",
                   help="Announce-Modus (Pfadanfrage + Announce, kein Link), wie die Firmware")
    g.add_argument("--json", action="store_true")
    g.set_defaults(fn=cmd_get)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
