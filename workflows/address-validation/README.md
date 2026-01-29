# Adress-Validierung

**Workflow-ID**: `address-validation`
**Typ**: Checker
**Kategorie**: Qualitätssicherung

---

## Beschreibung

Dieser Workflow validiert Adressdaten für Schweizer Immobilienportfolios. Er prüft:

- Vollständigkeit der Pflichtfelder (PLZ, Ort)
- Format von PLZ, Kanton, EGID
- Koordinaten innerhalb der Schweiz (LV95/WGS84)
- Doppelte Adressen und EGIDs

---

## Eingabe

**Dateiformate**: Excel (.xlsx, .xls)

**Erwartete Spalten** (exakte Spaltennamen erforderlich):

| Spalte | Pflicht | Beschreibung | Beispiel |
|--------|---------|--------------|----------|
| bbl_id | Ja | BBL Objekt-ID | 12345 |
| av_egid | Ja | Eidg. Gebäudeidentifikator (EGID) | 123456789 |
| adr_plz | Nein | Postleitzahl | 8001 |
| adr_ort | Nein | Ortschaft | Zürich |
| adr_str | Nein | Strassenname | Bahnhofstrasse |
| adr_hsnr | Nein | Hausnummer | 42a |
| adr_reg | Nein | Kanton (2-stellig) | ZH |
| wgs84_lat | Nein | Breitengrad (WGS84) | 47.376887 |
| wgs84_lon | Nein | Längengrad (WGS84) | 8.541694 |

**Hinweis**: Spalten mit abweichenden Namen werden nicht erkannt. Bei fehlenden Spalten wird eine Warnung ausgegeben.

---

## Prüfregeln

### Vollständigkeit

| ID | Regel | Schweregrad |
|----|-------|-------------|
| R-ADDR-001 | Pflichtfelder (PLZ, Ort) | Fehler |
| R-ADDR-005 | Koordinaten vorhanden | Warnung |
| R-ADDR-008 | EGID vorhanden | Fehler |

### Formatprüfung

| ID | Regel | Schweregrad |
|----|-------|-------------|
| R-ADDR-002 | PLZ-Format (4-stellig, 1000-9999) | Fehler |
| R-ADDR-003 | Kanton gültig (ZH, BE, etc.) | Fehler |
| R-ADDR-004 | Strassenformat | Warnung |
| R-ADDR-007 | EGID-Format (positive Ganzzahl) | Fehler |

### Konsistenzprüfung

| ID | Regel | Schweregrad |
|----|-------|-------------|
| R-ADDR-006 | Koordinaten innerhalb Schweiz | Fehler |

### Duplikaterkennung

| ID | Regel | Schweregrad |
|----|-------|-------------|
| R-ADDR-009 | Doppelte Adressen | Warnung |
| R-ADDR-010 | Doppelte EGIDs | Warnung |

---

## Ausgabe

- **Dashboard**: Übersicht mit Fehlerstatistiken
- **Excel-Report**: Detaillierte Fehlerliste mit Zeilennummern

---

## Kontakt

BBL - Bundesamt für Bauten und Logistik
