# EGID/GWR Checker

**Workflow-ID**: `address-validation`
**Typ**: Checker / Enricher
**Kategorie**: Qualitätssicherung

---

## Beschreibung

Dieser Workflow validiert und ergänzt Gebäudedaten anhand des offiziellen Schweizer Gebäude- und Wohnungsregisters (GWR) über die geo.admin.ch API.

**Hauptfunktionen:**

- Validierung von EGIDs gegen das GWR
- Anreicherung mit offiziellen GWR-Adressdaten
- Koordinatenabgleich (LV95 ↔ WGS84)
- Adressvergleich mit Match-Score-Berechnung
- Duplikaterkennung für EGIDs

**API-Dokumentation**: https://docs.geo.admin.ch/access-data/find-features.html

---

## Eingabe

**Dateiformate**: Excel (.xlsx, .xls), CSV

**Erwartete Spalten** (mit automatischer Erkennung):

| Logischer Name | Mögliche Spaltennamen | Pflicht | Beschreibung |
|----------------|----------------------|---------|--------------|
| av_egid | av_egid, egid, gwr_egid, gebaeude_id, building_id | Ja | Eidgenössischer Gebäudeidentifikator |
| bbl_id | bbl_id, bblid, bbl-id, id, objekt_id, objektid | Nein | BBL-Objekt-ID |
| wgs84_lat | wgs84_lat, lat, latitude, breitengrad, y, coord_y | Nein | Breitengrad (WGS84) |
| wgs84_lon | wgs84_lon, lon, lng, longitude, laengengrad, x, coord_x | Nein | Längengrad (WGS84) |
| adr_reg | adr_reg, kanton, canton, region, kt, state | Nein | Kanton (z.B. ZH, BE) |
| adr_ort | adr_ort, ort, city, stadt, gemeinde, municipality, ortschaft | Nein | Ortschaft |
| adr_plz | adr_plz, plz, zip, postleitzahl, postal_code, npa | Nein | Postleitzahl |
| adr_str | adr_str, strasse, street, str, strassenname, rue | Nein | Strassenname |
| adr_hsnr | adr_hsnr, hausnummer, hsnr, hnr, house_number, nr, numero | Nein | Hausnummer |

> **Hinweis**: Die Spalten werden automatisch anhand der Namenskonventionen erkannt. Alternativ kann ein explizites Column-Mapping übergeben werden.

---

## Prüfregeln

### EGID-Prüfung

| ID | Regel | Schweregrad |
|----|-------|-------------|
| R-GWR-01 | EGID ist vorhanden (nicht leer, 0 oder NULL) | Fehler |
| R-GWR-02 | EGID ist eindeutig (keine Duplikate) | Warnung |
| R-GWR-07 | EGID existiert im GWR | Fehler |

### Adressfeld-Vollständigkeit

| ID | Regel | Schweregrad |
|----|-------|-------------|
| R-GWR-04a | Kanton (adr_reg) ist vorhanden | Info |
| R-GWR-04b | Ort (adr_ort) ist vorhanden | Info |
| R-GWR-04c | PLZ (adr_plz) ist vorhanden | Info |
| R-GWR-04d | Strasse (adr_str) ist vorhanden | Info |
| R-GWR-04e | Hausnummer (adr_hsnr) ist vorhanden | Info |

### Abgleich mit GWR

| ID | Regel | Schweregrad |
|----|-------|-------------|
| R-GWR-05 | Adressfelder stimmen mit GWR überein | Warnung |
| R-GWR-06 | Koordinaten weichen maximal 50m vom GWR ab | Warnung |

---

## Ausgabe

### Neue Spalten (GWR-Daten)

| Spalte | Beschreibung |
|--------|--------------|
| gwr_wgs84_lat | Breitengrad aus GWR (WGS84) |
| gwr_wgs84_lon | Längengrad aus GWR (WGS84) |
| gwr_gkode | E-Koordinate aus GWR (LV95) |
| gwr_gkodn | N-Koordinate aus GWR (LV95) |
| gwr_adr_reg | Kanton aus GWR |
| gwr_adr_ort | Gemeindename aus GWR |
| gwr_adr_plz | PLZ aus GWR |
| gwr_adr_str | Strassenname aus GWR |
| gwr_adr_hsnr | Hausnummer aus GWR |

### Bewertung

| Spalte | Beschreibung |
|--------|--------------|
| eval_score | Match-Score (0-100%) |
| eval_label | Bewertungskategorie |

**Bewertungskategorien (eval_label):**

| Label | Score | Bedeutung |
|-------|-------|-----------|
| Match | ≥ 90% | Vollständige Übereinstimmung |
| Partial | 50-89% | Teilweise Übereinstimmung |
| Mismatch | < 50% | Starke Abweichungen |
| Not Found | - | EGID nicht im GWR gefunden |

### Ergebniszusammenfassung

Die `run_gwr_check()`-Funktion liefert ein Dictionary mit:

- `total_rows`: Gesamtzahl der Zeilen
- `error_count`: Anzahl Fehler
- `warning_count`: Anzahl Warnungen
- `info_count`: Anzahl Info-Meldungen
- `passed_rows`: Zeilen ohne Fehler
- `match_count`: Anzahl "Match"
- `partial_count`: Anzahl "Partial"
- `mismatch_count`: Anzahl "Mismatch"
- `not_found_count`: Anzahl "Not Found"
- `errors`: Liste aller Validierungsfehler

---

## Verwendung

```python
from workflow import run_gwr_check
import pandas as pd

# Daten laden
df = pd.read_excel("gebaeude.xlsx")

# GWR-Check durchführen (automatische Spaltenerkennung)
enriched_df, results = run_gwr_check(df)

# Mit explizitem Column-Mapping
column_mapping = {
    'av_egid': 'EGID',
    'adr_plz': 'Postleitzahl',
    'adr_ort': 'Gemeinde'
}
enriched_df, results = run_gwr_check(df, column_mapping=column_mapping)

# Mit Progress-Callback
def progress(current, total, message):
    print(f"{message}: {current}/{total}")

enriched_df, results = run_gwr_check(df, progress_callback=progress)
```

---

## Technische Details

- **API-Endpoint**: `https://api3.geo.admin.ch/rest/services/ech/MapServer/find`
- **GWR-Layer**: `ch.bfs.gebaeude_wohnungs_register`
- **Koordinatentransformation**: LV95 → WGS84 (swisstopo-Formeln)
- **Koordinatentoleranz**: 50 Meter
- **Async-Unterstützung**: Mit `aiohttp` für schnellere Batch-Abfragen (max. 20 parallele Requests)
- **Rate-Limiting**: 0.1s Verzögerung zwischen synchronen Requests

---

## Kontakt

BBL - Bundesamt für Bauten und Logistik
