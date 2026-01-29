# CAFM Basisplan - Anforderungen und Prüfplan

**Version**: 1.0
**Stand**: Januar 2026
**Gültig für**: BBL - Bundesamt für Bauten und Logistik

---

## 1. Übersicht

Der CAFM Basisplan ist die standardisierte CAD-Grundlage für das Computer Aided Facility Management. Dieser Prüfplan definiert die Anforderungen an DWG-Dateien, die an das BBL geliefert werden.

---

## 2. Allgemeine Anforderungen

### 2.1 Dateiformat

| Anforderung | Spezifikation | Prüf-ID |
|-------------|---------------|---------|
| Format | AutoCAD DWG (2018 oder älter) | DWG-001 |
| Dateiname | `[EGID]_[Geschoss]_Basisplan.dwg` | DWG-002 |
| Koordinatensystem | CH1903+ / LV95 | DWG-003 |
| Einheiten | Meter (1 Einheit = 1 Meter) | DWG-004 |
| Massstab | 1:100 im Modellbereich | DWG-005 |

### 2.2 Zeichnungsstruktur

| Anforderung | Spezifikation | Prüf-ID |
|-------------|---------------|---------|
| Externe Referenzen | Keine XREFs erlaubt (aufgelöst) | DWG-010 |
| Proxy-Objekte | Keine Proxy-Objekte | DWG-011 |
| OLE-Objekte | Keine OLE-Objekte | DWG-012 |
| Layout-Tabs | Mindestens 1 Layout vorhanden | DWG-013 |

---

## 3. Layer-Struktur (Pflichtlayer)

### 3.1 Baukonstruktion

| Layer-Name | Farbe | Linientyp | Beschreibung | Prüf-ID |
|------------|-------|-----------|--------------|---------|
| `BBL_WAND_TRAGEND` | 1 (Rot) | Continuous | Tragende Wände | LAY-101 |
| `BBL_WAND_NICHTTRAGEND` | 3 (Grün) | Continuous | Nichttragende Wände | LAY-102 |
| `BBL_WAND_GLAS` | 4 (Cyan) | Continuous | Glaswände, Trennwände | LAY-103 |
| `BBL_STUETZE` | 1 (Rot) | Continuous | Stützen, Pfeiler | LAY-104 |
| `BBL_DECKE` | 8 (Grau) | Continuous | Deckenöffnungen | LAY-105 |
| `BBL_FASSADE` | 2 (Gelb) | Continuous | Fassadenlinie | LAY-106 |

### 3.2 Öffnungen

| Layer-Name | Farbe | Linientyp | Beschreibung | Prüf-ID |
|------------|-------|-----------|--------------|---------|
| `BBL_TUER` | 6 (Magenta) | Continuous | Türen mit Aufschlag | LAY-201 |
| `BBL_FENSTER` | 5 (Blau) | Continuous | Fenster | LAY-202 |
| `BBL_TOR` | 6 (Magenta) | Continuous | Tore, Rolltore | LAY-203 |

### 3.3 Raumpolygone

| Layer-Name | Farbe | Linientyp | Beschreibung | Prüf-ID |
|------------|-------|-----------|--------------|---------|
| `BBL_RAUM_POLYGON` | 30 (Orange) | Continuous | Geschlossene Raumpolygone | LAY-301 |
| `BBL_RAUM_NUMMER` | 7 (Weiss) | - | Raumnummern (Text) | LAY-302 |
| `BBL_RAUM_BEZEICHNUNG` | 7 (Weiss) | - | Raumbezeichnung (Text) | LAY-303 |
| `BBL_RAUM_FLAECHE` | 7 (Weiss) | - | Flächenangabe (Text) | LAY-304 |

### 3.4 Technische Installationen

| Layer-Name | Farbe | Linientyp | Beschreibung | Prüf-ID |
|------------|-------|-----------|--------------|---------|
| `BBL_SANITAER` | 160 (Blau) | Continuous | Sanitärobjekte | LAY-401 |
| `BBL_HEIZUNG` | 10 (Rot) | Continuous | Heizkörper | LAY-402 |
| `BBL_LUEFTUNG` | 130 (Cyan) | Hidden | Lüftungsauslässe | LAY-403 |
| `BBL_ELEKTRO` | 40 (Orange) | Continuous | Elektroanschlüsse | LAY-404 |

### 3.5 Ausstattung

| Layer-Name | Farbe | Linientyp | Beschreibung | Prüf-ID |
|------------|-------|-----------|--------------|---------|
| `BBL_MOEBEL_FEST` | 8 (Grau) | Continuous | Fest eingebaute Möbel | LAY-501 |
| `BBL_MOEBEL_LOSE` | 9 (Grau) | Dashed | Lose Möblierung | LAY-502 |
| `BBL_GERAETE` | 8 (Grau) | Continuous | Geräte, Maschinen | LAY-503 |

### 3.6 Beschriftung und Hilfslinien

| Layer-Name | Farbe | Linientyp | Beschreibung | Prüf-ID |
|------------|-------|-----------|--------------|---------|
| `BBL_TEXT` | 7 (Weiss) | - | Allgemeine Beschriftung | LAY-601 |
| `BBL_MASSLINIE` | 7 (Weiss) | Continuous | Masslinien | LAY-602 |
| `BBL_ACHSE` | 1 (Rot) | Center | Achsen | LAY-603 |
| `BBL_HILFSLINIEN` | 8 (Grau) | Dashed | Konstruktionshilfen | LAY-604 |
| `BBL_NORDPFEIL` | 7 (Weiss) | - | Nordpfeil | LAY-605 |

---

## 4. Raumpolygone - Detailanforderungen

### 4.1 Geometrie

| Anforderung | Spezifikation | Prüf-ID |
|-------------|---------------|---------|
| Objekttyp | Geschlossene Polylinien (LWPOLYLINE) | RPO-001 |
| Geschlossenheit | Alle Polygone müssen geschlossen sein | RPO-002 |
| Selbstüberschneidung | Keine Selbstüberschneidungen | RPO-003 |
| Überlappung | Raumpolygone dürfen sich nicht überlappen | RPO-004 |
| Mindestfläche | > 1 m² | RPO-005 |
| Lücken | Keine Lücken zwischen angrenzenden Räumen > 1cm | RPO-006 |

### 4.2 Attribute / Extended Data

Jedes Raumpolygon muss folgende XDATA enthalten:

| Attribut | Datentyp | Pflicht | Prüf-ID |
|----------|----------|---------|---------|
| `RAUM_NR` | String | Ja | RPO-101 |
| `RAUM_BEZ` | String | Ja | RPO-102 |
| `GESCHOSS` | String | Ja | RPO-103 |
| `NUTZUNGSART` | Integer (SIA 416) | Ja | RPO-104 |
| `FLAECHE_SOLL` | Double (m²) | Nein | RPO-105 |

---

## 5. Blöcke und Symbole

### 5.1 Pflichtblöcke

| Blockname | Beschreibung | Prüf-ID |
|-----------|--------------|---------|
| `BBL_TUER_*` | Türsymbole (verschiedene Typen) | BLK-001 |
| `BBL_FENSTER_*` | Fenstersymbole | BLK-002 |
| `BBL_NORDPFEIL` | Standardisierter Nordpfeil | BLK-003 |
| `BBL_PLANKOPF` | Plankopf mit Metadaten | BLK-004 |

### 5.2 Blockattribute (Plankopf)

| Attribut | Pflicht | Prüf-ID |
|----------|---------|---------|
| `PROJEKT_NR` | Ja | BLK-101 |
| `PROJEKT_NAME` | Ja | BLK-102 |
| `GEBAEUDE_NR` | Ja | BLK-103 |
| `EGID` | Ja | BLK-104 |
| `GESCHOSS` | Ja | BLK-105 |
| `ERSTELLT_AM` | Ja | BLK-106 |
| `ERSTELLT_VON` | Ja | BLK-107 |
| `MASSSTAB` | Ja | BLK-108 |

---

## 6. Textstile

| Stilname | Schriftart | Höhe (Standard) | Prüf-ID |
|----------|------------|-----------------|---------|
| `BBL_STANDARD` | Arial | 2.5mm (1:100) | TXT-001 |
| `BBL_RAUMNUMMER` | Arial Bold | 3.5mm (1:100) | TXT-002 |
| `BBL_TITEL` | Arial Bold | 5.0mm (1:100) | TXT-003 |

---

## 7. Prüfplan - Zusammenfassung

### 7.1 Kritische Fehler (Ablehnung)

Diese Fehler führen zur Ablehnung der Datei:

- DWG-001: Falsches Dateiformat
- DWG-003: Falsches Koordinatensystem
- DWG-010: XREFs vorhanden
- LAY-301: Layer `BBL_RAUM_POLYGON` fehlt oder leer
- RPO-002: Nicht geschlossene Raumpolygone
- RPO-004: Überlappende Raumpolygone
- BLK-004: Plankopf fehlt

### 7.2 Warnungen (Korrektur empfohlen)

- LAY-*: Optionale Layer fehlen
- RPO-005: Sehr kleine Raumpolygone (< 1 m²)
- TXT-*: Falsche Textstile verwendet
- BLK-101-108: Plankopf-Attribute unvollständig

### 7.3 Informationen

- Statistiken über Layer-Nutzung
- Anzahl Räume pro Nutzungsart
- Gesamtfläche vs. Summe Raumflächen

---

## 8. Kontakt

Bei Fragen zu den Anforderungen:

**BBL - Bundesamt für Bauten und Logistik**
Abteilung CAFM
cafm@bbl.admin.ch

---

## Anhang A: Nutzungsarten nach SIA 416

| Code | Bezeichnung |
|------|-------------|
| 1 | Wohnen |
| 2 | Arbeiten |
| 3 | Bildung |
| 4 | Verkauf |
| 5 | Gastgewerbe |
| 6 | Versammlung |
| 7 | Gesundheit |
| 8 | Lager |
| 9 | Verkehr |
| 10 | Technik |
| 99 | Sonstige |
