"""Samaya (समय, "Zeit") – Zeitdienst für Reticulum.

Ein Server liefert die Unix-Zeit über einen signierten, verschlüsselten
RNS-Link. Knoten ohne Uhr (microReticulum) holen sie dort und senden danach
einen sauberen Announce. Siehe PROTOKOLL.md.
"""

__version__ = "0.1.0"
