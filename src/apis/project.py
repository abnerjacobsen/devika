from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import os
import re
from pathlib import Path

from src.logger import Logger, route_logger
from src.config import Config
from src.project import ProjectManager
from ..state import AgentState

# Create router instead of blueprint
router = APIRouter()

logger = Logger()
manager = ProjectManager()

# Pydantic models for request validation
class ProjectCreate(BaseModel):
    project_name: str

class ProjectDelete(BaseModel):
    project_name: str

# Helper function to replace secure_filename
def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to ensure it's safe for filesystem operations.
    Similar to werkzeug's secure_filename but simpler.
    """
    # Remove potentially dangerous characters
    filename = re.sub(r'[^\w\s.-]', '', filename)
    # Replace spaces with underscores
    filename = filename.replace(' ', '_')
    # Remove leading/trailing dots or spaces
    filename = filename.strip('. ')
    # Ensure we have a valid filename
    if not filename:
        filename = "unnamed_project"
    return filename

# Project APIs

@router.get("/api/get-project-files")
@route_logger(logger)
def project_files(project_name: str = Query(...)):
    safe_name = sanitize_filename(project_name)
    files = manager.get_project_files(safe_name)  
    return {"files": files}

@router.post("/api/create-project")
@route_logger(logger)
def create_project(project_data: ProjectCreate):
    project_name = sanitize_filename(project_data.project_name)
    manager.create_project(project_name)
    return {"message": "Project created"}

@router.post("/api/delete-project")
@route_logger(logger)
def delete_project(project_data: ProjectDelete):
    project_name = sanitize_filename(project_data.project_name)
    manager.delete_project(project_name)
    AgentState().delete_state(project_name)
    return {"message": "Project deleted"}

@router.get("/api/download-project")
@route_logger(logger)
def download_project(project_name: str = Query(...)):
    safe_name = sanitize_filename(project_name)
    manager.project_to_zip(safe_name)
    project_path = manager.get_zip_path(safe_name)
    return FileResponse(
        path=project_path,
        filename=f"{safe_name}.zip",
        media_type="application/zip"
    )

@router.get("/api/download-project-pdf")
@route_logger(logger)
def download_project_pdf(project_name: str = Query(...)):
    safe_name = sanitize_filename(project_name)
    pdf_dir = Config().get_pdfs_dir()
    pdf_path = os.path.join(pdf_dir, f"{safe_name}.pdf")
    
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF file not found")
        
    return FileResponse(
        path=pdf_path,
        filename=f"{safe_name}.pdf",
        media_type="application/pdf"
    )
