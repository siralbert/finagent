from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
import logging
from typing import Optional

logger = logging.getLogger("file_download")

router = APIRouter()

# Directory where generated files will be stored
DOWNLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "downloads")

# Ensure downloads directory exists
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

@router.get("/download/{filename}")
async def download_file(filename: str):
    """
    Download a generated file (Word document, PDF, etc.)
    
    Args:
        filename: Name of the file to download
    """
    try:
        # Security: Only allow certain file extensions
        allowed_extensions = ['.docx', '.pdf', '.txt']
        file_ext = None
        for ext in allowed_extensions:
            if filename.lower().endswith(ext):
                file_ext = ext
                break
        
        if not file_ext:
            raise HTTPException(status_code=400, detail="File type not allowed")
        
        # Security: Prevent path traversal attacks
        if '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        file_path = os.path.join(DOWNLOADS_DIR, filename)
        
        # Check if file exists
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="File not found")
        
        # Determine media type based on extension
        media_type_map = {
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.pdf': 'application/pdf',
            '.txt': 'text/plain'
        }
        
        media_type = media_type_map.get(file_ext, 'application/octet-stream')
        
        logger.info(f"Serving file download: {filename}")
        
        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=filename
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving file download: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/list")
async def list_available_files():
    """
    List all available files for download
    """
    try:
        files = []
        allowed_extensions = ['.docx', '.pdf', '.txt']
        
        if os.path.exists(DOWNLOADS_DIR):
            for filename in os.listdir(DOWNLOADS_DIR):
                if any(filename.lower().endswith(ext) for ext in allowed_extensions):
                    file_path = os.path.join(DOWNLOADS_DIR, filename)
                    file_stats = os.stat(file_path)
                    files.append({
                        'filename': filename,
                        'size': file_stats.st_size,
                        'created': file_stats.st_ctime,
                        'modified': file_stats.st_mtime
                    })
        
        # Sort by modification time (newest first)
        files.sort(key=lambda x: x['modified'], reverse=True)
        
        return {'files': files}
        
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

def get_downloads_directory():
    """Get the downloads directory path"""
    return DOWNLOADS_DIR