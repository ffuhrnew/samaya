# Samaya (समय)

Zeitdienst für Reticulum. Ein Server liefert die Unix-Zeit über einen verschlüsselten
RNS-Link. Knoten ohne Uhr (microReticulum) holen sie dort und senden danach einen sauberen
Announce – so bleiben ihre Pfade auch nach Flashen oder Neustart gültig.
Hintergrund und Protokoll: [PROTOKOLL.md](PROTOKOLL.md).

Stand 0.1.0: Server, Python-Client, Tests. Der Client für die Firmware fehlt noch.

## Installation

Voraussetzung ist ein laufendes Reticulum (`rns`). Entwickelt wurde mit rns 1.5.4.

```
pipx install .                       # oder: pip install --no-deps . (vorhandenes rns bleibt unverändert)
```

Bei pipx liegt Samaya in einem eigenen venv. Dort muss `rns` ebenfalls vorhanden sein:
`pipx runpip samaya install --no-deps --force-reinstall rns==1.5.4` (Version nach Bedarf anpassen).

## Benutzung

```
samaya identity                      # Hash und öffentlichen Schlüssel anzeigen (legt ~/.samaya/identity an)
samaya serve                         # Server, hängt an der Shared Instance (~/.reticulum)
samaya get <public_key>              # Zeit holen (Test), --json für Skripte
```

Der öffentliche Schlüssel (128 Hex-Zeichen) wird später in den Knoten eingetragen.
Die Datei `~/.samaya/identity` ist geheim und gehört nicht ins Repo.

Als Dienst: `deploy/samaya.service` ist eine Vorlage. Benutzer und Pfad zu `samaya` darin
anpassen, nach `/etc/systemd/system/` kopieren, dann
`sudo systemctl daemon-reload && sudo systemctl enable --now samaya`.

## Tests

```
python -m unittest discover -s tests -t .
```

Die Integrationstests starten Server und Client als getrennte Prozesse mit echtem RNS über
ein TCP-Interface auf 127.0.0.1 und brauchen `rns`.

## Lizenz

Reticulum License, siehe [LICENSE](LICENSE).
