# Samaya (समय) – Protokoll v1

## Problem

Reticulum nimmt einen Announce für ein bekanntes Ziel nur an, wenn sein Zeitstempel
größer ist als der größte im gespeicherten Pfad (`Transport.cpp` 2271–2274, entspricht `Transport.py`).
Der Zeitstempel steckt im Random-Blob des Announces (Bytes 5–9, Sekunden, big endian).
Hat ein Knoten keine echte Uhr (microReticulum: Laufzeit + gespeicherter Offset),
kann sein Zeitstempel nach Flashen oder Verlust der Datei `time_offset` weit unter dem
Wert liegen, den andere Transportknoten schon gespeichert haben. Seine Announces werden
dann bis zum Ablauf des Pfads (7 Tage) verworfen, obwohl der Knoten korrekt sendet.

## Idee

Ein Knoten holt die Unix-Zeit von einem vertrauten Server im Netz, setzt damit seine
Uhr und sendet danach einen sauberen Announce. Unix-Zeit (~1,8 Milliarden Sekunden) liegt
über jedem Laufzeit-Zeitstempel, den ein Mikro-Knoten je gebildet hat. Der Announce wird
daher von jedem Transportknoten angenommen, auch bei einem alten Pfadeintrag.

## Destination

`samaya.time` (App `samaya`, Aspekt `time`), Typ SINGLE, IN auf dem Server.
Der Server hat eine feste Identity. Der Client bekommt den **öffentlichen Schlüssel**
(64 Byte, 128 Hex-Zeichen) des Servers eingetragen, nicht nur einen Hash: Daraus lässt sich die
Destination berechnen, ohne je einen Announce gehört zu haben (Knoten mit Transport aus
speichern keine Identities, RAK4 meldet sogar „failed to store identity“).

## Anfrage und Antwort

Link zur Destination, Request-Pfad `/time`, keine Nutzdaten, `ALLOW_ALL`.
Die Antwort ist eine MsgPack-Map mit Ganzzahl-Schlüsseln:

| Schlüssel | Bedeutung |
|---|---|
| 1 | Unix-Zeit in ganzen Sekunden (UTC) |
| 2 | Millisekunden 0..999 (optional) |
| 3 | Protokollversion (1) |
| 4 | 1 = Uhr des Servers synchronisiert, 0 = nicht (dann fehlt Schlüssel 1) |

Die Antwort kommt über einen verschlüsselten Link, dessen Gegenstelle durch den
eingetragenen Schlüssel festgelegt ist. Ein Dritter kann keine Zeit unterschieben.

## Regeln für Clients

1. Antwort verwerfen, wenn Schlüssel 4 = 0, Schlüssel 1 fehlt oder die Zeit außerhalb
   2026-01-01 … 2100-01-01 liegt (`MIN_VALID`/`MAX_VALID`).
2. Zeit nur **vorwärts** übernehmen: Ist sie nicht größer als die eigene Uhr, nichts tun.
   So kann ein falscher Server die Uhr nie zurückdrehen.
3. Nur im Link-Modus: halbe Link-Laufzeit zur Serverzeit addieren (Request-Dauer / 2).
   Im Announce-Modus gibt es keine Korrektur, für die Zeitstempel im Announce ist die Genauigkeit unwichtig.
4. Nach erfolgreicher Übernahme die Uhr **sofort speichern** (`time_offset`) und
   **genau einmal** NomadNet- und Management-Announce senden.
5. Ohne Erfolg alle paar Minuten wiederholen (Backoff, auf LoRa sparsam). Der Knoten läuft
   in der Zwischenzeit wie bisher.
6. Start-Announce nicht verzögern: ohne Server-Zeit gilt das alte Verhalten, nach der
   Synchronisation folgt der saubere Announce.

## Anforderungen an die Firmware (microReticulum)

Stand 05.11.2026. Zwei Entwürfe wurden verglichen: eine getrennte Announce-Uhr und eine interne
Uhr auf Unix-Skala. Entscheidung: **interne Uhr auf Unix-Skala, aber der große Sprung findet beim
Start statt, nie zur Laufzeit.** Grund: `OS::time()` ist die Uhr aller Timer und Ablaufzeiten in
`Transport.cpp` (`path_entry._timeout`, `_timestamp + DESTINATION_TIMEOUT`, `LINK_TIMEOUT`,
Reverse-Tabelle, Announce-Retransmits). Springt sie zur Laufzeit um 1,8·10⁹ s, laufen alle
bestehenden Einträge ab und aktive Links reißen (aus dem Quellcode gelesen, nicht gemessen).
Beim Start existiert dieser Zustand noch nicht.

- **Seed:** Fehlt `time_offset`, beginnt die Uhr bei der Compile-Zeit in **UTC**-Unix-Sekunden
  (nicht `__DATE__`/`__TIME__` als Ortszeit nehmen: sonst liegt der Node Stunden vorn, und die
  Regel „nur vorwärts“ kann ihn nie korrigieren).
- **Migration:** Ein gespeicherter Wert unter `MIN_VALID * 1000` ms stammt aus der alten Skala
  (Laufzeit seit erstem Boot) und wird beim Start durch den Seed ersetzt. Nodes, die im
  Update-Modus geflasht werden und ihre alte Datei behalten, sind sonst beim ersten Sync der
  große Sprung zur Laufzeit.
- **Grenze in `readTimeOffset()`:** von 4 294 967 295 ms auf `MAX_VALID * 1000` anheben, dauerhaft
  in der Bibliothek. Das behebt zugleich die 49,7-Tage-Grenze (gespeichert ist die Gesamtzeit
  seit dem ersten Boot) und ist Voraussetzung dafür, dass ein Unix-Offset (≈ 1,8·10¹² ms) einen Neustart überlebt.
- **Sync:** nur vorwärts. Der Sprung ist dann höchstens das Alter des Builds, nicht 1,8·10⁹ s.
  Sofort in `time_offset` schreiben (`Reticulum::writeTimeOffset()`).
- `microStore::set_time_offset(offset / 1000)` nimmt `uint32_t`: Unix-Sekunden passen bis 2106.
- **Vorbedingung vor dem Flashen:** keine Verengung von `OS::time()` auf `float` oder `uint32_t`
  im Quellcode (ein `float` verliert bei 1,8·10⁹ rund ±128 s Genauigkeit).
- **Rückfall**, falls die Prüfung eine Stelle findet, die Unix-Skala nicht verträgt: getrennte
  Announce-Uhr nur für `Destination.cpp` Zeile 272 (`OS::announce_time()` = `time()` + `_announce_base`,
  eigene Datei `announce_time`, beim Start `base = gespeichert + 1 - time()`), interne Uhr unverändert.
- Feld im Provisioning-Namespace 1: „Time Server Key“ (Bytes, 64 Byte, leer = aus).
  Ein Konfigurationswerkzeug, das das Provisioning-Schema ausliest, zeigt es dann ohne Änderung an.

## Announce-Modus (leichtere Alternative für Mikro-Knoten)

Jeder Announce des Servers trägt als App-Data dieselbe Map wie die Antwort auf `/time`
(MsgPack, ca. 14 Byte). Das gilt auch für Pfadantworten: Reticulum sendet dafür einen
frischen Announce der lokalen Destination, die Zeit ist die der Aussendung.

Ein Client braucht dann **keinen Link**: Pfadanfrage für die Server-Destination senden
(ein kleines Paket), den Announce empfangen, Map nach denselben Regeln auswerten. Die
Signatur und die Bindung der Destination an die Identity prüft Reticulum beim Annehmen.
Der Client vergleicht die Identity mit dem eingetragenen Schlüssel.

Warum das für die Firmware sinnvoll ist (aus den Zahlen dieses Netzes, nicht gemessen am Link):
- Freier Heap liegt bei 19,6 KB (NRF_TEST) bis 34 KB (RAK). Ein ausgehender Link mit Request
  braucht mehr Speicher als ein Announce-Handler. Im Firmware-Quellcode gibt es außerdem
  keinen ausgehenden Link als Vorlage (`grep` über `Link(` und `.request(` außerhalb von `Link.*`: kein Treffer).
- Management-Links zu LoRa-Knoten brechen im Betrieb häufig ab (Zeitüberschreitungen bei GetState und
  GetSchema). Eine Pfadanfrage plus ein Announce sind zwei Pakete statt Link-Aufbau, Request und Antwort.
- Ein Knoten mit Transport aus hört Announces und prüft sie (die Zähler „Paths Failed“ zählen sie),
  nur das Speichern der Identity kann scheitern (RAK4: „failed to store identity“). Die Identity
  muss der Client deshalb aus dem eingetragenen Schlüssel kennen, nicht aus dem Speicher.

Grenze: Antwortet ein Transportknoten auf die Pfadanfrage aus seinem Cache, ist die Zeit so alt
wie dessen letzter empfangener Announce (höchstens `--announce-interval`, solange der Server läuft).
Für die Announce-Uhr genügt das, weil sie nur vorwärts gesetzt wird. Wer die Zeit genau braucht,
nimmt den Link-Modus.

## Server

`samaya serve`: Destination anlegen, Request-Handler `/time`, Announce beim Start und alle
`--announce-interval` Sekunden (Standard 7200). Antwort nur, wenn `timedatectl` die Systemuhr
als synchronisiert meldet (`NTPSynchronized=yes`) oder die Prüfung nicht verfügbar ist.
Meldet es `no`, wird nur `{3: 1, 4: 0}` geliefert, ohne Zeit.

## Offene Punkte

- Firmware-Client noch nicht geschrieben. Erster Test auf einem Testknoten, nicht auf produktiv laufenden Knoten.
- Mehrere Server (Redundanz) und Mehrheitsentscheid: bewusst nicht in v1.
- Unix-Zeit statt Zeitzonen: UTC, Umrechnung ist Sache des Anzeigenden.
- Schutz vor Missbrauch (Last auf LoRa): Server antwortet auf `ALLOW_ALL`, Antwort ist klein (ein Paket).
