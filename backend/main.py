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
from fastapi.responses import StreamingResponse, JSONResponse
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
    """Health check endpoint."""
    return {"status": "ok", "service": "GeoDataCheck API", "version": "1.0.0"}


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
                "required_columns": w.get("columns", {}).get("required", []),
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
        df = pd.read_excel(io.BytesIO(contents))

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

    # Run validation
    result = engine.validate(df, validation_config, rule_ids)

    # Add dimensional analysis
    result_dict = result.to_dict()

    # Add dimension breakdowns if columns specified
    for dim_name, dim_col in config.dimension_columns.items():
        if dim_col and dim_col in df.columns:
            result_dict[f'by_{dim_name}'] = result.get_errors_by_dimension(df, dim_col)

    # Store result in session
    session['result'] = result
    session['config'] = validation_config

    return result_dict


@app.get("/api/workflows/{workflow_id}/sessions/{session_id}/report")
async def workflow_download_report(workflow_id: str, session_id: str):
    """
    Download validation report for a workflow session.
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

    # Create Excel report
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Summary sheet
        summary_data = {
            'Metrik': ['Workflow', 'Total Zeilen', 'Fehler', 'Warnungen', 'Bestanden', 'Erfolgsquote'],
            'Wert': [
                workflow['name'],
                result.total_rows,
                result.error_count,
                result.warning_count,
                result.passed_rows,
                f"{round(result.passed_rows / result.total_rows * 100, 1)}%" if result.total_rows > 0 else "N/A"
            ]
        }
        pd.DataFrame(summary_data).to_excel(writer, sheet_name='Zusammenfassung', index=False)

        # Errors sheet
        if result.errors:
            error_data = [e.to_dict() for e in result.errors]
            errors_df = pd.DataFrame(error_data)
            errors_df = errors_df.rename(columns={
                'row_number': 'Zeile',
                'column': 'Spalte',
                'rule_id': 'Regel-ID',
                'rule_name': 'Regel',
                'severity': 'Schweregrad',
                'message': 'Meldung',
                'value': 'Wert',
                'suggestion': 'Vorschlag',
            })
            errors_df = errors_df[['Zeile', 'Spalte', 'Regel', 'Schweregrad', 'Meldung', 'Wert', 'Vorschlag']]
            errors_df.to_excel(writer, sheet_name='Fehler', index=False)

    output.seek(0)

    filename = session.get('filename', 'data').replace('.xlsx', '').replace('.xls', '')
    workflow_name = workflow['id'].replace('-', '_')

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}_{workflow_name}_report.xlsx"
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
