"""
GeoDataCheck API - FastAPI backend for geo data validation.

Run with: uvicorn main:app --reload
"""

import io
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import pandas as pd

from validation import (
    create_default_registry,
    ValidationEngine,
    ValidationResult,
)


# Session storage (in-memory, no persistence)
sessions: Dict[str, dict] = {}
SESSION_TIMEOUT_MINUTES = 30


class SessionData:
    """In-memory session data, cleared on timeout."""

    def __init__(self, df: pd.DataFrame, result: ValidationResult, config: dict):
        self.df = df
        self.result = result
        self.config = config
        self.created_at = datetime.now()
        self.expires_at = datetime.now() + timedelta(minutes=SESSION_TIMEOUT_MINUTES)

    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at

    def cleanup(self):
        """Explicitly clear data from memory."""
        self.df = None
        self.result = None
        self.config = None


def cleanup_expired_sessions():
    """Remove expired sessions."""
    expired = [
        sid for sid, data in sessions.items()
        if isinstance(data, SessionData) and data.is_expired()
    ]
    for sid in expired:
        if sid in sessions:
            sessions[sid].cleanup()
            del sessions[sid]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    print("GeoDataCheck API starting...")
    yield
    # Shutdown - cleanup all sessions
    print("Cleaning up sessions...")
    for sid, data in sessions.items():
        if isinstance(data, SessionData):
            data.cleanup()
    sessions.clear()


# Initialize FastAPI app
app = FastAPI(
    title="GeoDataCheck API",
    description="Geo data validation service for Swiss building portfolios",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize validation engine
registry = create_default_registry()
engine = ValidationEngine(registry)


# Pydantic models for API
class ValidationConfig(BaseModel):
    columns: Dict[str, str] = {}
    options: Dict[str, Any] = {}
    rule_ids: Optional[List[str]] = None
    dimension_columns: Dict[str, str] = {}  # region, portfolio, responsible


class ColumnInfo(BaseModel):
    name: str
    detected_as: Optional[str] = None
    sample_values: List[str] = []


class UploadResponse(BaseModel):
    session_id: str
    columns: List[ColumnInfo]
    detected_mappings: Dict[str, str]
    row_count: int
    expires_in_minutes: int


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Serve the frontend HTML."""
    # In Docker: /app/backend/main.py, index.html is at /app/index.html
    index_path = Path(__file__).parent.parent / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    # Fallback for local development
    local_path = Path(__file__).parent.parent / "index.html"
    if local_path.exists():
        return FileResponse(local_path, media_type="text/html")
    return {"error": "index.html not found"}


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "GeoDataCheck API", "version": "1.0.0"}


@app.get("/assets/{filename:path}")
async def serve_assets(filename: str):
    """Serve static assets (logos, icons)."""
    assets_path = Path(__file__).parent.parent / "assets" / filename
    if assets_path.exists() and assets_path.is_file():
        # Determine media type
        suffix = assets_path.suffix.lower()
        media_types = {
            '.svg': 'image/svg+xml',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.ico': 'image/x-icon',
            '.css': 'text/css',
            '.js': 'application/javascript',
        }
        media_type = media_types.get(suffix, 'application/octet-stream')
        return FileResponse(assets_path, media_type=media_type)
    raise HTTPException(status_code=404, detail=f"Asset not found: {filename}")


@app.get("/api/rules")
async def get_rules():
    """Get documentation for all validation rules."""
    cleanup_expired_sessions()
    return {"rules": registry.get_documentation()}


@app.get("/api/rules/{category}")
async def get_rules_by_category(category: str):
    """Get rules by category."""
    from validation import Category
    try:
        cat = Category(category)
        rules = registry.get_rules_by_category(cat)
        return {"rules": [r.metadata.to_dict() for r in rules]}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid category: {category}")


# ============================================================================
# Workflows (loaded from workflows.json)
# ============================================================================

def load_workflows() -> List[Dict[str, Any]]:
    """Load workflow definitions from workflows.json."""
    workflows_path = Path(__file__).parent.parent / "workflows" / "workflows.json"
    with open(workflows_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("workflows", [])


# Load workflows at startup
WORKFLOWS = load_workflows()


def get_workflow_by_id(workflow_id: str) -> Optional[Dict[str, Any]]:
    """Get a workflow by its ID."""
    for workflow in WORKFLOWS:
        if workflow['id'] == workflow_id:
            return workflow
    return None


@app.get("/api/workflows")
async def get_workflows():
    """Get all available workflow configurations."""
    # Return simplified list for gallery view
    return {
        "workflows": [
            {
                "id": w["id"],
                "name": w["name"],
                "type": w.get("type", "checker"),
                "description": w["description"],
                "description_long": w.get("description_long", w["description"]),
                "category": w.get("category", ""),
                "icon": w.get("icon", ""),
                "input_formats": w.get("input", {}).get("formats", []),
                "required_columns": [inp.get("name", inp.get("id")) for inp in w.get("inputs", []) if inp.get("required", False)],
            }
            for w in WORKFLOWS
        ]
    }


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get a specific workflow configuration with full details."""
    workflow = get_workflow_by_id(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    return workflow


# ============================================================================
# Workflow-Centric Endpoints
# ============================================================================

@app.post("/api/workflows/{workflow_id}/upload", response_model=UploadResponse)
async def workflow_upload(workflow_id: str, file: UploadFile = File(...)):
    """
    Upload a file for a specific workflow.

    Returns session ID and detected column information.
    """
    cleanup_expired_sessions()

    # Verify workflow exists
    workflow = get_workflow_by_id(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

    # Check file format against workflow's accepted formats
    input_config = workflow.get('input', {})
    allowed_formats = input_config.get('formats', ['.xlsx', '.xls'])

    file_ext = '.' + file.filename.split('.')[-1].lower() if '.' in file.filename else ''
    if file_ext not in allowed_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file format. This workflow accepts: {', '.join(allowed_formats)}"
        )

    # Check file size if specified
    max_size_mb = input_config.get('max_size_mb')
    if max_size_mb:
        contents = await file.read()
        if len(contents) > max_size_mb * 1024 * 1024:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {max_size_mb} MB"
            )
        await file.seek(0)  # Reset file position

    try:
        # Read file into memory
        contents = await file.read()

        # Read based on file extension
        if file_ext == '.csv':
            df = pd.read_csv(io.BytesIO(contents))
        else:
            # For Excel files, auto-detect the best sheet
            excel_file = pd.ExcelFile(io.BytesIO(contents))
            sheet_names = excel_file.sheet_names

            if len(sheet_names) == 1:
                # Only one sheet, use it
                df = pd.read_excel(excel_file, sheet_name=0)
            else:
                # Multiple sheets - find the one with expected columns
                # Get expected column names from workflow inputs
                expected_cols = set()
                for inp in workflow.get('inputs', []):
                    col_name = inp.get('name', inp.get('id', ''))
                    if col_name:
                        expected_cols.add(col_name.lower())

                best_sheet = None
                best_score = -1

                for sheet_name in sheet_names:
                    try:
                        sheet_df = pd.read_excel(excel_file, sheet_name=sheet_name)
                        if len(sheet_df) == 0:
                            continue

                        # Count matching columns (case-insensitive)
                        sheet_cols = set(c.lower() for c in sheet_df.columns)
                        matches = len(expected_cols & sheet_cols)

                        # Prefer sheets with more matches, or more data if tied
                        score = matches * 1000 + len(sheet_df)
                        if score > best_score:
                            best_score = score
                            best_sheet = sheet_name
                    except Exception:
                        continue

                if best_sheet:
                    df = pd.read_excel(excel_file, sheet_name=best_sheet)
                else:
                    # Fallback to first sheet
                    df = pd.read_excel(excel_file, sheet_name=0)

        if len(df) == 0:
            raise HTTPException(status_code=400, detail="File is empty")

        # Detect column mappings
        detected = engine.detect_columns(df)

        # Build column info with samples
        columns_info = []
        for col in df.columns:
            sample_values = df[col].dropna().head(3).astype(str).tolist()
            detected_as = None
            for logical, actual in detected.items():
                if actual == col:
                    detected_as = logical
                    break
            columns_info.append(ColumnInfo(
                name=col,
                detected_as=detected_as,
                sample_values=sample_values,
            ))

        # Create session with workflow context
        session_id = str(uuid.uuid4())
        sessions[session_id] = {
            'df': df,
            'filename': file.filename,
            'workflow_id': workflow_id,
            'workflow': workflow,
            'created_at': datetime.now(),
        }

        return UploadResponse(
            session_id=session_id,
            columns=columns_info,
            detected_mappings=detected,
            row_count=len(df),
            expires_in_minutes=SESSION_TIMEOUT_MINUTES,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")


@app.post("/api/workflows/{workflow_id}/sessions/{session_id}/validate")
async def workflow_validate(workflow_id: str, session_id: str, config: ValidationConfig):
    """
    Run validation for a specific workflow on uploaded data.

    Returns validation results with dimensional breakdowns.
    """
    cleanup_expired_sessions()

    # Verify workflow exists
    workflow = get_workflow_by_id(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    session = sessions[session_id]

    # Verify session belongs to this workflow
    if session.get('workflow_id') != workflow_id:
        raise HTTPException(status_code=400, detail="Session does not belong to this workflow")

    df = session.get('df')
    if df is None:
        raise HTTPException(status_code=404, detail="Session data not available")

    # Build config - use workflow's default rules if none specified
    rule_ids = config.rule_ids
    if rule_ids is None and workflow.get('rules'):
        # Use workflow's enabled rules by default
        rule_ids = [r['id'] for r in workflow['rules'] if r.get('default_enabled', True)]

    validation_config = {
        'columns': config.columns or engine.detect_columns(df),
        'options': config.options,
    }

    # Check if this is the GWR enricher workflow
    if workflow_id == 'egid-gwr-checker':
        # Use the GWR workflow enricher
        try:
            import sys
            from pathlib import Path
            # Add workflows directory to path
            workflows_dir = Path(__file__).parent.parent / "workflows" / "address-validation"
            if str(workflows_dir) not in sys.path:
                sys.path.insert(0, str(workflows_dir))

            from workflow import run_gwr_check, auto_detect_columns as gwr_auto_detect

            # Use GWR workflow's own column detection (knows about av_egid, etc.)
            # Override the generic engine detection with GWR-specific detection
            gwr_columns = gwr_auto_detect(df)

            # Run GWR enrichment with detected columns
            enriched_df, gwr_results = run_gwr_check(df, gwr_columns)

            # Store enriched dataframe and detected columns in session
            session['enriched_df'] = enriched_df
            session['result'] = gwr_results
            session['config'] = validation_config
            session['detected_gwr_columns'] = gwr_columns  # For export to find bbl_id etc.

            return gwr_results

        except ImportError as e:
            raise HTTPException(status_code=500, detail=f"GWR workflow module not available: {e}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"GWR validation failed: {e}")

    # Default: Run standard validation
    result = engine.validate(df, validation_config, rule_ids)

    # Add dimensional analysis
    result_dict = result.to_dict()

    # Add dimension breakdowns if columns specified
    for dim_name, dim_col in config.dimension_columns.items():
        if dim_col and dim_col in df.columns:
            result_dict[f'by_{dim_name}'] = result.get_errors_by_dimension(df, dim_col)

    # Store result in session
    session['result'] = result
    session['enriched_df'] = df  # No enrichment for standard validation
    session['config'] = validation_config

    return result_dict


@app.get("/api/workflows/{workflow_id}/sessions/{session_id}/report")
async def workflow_download_report(workflow_id: str, session_id: str):
    """
    Download validation report for a workflow session.

    Creates an Excel file with multiple tabs:
    - Rules: Description of validation rules used
    - Meta: Input/output column definitions
    - Input: Original uploaded data
    - Output: Enrichment result columns (bbl_id + gwr_* + eval_*)
    - Warnings: All errors and warnings
    """
    cleanup_expired_sessions()

    # Verify workflow exists
    workflow = get_workflow_by_id(workflow_id)
    if not workflow:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found or expired")

    session = sessions[session_id]

    # Verify session belongs to this workflow
    if session.get('workflow_id') != workflow_id:
        raise HTTPException(status_code=400, detail="Session does not belong to this workflow")

    result = session.get('result')
    if result is None:
        raise HTTPException(status_code=400, detail="No validation results. Run validation first.")

    original_df = session.get('df')
    enriched_df = session.get('enriched_df', original_df)  # Fallback to original if no enrichment

    # Create Excel report
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:

        # ─────────────────────────────────────────────────────────────────────
        # Tab 1: Rules - Description of validation rules used
        # ─────────────────────────────────────────────────────────────────────
        rules = workflow.get('rules', [])
        if rules:
            rules_data = []
            for rule in rules:
                rules_data.append({
                    'Regel-ID': rule.get('id', ''),
                    'Name': rule.get('name_de', rule.get('name', '')),
                    'Beschreibung': rule.get('description_de', rule.get('description', '')),
                    'Schweregrad': rule.get('severity', ''),
                    'Kategorie': rule.get('category', ''),
                    'Standard aktiv': 'Ja' if rule.get('default_enabled', True) else 'Nein'
                })
            pd.DataFrame(rules_data).to_excel(writer, sheet_name='Rules', index=False)

        # ─────────────────────────────────────────────────────────────────────
        # Tab 2: Meta - Input/output column definitions
        # ─────────────────────────────────────────────────────────────────────
        meta_data = []

        # Input columns
        for col in workflow.get('inputs', []):
            meta_data.append({
                'Typ': 'Input',
                'Spalte': col.get('name', col.get('id', '')),
                'Beschreibung': col.get('description', ''),
                'Format': col.get('format', ''),
                'Pflicht': 'Ja' if col.get('required', False) else 'Nein',
                'Beispiel': col.get('example', ''),
                'Erlaubte Werte': ', '.join(col.get('allowed_values', [])) if col.get('allowed_values') else ''
            })

        # Output columns
        for col in workflow.get('outputs', []):
            meta_data.append({
                'Typ': 'Output',
                'Spalte': col.get('name', col.get('id', '')),
                'Beschreibung': col.get('description', ''),
                'Format': col.get('format', ''),
                'Pflicht': 'Ja' if col.get('required', False) else 'Nein',
                'Beispiel': col.get('example', ''),
                'Erlaubte Werte': ', '.join(col.get('allowed_values', [])) if col.get('allowed_values') else ''
            })

        if meta_data:
            pd.DataFrame(meta_data).to_excel(writer, sheet_name='Meta', index=False)

        # ─────────────────────────────────────────────────────────────────────
        # Tab 3: Input - Original uploaded data
        # ─────────────────────────────────────────────────────────────────────
        if original_df is not None:
            original_df.to_excel(writer, sheet_name='Input', index=False)

        # ─────────────────────────────────────────────────────────────────────
        # Tab 4: Output - Input reference columns + enrichment output columns
        # ─────────────────────────────────────────────────────────────────────
        # Get column IDs from workflow definition
        input_col_ids = [col.get('id', col.get('name', '')) for col in workflow.get('inputs', [])]
        output_col_ids = [col.get('id', col.get('name', '')) for col in workflow.get('outputs', [])]

        # Get detected column mappings for finding actual column names
        detected_columns = session.get('detected_gwr_columns', {})

        # Find the actual bbl_id column name
        id_col = None
        if detected_columns.get('bbl_id') and enriched_df is not None:
            if detected_columns['bbl_id'] in enriched_df.columns:
                id_col = detected_columns['bbl_id']

        # Fallback to common names if not detected
        if not id_col:
            for possible_id in ['bbl_id', 'id', 'ID', 'Id', 'BBL_ID', 'object_id', 'objekt_id']:
                if enriched_df is not None and possible_id in enriched_df.columns:
                    id_col = possible_id
                    break

        # Build output dataframe: input columns (for reference) + output columns
        output_cols = []

        if enriched_df is not None:
            # First add input columns (using detected mappings to find actual names)
            for logical_id in input_col_ids:
                actual_col = detected_columns.get(logical_id)
                if actual_col and actual_col in enriched_df.columns and actual_col not in output_cols:
                    output_cols.append(actual_col)
                elif logical_id in enriched_df.columns and logical_id not in output_cols:
                    output_cols.append(logical_id)

            # Then add output columns (GWR enrichment results)
            for col_id in output_col_ids:
                if col_id in enriched_df.columns and col_id not in output_cols:
                    output_cols.append(col_id)

            if output_cols:
                output_df = enriched_df[output_cols].copy()
                output_df.to_excel(writer, sheet_name='Output', index=False)

        # ─────────────────────────────────────────────────────────────────────
        # Tab 5: Warnings - All errors and warnings with details
        # ─────────────────────────────────────────────────────────────────────
        # Handle both object (ValidationResult) and dict (GWR workflow) formats
        errors_list = result.get('errors', []) if isinstance(result, dict) else getattr(result, 'errors', [])

        if errors_list:
            warnings_data = []
            for e in errors_list:
                error_dict = e.to_dict() if hasattr(e, 'to_dict') else e

                # Try to get bbl_id from the original data
                bbl_id = ''
                row_num = error_dict.get('row_number', error_dict.get('row_index'))
                if row_num is not None and original_df is not None:
                    # row_number is Excel row (1-indexed + header), convert to df index
                    df_idx = row_num - 2 if isinstance(row_num, int) and row_num >= 2 else row_num
                    if id_col and isinstance(df_idx, int) and 0 <= df_idx < len(original_df):
                        try:
                            bbl_id = original_df.iloc[df_idx][id_col]
                        except (KeyError, IndexError):
                            bbl_id = ''

                warnings_data.append({
                    'bbl_id': bbl_id,
                    'Zeile': row_num,
                    'Regel-ID': error_dict.get('rule_id', ''),
                    'Regel': error_dict.get('rule_name', error_dict.get('rule_id', '')),
                    'Spalte': error_dict.get('column', ''),
                    'Wert': error_dict.get('value', ''),
                    'Schweregrad': error_dict.get('severity', ''),
                    'Meldung': error_dict.get('message', ''),
                    'Vorschlag': error_dict.get('suggestion', '')
                })

            warnings_df = pd.DataFrame(warnings_data)
            warnings_df.to_excel(writer, sheet_name='Warnings', index=False)

        # ─────────────────────────────────────────────────────────────────────
        # Auto-fit column widths for all sheets
        # ─────────────────────────────────────────────────────────────────────
        for sheet_name in writer.sheets:
            worksheet = writer.sheets[sheet_name]
            for column_cells in worksheet.columns:
                max_length = 0
                column_letter = column_cells[0].column_letter
                for cell in column_cells:
                    try:
                        cell_value = str(cell.value) if cell.value is not None else ''
                        max_length = max(max_length, len(cell_value))
                    except:
                        pass
                # Add padding, cap at reasonable max width
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width

    output.seek(0)

    filename = session.get('filename', 'data').replace('.xlsx', '').replace('.xls', '').replace('.csv', '')
    workflow_name = workflow['id'].replace('-', '_')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}_{workflow_name}_{timestamp}.xlsx"
        }
    )


@app.delete("/api/workflows/{workflow_id}/sessions/{session_id}")
async def workflow_delete_session(workflow_id: str, session_id: str):
    """
    Delete a workflow session and all associated data.
    """
    if session_id in sessions:
        session = sessions[session_id]

        # Verify session belongs to this workflow (if workflow_id stored)
        if session.get('workflow_id') and session.get('workflow_id') != workflow_id:
            raise HTTPException(status_code=400, detail="Session does not belong to this workflow")

        if isinstance(session, SessionData):
            session.cleanup()
        elif isinstance(session, dict):
            session.clear()
        del sessions[session_id]

    return {"status": "ok", "message": "Session deleted"}


# ============================================================================
# Run server (development)
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
