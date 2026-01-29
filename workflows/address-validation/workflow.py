"""
EGID/GWR Checker Workflow
=========================

Validates and enriches building data against the official Swiss
Gebäude- und Wohnungsregister (GWR) via geo.admin.ch API.

API Documentation: https://docs.geo.admin.ch/access-data/find-features.html
"""

import math
import time
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import requests
from collections import defaultdict

try:
    import aiohttp
    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False


# =============================================================================
# Constants
# =============================================================================

SWISS_CANTONS = {
    'AG', 'AI', 'AR', 'BE', 'BL', 'BS', 'FR', 'GE', 'GL', 'GR',
    'JU', 'LU', 'NE', 'NW', 'OW', 'SG', 'SH', 'SO', 'SZ', 'TG',
    'TI', 'UR', 'VD', 'VS', 'ZG', 'ZH'
}

# geo.admin.ch API configuration
GWR_API_BASE = "https://api3.geo.admin.ch/rest/services/ech/MapServer/find"
GWR_LAYER = "ch.bfs.gebaeude_wohnungs_register"

# Coordinate tolerance for matching (in meters)
COORDINATE_TOLERANCE_M = 50


# =============================================================================
# Data Classes
# =============================================================================

class EvalLabel(str, Enum):
    MATCH = "Match"
    PARTIAL = "Partial"
    MISMATCH = "Mismatch"
    NOT_FOUND = "Not Found"


@dataclass
class GWRRecord:
    """Data from the GWR for a single building."""
    egid: str
    gkode: Optional[float] = None  # LV95 East
    gkodn: Optional[float] = None  # LV95 North
    wgs84_lat: Optional[float] = None
    wgs84_lon: Optional[float] = None
    gdekt: Optional[str] = None    # Canton
    ggdename: Optional[str] = None  # Municipality name
    dplz4: Optional[str] = None    # PLZ
    strname: Optional[str] = None  # Street name
    deinr: Optional[str] = None    # House number
    raw_data: Optional[Dict] = None


@dataclass
class ValidationError:
    """A validation error or warning."""
    row_index: int
    column: str
    rule_id: str
    severity: str  # 'error', 'warning', 'info'
    message: str
    value: Any = None
    suggestion: Optional[str] = None


# =============================================================================
# Helper Functions
# =============================================================================

def _extract_string(value: Any) -> Optional[str]:
    """
    Extract a string from a value that might be a list.
    GWR API sometimes returns string fields as lists (e.g., strname).
    """
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return str(value)


# =============================================================================
# GWR API Client
# =============================================================================

class GWRClient:
    """
    Client for querying the Swiss Gebäude- und Wohnungsregister (GWR)
    via the geo.admin.ch API.
    """

    def __init__(self, timeout: int = 10, rate_limit_delay: float = 0.1):
        self.timeout = timeout
        self.rate_limit_delay = rate_limit_delay
        self._session = requests.Session()
        self._last_request_time = 0

    def _rate_limit(self):
        """Ensure we don't exceed API rate limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self._last_request_time = time.time()

    def lookup_egid(self, egid: str) -> Optional[GWRRecord]:
        """
        Look up a building by EGID in the GWR.

        Args:
            egid: The Eidgenössischer Gebäudeidentifikator

        Returns:
            GWRRecord if found, None otherwise
        """
        self._rate_limit()

        params = {
            "layer": GWR_LAYER,
            "searchText": str(egid),
            "searchField": "egid",
            "returnGeometry": "false",
            "contains": "false"  # Exact match
        }

        try:
            response = self._session.get(
                GWR_API_BASE,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            if not data.get("results"):
                return None

            # Take first result (exact match)
            result = data["results"][0]
            attrs = result.get("attributes", {})

            # Convert LV95 to WGS84 if coordinates present
            gkode = attrs.get("gkode")
            gkodn = attrs.get("gkodn")
            wgs84_lat, wgs84_lon = None, None

            if gkode and gkodn:
                wgs84_lat, wgs84_lon = self._lv95_to_wgs84(gkode, gkodn)

            return GWRRecord(
                egid=str(attrs.get("egid", egid)),
                gkode=gkode,
                gkodn=gkodn,
                wgs84_lat=wgs84_lat,
                wgs84_lon=wgs84_lon,
                gdekt=_extract_string(attrs.get("gdekt")),      # Canton code (may be list)
                ggdename=_extract_string(attrs.get("ggdename")),  # Municipality (may be list)
                dplz4=str(attrs.get("dplz4")) if attrs.get("dplz4") else None,
                strname=_extract_string(attrs.get("strname")),  # Street (may be list)
                deinr=str(attrs.get("deinr")) if attrs.get("deinr") else None,
                raw_data=attrs
            )

        except requests.RequestException as e:
            print(f"GWR API error for EGID {egid}: {e}")
            return None
        except (KeyError, ValueError, TypeError) as e:
            print(f"GWR parse error for EGID {egid}: {e}")
            return None

    def lookup_batch(self, egids: List[str], progress_callback=None) -> Dict[str, Optional[GWRRecord]]:
        """
        Look up multiple EGIDs (synchronous version).

        Args:
            egids: List of EGID strings
            progress_callback: Optional callback(current, total)

        Returns:
            Dict mapping EGID to GWRRecord (or None if not found)
        """
        results = {}
        total = len(egids)

        for i, egid in enumerate(egids):
            if egid and str(egid).strip():
                results[str(egid)] = self.lookup_egid(str(egid).strip())
            else:
                results[str(egid)] = None

            if progress_callback:
                progress_callback(i + 1, total)

        return results

    async def async_lookup_egid(self, session: 'aiohttp.ClientSession', egid: str) -> Tuple[str, Optional[GWRRecord]]:
        """
        Async lookup of a single EGID.

        Returns:
            Tuple of (egid, GWRRecord or None)
        """
        params = {
            "layer": GWR_LAYER,
            "searchText": str(egid),
            "searchField": "egid",
            "returnGeometry": "false",
            "contains": "false"
        }

        try:
            async with session.get(GWR_API_BASE, params=params, timeout=aiohttp.ClientTimeout(total=self.timeout)) as response:
                if response.status != 200:
                    return (egid, None)

                data = await response.json()

                if not data.get("results"):
                    return (egid, None)

                result = data["results"][0]
                attrs = result.get("attributes", {})

                gkode = attrs.get("gkode")
                gkodn = attrs.get("gkodn")
                wgs84_lat, wgs84_lon = None, None

                if gkode and gkodn:
                    wgs84_lat, wgs84_lon = self._lv95_to_wgs84(gkode, gkodn)

                record = GWRRecord(
                    egid=str(attrs.get("egid", egid)),
                    gkode=gkode,
                    gkodn=gkodn,
                    wgs84_lat=wgs84_lat,
                    wgs84_lon=wgs84_lon,
                    gdekt=_extract_string(attrs.get("gdekt")),      # Canton (may be list)
                    ggdename=_extract_string(attrs.get("ggdename")),  # Municipality (may be list)
                    dplz4=str(attrs.get("dplz4")) if attrs.get("dplz4") else None,
                    strname=_extract_string(attrs.get("strname")),  # Street (may be list)
                    deinr=str(attrs.get("deinr")) if attrs.get("deinr") else None,
                    raw_data=attrs
                )
                return (egid, record)

        except Exception as e:
            print(f"Async GWR API error for EGID {egid}: {e}")
            return (egid, None)

    async def async_lookup_batch(self, egids: List[str], max_concurrent: int = 20,
                                  progress_callback=None) -> Dict[str, Optional[GWRRecord]]:
        """
        Look up multiple EGIDs concurrently (async version).

        Args:
            egids: List of EGID strings
            max_concurrent: Maximum concurrent requests (default 20)
            progress_callback: Optional callback(current, total, message)

        Returns:
            Dict mapping EGID to GWRRecord (or None if not found)
        """
        if not ASYNC_AVAILABLE:
            # Fallback to sync version
            return self.lookup_batch(egids, progress_callback)

        results = {}
        total = len(egids)
        completed = 0

        # Semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(max_concurrent)

        async def lookup_with_semaphore(session, egid):
            nonlocal completed
            async with semaphore:
                result = await self.async_lookup_egid(session, egid)
                completed += 1
                if progress_callback:
                    progress_callback(completed, total, f"GWR-Abfrage: {completed}/{total}")
                return result

        connector = aiohttp.TCPConnector(limit=max_concurrent, limit_per_host=max_concurrent)
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                lookup_with_semaphore(session, egid)
                for egid in egids
                if egid and str(egid).strip()
            ]

            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for item in batch_results:
                if isinstance(item, Exception):
                    continue
                if isinstance(item, tuple) and len(item) == 2:
                    egid, record = item
                    results[egid] = record

        return results

    @staticmethod
    def _lv95_to_wgs84(e: float, n: float) -> Tuple[float, float]:
        """
        Convert LV95 coordinates to WGS84.

        Based on the approximate formulas from swisstopo.
        """
        # Shift to Bern origin
        y = (e - 2600000) / 1000000
        x = (n - 1200000) / 1000000

        # Calculate longitude
        lon = 2.6779094 \
            + 4.728982 * y \
            + 0.791484 * y * x \
            + 0.1306 * y * x * x \
            - 0.0436 * y * y * y

        # Calculate latitude
        lat = 16.9023892 \
            + 3.238272 * x \
            - 0.270978 * y * y \
            - 0.002528 * x * x \
            - 0.0447 * y * y * x \
            - 0.0140 * x * x * x

        # Convert to degrees
        lon = lon * 100 / 36
        lat = lat * 100 / 36

        return round(lat, 6), round(lon, 6)


# =============================================================================
# Column Detection (Exact Match)
# =============================================================================

# Expected column names (exact match required)
EXPECTED_COLUMNS = {
    'bbl_id': 'bbl_id',
    'av_egid': 'av_egid',
    'wgs84_lat': 'wgs84_lat',
    'wgs84_lon': 'wgs84_lon',
    'adr_reg': 'adr_reg',
    'adr_ort': 'adr_ort',
    'adr_plz': 'adr_plz',
    'adr_str': 'adr_str',
    'adr_hsnr': 'adr_hsnr',
}

# Required columns (must be present)
REQUIRED_COLUMNS = ['bbl_id', 'av_egid']


def auto_detect_columns(df: pd.DataFrame) -> Dict[str, str]:
    """
    Detect columns using exact name matching.

    Args:
        df: Input DataFrame

    Returns:
        Dict mapping logical names to actual column names found in df
    """
    detected = {}
    warnings = []
    df_columns_lower = {col.lower(): col for col in df.columns}

    for logical_name, expected_name in EXPECTED_COLUMNS.items():
        if expected_name.lower() in df_columns_lower:
            detected[logical_name] = df_columns_lower[expected_name.lower()]
        else:
            # Check if column is required
            if logical_name in REQUIRED_COLUMNS:
                warnings.append(f"Pflichtfeld '{expected_name}' nicht gefunden")
            else:
                warnings.append(f"Optionales Feld '{expected_name}' nicht gefunden")

    # Print warnings if any columns are missing
    if warnings:
        print("Spalten-Warnungen:")
        for warning in warnings:
            print(f"  - {warning}")

    return detected


# =============================================================================
# GWR Enricher
# =============================================================================

class GWREnricher:
    """
    Enriches a DataFrame with GWR data and performs validation.

    The enricher will:
    - Auto-detect columns if no mapping is provided
    - Keep ALL original columns in the output
    - Add GWR output columns
    - Only require the EGID column to be present
    """

    def __init__(self, client: Optional[GWRClient] = None):
        self.client = client or GWRClient()

    def enrich(self, df: pd.DataFrame, column_mapping: Optional[Dict[str, str]] = None,
               progress_callback=None) -> Tuple[pd.DataFrame, List[ValidationError]]:
        """
        Enrich DataFrame with GWR data and validate.

        Args:
            df: Input DataFrame (can contain extra columns - only mapped ones are processed)
            column_mapping: Maps logical names to actual column names. If None or empty,
                columns will be auto-detected based on naming patterns.
                - 'bbl_id': BBL ID column
                - 'av_egid': EGID column (required)
                - 'wgs84_lat': Latitude column (optional)
                - 'wgs84_lon': Longitude column (optional)
                - 'adr_reg': Region/Canton column (optional)
                - 'adr_ort': City column (optional)
                - 'adr_plz': PLZ column (optional)
                - 'adr_str': Street column (optional)
                - 'adr_hsnr': House number column (optional)
            progress_callback: Optional callback(current, total, message)

        Returns:
            Tuple of (enriched DataFrame, list of validation errors)
        """
        errors = []
        result_df = df.copy()

        # Auto-detect columns if mapping not provided or empty
        if not column_mapping:
            column_mapping = auto_detect_columns(df)
            if progress_callback:
                detected_cols = ', '.join(f"{k}={v}" for k, v in column_mapping.items())
                progress_callback(0, 0, f"Auto-detected: {detected_cols}")

        # Get column names
        egid_col = column_mapping.get('av_egid')
        if not egid_col or egid_col not in df.columns:
            raise ValueError("EGID column not found in DataFrame")

        # Add output columns
        output_cols = [
            'gwr_wgs84_lat', 'gwr_wgs84_lon', 'gwr_gkode', 'gwr_gkodn',
            'gwr_adr_reg', 'gwr_adr_ort', 'gwr_adr_plz', 'gwr_adr_str',
            'gwr_adr_hsnr', 'eval_score', 'eval_label'
        ]
        for col in output_cols:
            result_df[col] = None

        # Collect unique EGIDs (cleaned: handle float values like 123456.0)
        def clean_egid(val):
            s = str(val).strip()
            if '.' in s:
                try:
                    return str(int(float(s)))
                except ValueError:
                    pass
            return s

        egids = list(set(clean_egid(e) for e in df[egid_col].dropna().astype(str).unique()))

        if progress_callback:
            progress_callback(0, len(egids), "GWR-Abfrage wird gestartet...")

        # Batch lookup - use async if available for better performance
        if ASYNC_AVAILABLE and len(egids) > 5:
            # Use async for larger batches (significant speedup)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If already in async context, create a new task
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            self.client.async_lookup_batch(egids, max_concurrent=20, progress_callback=progress_callback)
                        )
                        gwr_cache = future.result()
                else:
                    gwr_cache = loop.run_until_complete(
                        self.client.async_lookup_batch(egids, max_concurrent=20, progress_callback=progress_callback)
                    )
            except RuntimeError:
                # No event loop, create new one
                gwr_cache = asyncio.run(
                    self.client.async_lookup_batch(egids, max_concurrent=20, progress_callback=progress_callback)
                )
        else:
            # Use sync for small batches or when async not available
            gwr_cache = self.client.lookup_batch(
                egids,
                lambda i, t: progress_callback(i, t, f"GWR-Abfrage: {i}/{t}") if progress_callback else None
            )

        # Process each row
        for idx, row in df.iterrows():
            egid_val = row[egid_col]

            # R-GWR-01: EGID required
            if pd.isna(egid_val) or str(egid_val).strip() == '' or str(egid_val).strip() == '0':
                errors.append(ValidationError(
                    row_index=idx,
                    column=egid_col,
                    rule_id="R-GWR-01",
                    severity="error",
                    message="EGID fehlt oder ist 0/NULL",
                    value=egid_val
                ))
                result_df.at[idx, 'eval_label'] = EvalLabel.NOT_FOUND.value
                result_df.at[idx, 'eval_score'] = 0
                continue

            egid_str = str(egid_val).strip()

            # Handle float EGIDs (e.g., 123456.0)
            if '.' in egid_str:
                try:
                    egid_str = str(int(float(egid_str)))
                except ValueError:
                    pass

            # R-GWR-04a-e: Check address field completeness
            address_field_checks = [
                ('adr_reg', 'R-GWR-04a', 'Kanton (adr_reg) fehlt oder ist leer'),
                ('adr_ort', 'R-GWR-04b', 'Ort (adr_ort) fehlt oder ist leer'),
                ('adr_plz', 'R-GWR-04c', 'PLZ (adr_plz) fehlt oder ist leer'),
                ('adr_str', 'R-GWR-04d', 'Strasse (adr_str) fehlt oder ist leer'),
                ('adr_hsnr', 'R-GWR-04e', 'Hausnummer (adr_hsnr) fehlt oder ist leer'),
            ]
            for field_key, rule_id, message in address_field_checks:
                col = column_mapping.get(field_key)
                if col and col in row.index:
                    val = row.get(col)
                    if pd.isna(val) or str(val).strip() == '':
                        errors.append(ValidationError(
                            row_index=idx,
                            column=col,
                            rule_id=rule_id,
                            severity="info",
                            message=message,
                            value=val
                        ))

            # Look up GWR data
            gwr = gwr_cache.get(egid_str)

            if gwr is None:
                # R-GWR-07: EGID not found in GWR
                errors.append(ValidationError(
                    row_index=idx,
                    column=egid_col,
                    rule_id="R-GWR-07",
                    severity="error",
                    message=f"EGID {egid_str} nicht im GWR gefunden",
                    value=egid_str
                ))
                result_df.at[idx, 'eval_label'] = EvalLabel.NOT_FOUND.value
                result_df.at[idx, 'eval_score'] = 0
                continue

            # Populate GWR output columns
            result_df.at[idx, 'gwr_wgs84_lat'] = gwr.wgs84_lat
            result_df.at[idx, 'gwr_wgs84_lon'] = gwr.wgs84_lon
            result_df.at[idx, 'gwr_gkode'] = gwr.gkode
            result_df.at[idx, 'gwr_gkodn'] = gwr.gkodn
            result_df.at[idx, 'gwr_adr_reg'] = gwr.gdekt
            result_df.at[idx, 'gwr_adr_ort'] = gwr.ggdename
            result_df.at[idx, 'gwr_adr_plz'] = gwr.dplz4
            result_df.at[idx, 'gwr_adr_str'] = gwr.strname
            result_df.at[idx, 'gwr_adr_hsnr'] = gwr.deinr

            # Calculate match score
            score, field_errors = self._calculate_match_score(
                row, gwr, column_mapping, idx
            )
            errors.extend(field_errors)

            result_df.at[idx, 'eval_score'] = score

            # Determine label
            if score >= 90:
                result_df.at[idx, 'eval_label'] = EvalLabel.MATCH.value
            elif score >= 50:
                result_df.at[idx, 'eval_label'] = EvalLabel.PARTIAL.value
            else:
                result_df.at[idx, 'eval_label'] = EvalLabel.MISMATCH.value

        # R-GWR-02: Check EGID uniqueness
        egid_counts = df[egid_col].dropna().astype(str).value_counts()
        duplicates = egid_counts[egid_counts > 1]

        for egid, count in duplicates.items():
            dup_indices = df[df[egid_col].astype(str) == str(egid)].index.tolist()
            for idx in dup_indices[1:]:  # Skip first occurrence
                errors.append(ValidationError(
                    row_index=idx,
                    column=egid_col,
                    rule_id="R-GWR-02",
                    severity="warning",
                    message=f"EGID {egid} mehrfach vorhanden ({count}x)",
                    value=egid
                ))

        return result_df, errors

    def _calculate_match_score(self, row: pd.Series, gwr: GWRRecord,
                                column_mapping: Dict[str, str],
                                row_idx: int) -> Tuple[int, List[ValidationError]]:
        """
        Calculate match score between row data and GWR data.

        Returns score (0-100) and list of field-level errors.
        """
        errors = []
        matches = 0
        total_checks = 0

        # Check coordinates
        lat_col = column_mapping.get('wgs84_lat')
        lon_col = column_mapping.get('wgs84_lon')

        if lat_col and lon_col and lat_col in row.index and lon_col in row.index:
            row_lat = row.get(lat_col)
            row_lon = row.get(lon_col)

            if pd.notna(row_lat) and pd.notna(row_lon) and gwr.wgs84_lat and gwr.wgs84_lon:
                total_checks += 1
                try:
                    distance = self._haversine_distance(
                        float(row_lat), float(row_lon),
                        gwr.wgs84_lat, gwr.wgs84_lon
                    )
                    if distance <= COORDINATE_TOLERANCE_M:
                        matches += 1
                    else:
                        errors.append(ValidationError(
                            row_index=row_idx,
                            column=f"{lat_col}/{lon_col}",
                            rule_id="R-GWR-06",
                            severity="warning",
                            message=f"Koordinaten weichen um {distance:.0f}m vom GWR ab",
                            value=f"{row_lat}, {row_lon}",
                            suggestion=f"{gwr.wgs84_lat}, {gwr.wgs84_lon}"
                        ))
                except (ValueError, TypeError):
                    pass

        # Check address fields
        field_checks = [
            ('adr_reg', gwr.gdekt, "Kanton"),
            ('adr_plz', gwr.dplz4, "PLZ"),
            ('adr_ort', gwr.ggdename, "Ort"),
            ('adr_str', gwr.strname, "Strasse"),
            ('adr_hsnr', gwr.deinr, "Hausnummer"),
        ]

        mismatched_fields = []

        for field_key, gwr_value, field_label in field_checks:
            col = column_mapping.get(field_key)
            if not col or col not in row.index:
                continue

            row_value = row.get(col)

            if pd.notna(row_value) and gwr_value:
                total_checks += 1
                if self._normalize_string(str(row_value)) == self._normalize_string(str(gwr_value)):
                    matches += 1
                else:
                    mismatched_fields.append(f"{field_label}: '{row_value}' → '{gwr_value}'")

        # Report address mismatches as single error
        if mismatched_fields:
            errors.append(ValidationError(
                row_index=row_idx,
                column="Adresse",
                rule_id="R-GWR-05",
                severity="warning",
                message=f"Adresse weicht vom GWR ab: {'; '.join(mismatched_fields)}",
                value=None
            ))

        # Calculate percentage
        if total_checks == 0:
            return 100, errors  # No data to compare = assume match

        score = int((matches / total_checks) * 100)
        return score, errors

    @staticmethod
    def _normalize_string(s: str) -> str:
        """Normalize string for comparison."""
        return s.strip().lower().replace('.', '').replace(',', '')

    @staticmethod
    def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two WGS84 coordinates in meters.
        """
        R = 6371000  # Earth radius in meters

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = math.sin(delta_phi / 2) ** 2 + \
            math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return R * c


# =============================================================================
# Main Workflow Function
# =============================================================================

def run_gwr_check(df: pd.DataFrame, column_mapping: Optional[Dict[str, str]] = None,
                  progress_callback=None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Run the GWR check workflow.

    Args:
        df: Input DataFrame with building data (can contain extra columns)
        column_mapping: Maps logical names to actual column names.
            If None or empty, columns will be auto-detected.
        progress_callback: Optional progress callback

    Returns:
        Tuple of (enriched DataFrame, results dict)
    """
    enricher = GWREnricher()
    enriched_df, errors = enricher.enrich(df, column_mapping, progress_callback)

    # Build results summary
    total_rows = len(df)
    error_count = len([e for e in errors if e.severity == 'error'])
    warning_count = len([e for e in errors if e.severity == 'warning'])
    info_count = len([e for e in errors if e.severity == 'info'])

    # Count by eval_label
    label_counts = enriched_df['eval_label'].value_counts().to_dict()

    results = {
        'total_rows': total_rows,
        'error_count': error_count,
        'warning_count': warning_count,
        'info_count': info_count,
        'passed_rows': total_rows - len(set(e.row_index for e in errors if e.severity == 'error')),
        'match_count': label_counts.get(EvalLabel.MATCH.value, 0),
        'partial_count': label_counts.get(EvalLabel.PARTIAL.value, 0),
        'mismatch_count': label_counts.get(EvalLabel.MISMATCH.value, 0),
        'not_found_count': label_counts.get(EvalLabel.NOT_FOUND.value, 0),
        'errors': [
            {
                'row_number': e.row_index + 2,  # Excel row (1-indexed + header)
                'column': e.column,
                'rule_id': e.rule_id,
                'severity': e.severity,
                'message': e.message,
                'value': str(e.value) if e.value is not None else None,
                'suggestion': e.suggestion
            }
            for e in errors
        ]
    }

    return enriched_df, results


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Test GWR lookup
    client = GWRClient()

    # Test with a real EGID (Bundeshaus in Bern)
    test_egid = "1231641"
    print(f"Looking up EGID {test_egid}...")

    result = client.lookup_egid(test_egid)

    if result:
        print(f"  Found: {result.strname} {result.deinr}, {result.dplz4} {result.ggdename}")
        print(f"  Canton: {result.gdekt}")
        print(f"  Coordinates (LV95): E={result.gkode}, N={result.gkodn}")
        print(f"  Coordinates (WGS84): Lat={result.wgs84_lat}, Lon={result.wgs84_lon}")
    else:
        print("  Not found")
