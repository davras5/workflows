"""
Address Validation Workflow
===========================

Validation rules and logic for Swiss address validation.
Business documentation: see README.md
"""

from typing import List, Dict, Any
import pandas as pd
from collections import defaultdict

# Import base classes from core
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))

from core.base import BaseRule, ValidationError, Severity


# =============================================================================
# Constants
# =============================================================================

SWISS_CANTONS = {
    'AG', 'AI', 'AR', 'BE', 'BL', 'BS', 'FR', 'GE', 'GL', 'GR',
    'JU', 'LU', 'NE', 'NW', 'OW', 'SG', 'SH', 'SO', 'SZ', 'TG',
    'TI', 'UR', 'VD', 'VS', 'ZG', 'ZH'
}

# Switzerland bounds (LV95)
CH_BOUNDS_LV95 = {
    'e_min': 2485000, 'e_max': 2834000,
    'n_min': 1075000, 'n_max': 1296000
}

# Switzerland bounds (WGS84)
CH_BOUNDS_WGS84 = {
    'lon_min': 5.9, 'lon_max': 10.5,
    'lat_min': 45.8, 'lat_max': 47.9
}


# =============================================================================
# RULES: Vollständigkeit (Completeness)
# =============================================================================

class RequiredFieldsRule(BaseRule):
    """
    R-ADDR-001: Pflichtfelder
    Prüft ob PLZ und Ort ausgefüllt sind.
    """
    rule_id = "R-ADDR-001"

    def validate(self, df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationError]:
        errors = []

        required = [('plz', 'PLZ'), ('ort', 'Ort')]

        for field, label in required:
            col = self.get_column(df, config, field)
            if col is None:
                continue

            for idx, row in df.iterrows():
                val = row[col]
                if pd.isna(val) or str(val).strip() == '':
                    errors.append(ValidationError(
                        row_index=idx,
                        column=col,
                        rule_id=self.rule_id,
                        severity=Severity.ERROR,
                        message=f"{label} fehlt oder ist leer",
                        value=None
                    ))

        return errors


class CoordinatePresenceRule(BaseRule):
    """
    R-ADDR-005: Koordinaten vorhanden
    Prüft ob E- und N-Koordinaten beide vorhanden sind.
    """
    rule_id = "R-ADDR-005"

    def validate(self, df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationError]:
        errors = []

        e_col = self.get_column(df, config, 'easting')
        n_col = self.get_column(df, config, 'northing')

        if e_col is None or n_col is None:
            return errors

        for idx, row in df.iterrows():
            e_val = row[e_col]
            n_val = row[n_col]

            e_empty = pd.isna(e_val) or str(e_val).strip() == ''
            n_empty = pd.isna(n_val) or str(n_val).strip() == ''

            if e_empty and not n_empty:
                errors.append(ValidationError(
                    row_index=idx, column=e_col, rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message="E-Koordinate fehlt (N vorhanden)"
                ))
            elif n_empty and not e_empty:
                errors.append(ValidationError(
                    row_index=idx, column=n_col, rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message="N-Koordinate fehlt (E vorhanden)"
                ))

        return errors


class EGIDPresenceRule(BaseRule):
    """
    R-ADDR-008: EGID vorhanden
    Jeder Datensatz sollte eine EGID haben.
    """
    rule_id = "R-ADDR-008"

    def validate(self, df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationError]:
        errors = []

        egid_col = self.get_column(df, config, 'egid')
        if egid_col is None:
            return errors

        for idx, row in df.iterrows():
            val = row[egid_col]
            if pd.isna(val) or str(val).strip() == '':
                errors.append(ValidationError(
                    row_index=idx, column=egid_col, rule_id=self.rule_id,
                    severity=Severity.ERROR,
                    message="EGID fehlt"
                ))

        return errors


# =============================================================================
# RULES: Format
# =============================================================================

class PLZFormatRule(BaseRule):
    """
    R-ADDR-002: PLZ-Format
    Schweizer PLZ muss 4-stellig sein (1000-9999).
    """
    rule_id = "R-ADDR-002"

    def validate(self, df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationError]:
        errors = []

        plz_col = self.get_column(df, config, 'plz')
        if plz_col is None:
            return errors

        for idx, row in df.iterrows():
            val = row[plz_col]

            if pd.isna(val) or str(val).strip() == '':
                continue

            plz_str = str(val).strip()

            # Handle floats like 8001.0
            if '.' in plz_str:
                try:
                    plz_str = str(int(float(plz_str)))
                except ValueError:
                    pass

            if not plz_str.isdigit():
                errors.append(ValidationError(
                    row_index=idx, column=plz_col, rule_id=self.rule_id,
                    severity=Severity.ERROR,
                    message=f"PLZ nicht numerisch: '{val}'",
                    value=val
                ))
            elif len(plz_str) != 4:
                errors.append(ValidationError(
                    row_index=idx, column=plz_col, rule_id=self.rule_id,
                    severity=Severity.ERROR,
                    message=f"PLZ nicht 4-stellig: '{val}'",
                    value=val
                ))
            elif not (1000 <= int(plz_str) <= 9999):
                errors.append(ValidationError(
                    row_index=idx, column=plz_col, rule_id=self.rule_id,
                    severity=Severity.ERROR,
                    message=f"PLZ ausserhalb 1000-9999: '{val}'",
                    value=val
                ))

        return errors


class CantonValidationRule(BaseRule):
    """
    R-ADDR-003: Kanton gültig
    Kantonsabkürzung muss gültig sein.
    """
    rule_id = "R-ADDR-003"

    def validate(self, df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationError]:
        errors = []

        kanton_col = self.get_column(df, config, 'kanton')
        if kanton_col is None:
            return errors

        for idx, row in df.iterrows():
            val = row[kanton_col]

            if pd.isna(val) or str(val).strip() == '':
                continue

            kanton = str(val).strip().upper()

            if kanton not in SWISS_CANTONS:
                errors.append(ValidationError(
                    row_index=idx, column=kanton_col, rule_id=self.rule_id,
                    severity=Severity.ERROR,
                    message=f"Ungültiger Kanton: '{val}'",
                    value=val
                ))

        return errors


class StreetFormatRule(BaseRule):
    """
    R-ADDR-004: Strassenformat
    Prüft Strassennamen auf offensichtliche Fehler.
    """
    rule_id = "R-ADDR-004"

    def validate(self, df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationError]:
        errors = []

        strasse_col = self.get_column(df, config, 'strasse')
        if strasse_col is None:
            return errors

        for idx, row in df.iterrows():
            val = row[strasse_col]

            if pd.isna(val) or str(val).strip() == '':
                continue

            strasse = str(val).strip()

            if strasse.isdigit():
                errors.append(ValidationError(
                    row_index=idx, column=strasse_col, rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message=f"Strasse nur numerisch: '{val}'",
                    value=val
                ))
            elif len(strasse) < 3:
                errors.append(ValidationError(
                    row_index=idx, column=strasse_col, rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    message=f"Strasse sehr kurz: '{val}'",
                    value=val
                ))

        return errors


class EGIDFormatRule(BaseRule):
    """
    R-ADDR-007: EGID-Format
    EGID muss eine positive Ganzzahl sein.
    """
    rule_id = "R-ADDR-007"

    def validate(self, df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationError]:
        errors = []

        egid_col = self.get_column(df, config, 'egid')
        if egid_col is None:
            return errors

        for idx, row in df.iterrows():
            val = row[egid_col]

            if pd.isna(val) or str(val).strip() == '':
                continue

            try:
                egid_str = str(val).strip()
                if '.' in egid_str:
                    egid = int(float(egid_str))
                else:
                    egid = int(egid_str)

                if egid <= 0:
                    errors.append(ValidationError(
                        row_index=idx, column=egid_col, rule_id=self.rule_id,
                        severity=Severity.ERROR,
                        message=f"EGID muss positiv sein: '{val}'",
                        value=val
                    ))
            except (ValueError, TypeError):
                errors.append(ValidationError(
                    row_index=idx, column=egid_col, rule_id=self.rule_id,
                    severity=Severity.ERROR,
                    message=f"EGID ungültiges Format: '{val}'",
                    value=val
                ))

        return errors


# =============================================================================
# RULES: Konsistenz (Consistency)
# =============================================================================

class SwissBoundsRule(BaseRule):
    """
    R-ADDR-006: Koordinaten in Schweiz
    Koordinaten müssen innerhalb der Schweizer Grenzen liegen.
    """
    rule_id = "R-ADDR-006"

    def validate(self, df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationError]:
        errors = []

        e_col = self.get_column(df, config, 'easting')
        n_col = self.get_column(df, config, 'northing')

        if e_col is None or n_col is None:
            return errors

        for idx, row in df.iterrows():
            e_val = row[e_col]
            n_val = row[n_col]

            if pd.isna(e_val) or pd.isna(n_val):
                continue

            try:
                e = float(e_val)
                n = float(n_val)
            except (ValueError, TypeError):
                errors.append(ValidationError(
                    row_index=idx, column=f"{e_col}/{n_col}", rule_id=self.rule_id,
                    severity=Severity.ERROR,
                    message=f"Ungültige Koordinaten: E={e_val}, N={n_val}",
                    value=f"{e_val}, {n_val}"
                ))
                continue

            # Detect coordinate system
            if 2000000 < e < 3000000 and 1000000 < n < 2000000:
                # LV95
                bounds = CH_BOUNDS_LV95
                if not (bounds['e_min'] <= e <= bounds['e_max']):
                    errors.append(ValidationError(
                        row_index=idx, column=e_col, rule_id=self.rule_id,
                        severity=Severity.ERROR,
                        message=f"E-Koordinate ausserhalb CH: {e}",
                        value=e
                    ))
                if not (bounds['n_min'] <= n <= bounds['n_max']):
                    errors.append(ValidationError(
                        row_index=idx, column=n_col, rule_id=self.rule_id,
                        severity=Severity.ERROR,
                        message=f"N-Koordinate ausserhalb CH: {n}",
                        value=n
                    ))
            elif 5 < e < 11 and 45 < n < 48:
                # WGS84
                bounds = CH_BOUNDS_WGS84
                if not (bounds['lon_min'] <= e <= bounds['lon_max']):
                    errors.append(ValidationError(
                        row_index=idx, column=e_col, rule_id=self.rule_id,
                        severity=Severity.ERROR,
                        message=f"Longitude ausserhalb CH: {e}",
                        value=e
                    ))
                if not (bounds['lat_min'] <= n <= bounds['lat_max']):
                    errors.append(ValidationError(
                        row_index=idx, column=n_col, rule_id=self.rule_id,
                        severity=Severity.ERROR,
                        message=f"Latitude ausserhalb CH: {n}",
                        value=n
                    ))
            else:
                errors.append(ValidationError(
                    row_index=idx, column=f"{e_col}/{n_col}", rule_id=self.rule_id,
                    severity=Severity.ERROR,
                    message=f"Koordinatensystem nicht erkannt: E={e}, N={n}",
                    value=f"{e}, {n}"
                ))

        return errors


# =============================================================================
# RULES: Duplikate
# =============================================================================

class DuplicateAddressRule(BaseRule):
    """
    R-ADDR-009: Doppelte Adressen
    Erkennt doppelte Adressen basierend auf PLZ+Ort+Strasse.
    """
    rule_id = "R-ADDR-009"

    def validate(self, df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationError]:
        errors = []

        plz_col = self.get_column(df, config, 'plz')
        ort_col = self.get_column(df, config, 'ort')
        strasse_col = self.get_column(df, config, 'strasse')

        if plz_col is None or ort_col is None:
            return errors

        # Build address key -> rows mapping
        address_rows = defaultdict(list)

        for idx, row in df.iterrows():
            plz = str(row[plz_col]).strip() if pd.notna(row[plz_col]) else ''
            ort = str(row[ort_col]).strip().lower() if pd.notna(row[ort_col]) else ''
            strasse = str(row[strasse_col]).strip().lower() if strasse_col and pd.notna(row.get(strasse_col)) else ''

            if plz and ort:
                key = f"{plz}|{ort}|{strasse}"
                address_rows[key].append(idx)

        # Report duplicates
        for key, rows in address_rows.items():
            if len(rows) > 1:
                for idx in rows[1:]:
                    errors.append(ValidationError(
                        row_index=idx, column="Adresse", rule_id=self.rule_id,
                        severity=Severity.WARNING,
                        message=f"Mögliches Duplikat (Zeilen: {', '.join(str(r+2) for r in rows)})",
                        value=key.replace('|', ', ')
                    ))

        return errors


class DuplicateEGIDRule(BaseRule):
    """
    R-ADDR-010: Doppelte EGIDs
    Jede EGID sollte nur einmal vorkommen.
    """
    rule_id = "R-ADDR-010"

    def validate(self, df: pd.DataFrame, config: Dict[str, Any]) -> List[ValidationError]:
        errors = []

        egid_col = self.get_column(df, config, 'egid')
        if egid_col is None:
            return errors

        egid_rows = defaultdict(list)

        for idx, row in df.iterrows():
            val = row[egid_col]
            if pd.isna(val) or str(val).strip() == '':
                continue

            # Normalize
            try:
                egid_str = str(val).strip()
                if '.' in egid_str:
                    egid_key = str(int(float(egid_str)))
                else:
                    egid_key = egid_str
                egid_rows[egid_key].append(idx)
            except (ValueError, TypeError):
                continue

        for egid, rows in egid_rows.items():
            if len(rows) > 1:
                for idx in rows[1:]:
                    errors.append(ValidationError(
                        row_index=idx, column=egid_col, rule_id=self.rule_id,
                        severity=Severity.WARNING,
                        message=f"EGID mehrfach vorhanden (Zeilen: {', '.join(str(r+2) for r in rows)})",
                        value=egid
                    ))

        return errors


# =============================================================================
# Export all rules
# =============================================================================

ALL_RULES = [
    # Vollständigkeit
    RequiredFieldsRule,
    CoordinatePresenceRule,
    EGIDPresenceRule,
    # Format
    PLZFormatRule,
    CantonValidationRule,
    StreetFormatRule,
    EGIDFormatRule,
    # Konsistenz
    SwissBoundsRule,
    # Duplikate
    DuplicateAddressRule,
    DuplicateEGIDRule,
]

# Rule class lookup by ID
RULE_CLASSES = {rule.rule_id: rule for rule in ALL_RULES}
