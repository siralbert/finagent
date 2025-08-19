from typing import List, Dict, Any, Optional
from mcp.server.fastmcp import FastMCP
import logging
import asyncio
import time
import argparse
import os
import json
import subprocess
import platform
import shutil

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("pdf-generator-server")

# Initialize FastMCP server
mcp = FastMCP("pdf-generator", log_level="INFO")

# Rate limiting implementation
RATE_LIMIT = {
    "per_minute": 10,
    "per_day": 300
}

request_count = {
    "minute": 0,
    "day": 0,
    "last_minute_reset": time.time(),
    "last_day_reset": time.time()
}

def check_rate_limit():
    now = time.time()
    
    if now - request_count["last_minute_reset"] > 60:
        request_count["minute"] = 0
        request_count["last_minute_reset"] = now
    
    if now - request_count["last_day_reset"] > 86400:
        request_count["day"] = 0
        request_count["last_day_reset"] = now
    
    if (request_count["minute"] >= RATE_LIMIT["per_minute"] or 
            request_count["day"] >= RATE_LIMIT["per_day"]):
        raise Exception('Rate limit exceeded. Please try again later.')
    
    request_count["minute"] += 1
    request_count["day"] += 1

class APIError(Exception):
    pass

# Utility functions
def check_file_writeable(filepath: str):
    """
    Check if a file can be written to.
    
    Args:
        filepath: Path to the file
        
    Returns:
        Tuple of (is_writeable, error_message)
    """
    # If file doesn't exist, check if directory is writeable
    if not os.path.exists(filepath):
        directory = os.path.dirname(filepath)
        # If no directory is specified (empty string), use current directory
        if directory == '':
            directory = '.'
        if not os.path.exists(directory):
            return False, f"Directory {directory} does not exist"
        if not os.access(directory, os.W_OK):
            return False, f"Directory {directory} is not writeable"
        return True, ""
    
    # If file exists, check if it's writeable
    if not os.access(filepath, os.W_OK):
        return False, f"File {filepath} is not writeable (permission denied)"
    
    # Try to open the file for writing to see if it's locked
    try:
        with open(filepath, 'a'):
            pass
        return True, ""
    except IOError as e:
        return False, f"File {filepath} is not writeable: {str(e)}"
    except Exception as e:
        return False, f"Unknown error checking file permissions: {str(e)}"

def ensure_docx_extension(filename: str) -> str:
    """
    Ensure filename has .docx extension.
    
    Args:
        filename: The filename to check
        
    Returns:
        Filename with .docx extension
    """
    if not filename.endswith('.docx'):
        return filename + '.docx'
    return filename

async def convert_docx_to_pdf(filename: str, output_filename: Optional[str] = None):
    """
    Convert a Word document to PDF format.
    
    Args:
        filename: Path to the Word document
        output_filename: Optional path for the output PDF
        
    Returns:
        Status message with result of conversion
    """
    check_rate_limit()
    
    try:
        filename = ensure_docx_extension(filename)
        
        if not os.path.exists(filename):
            return f"Document {filename} does not exist"
        
        # Generate output filename if not provided
        if not output_filename:
            base_name, _ = os.path.splitext(filename)
            output_filename = f"{base_name}.pdf"
        elif not output_filename.lower().endswith('.pdf'):
            output_filename = f"{output_filename}.pdf"
        
        # Convert to absolute path if not already
        if not os.path.isabs(output_filename):
            output_filename = os.path.abspath(output_filename)
        
        # Ensure the output directory exists
        output_dir = os.path.dirname(output_filename)
        if not output_dir:
            output_dir = os.path.abspath('.')
        
        # Create the directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Check if output file can be written
        is_writeable, error_message = check_file_writeable(output_filename)
        if not is_writeable:
            return f"Cannot create PDF: {error_message} (Path: {output_filename}, Dir: {output_dir})"
        
        # Determine platform for appropriate conversion method
        system = platform.system()
        
        if system == "Windows":
            # On Windows, try docx2pdf which uses Microsoft Word
            try:
                from docx2pdf import convert
                convert(filename, output_filename)
                return f"Document successfully converted to PDF: {output_filename}"
            except (ImportError, Exception) as e:
                return f"Failed to convert document to PDF: {str(e)}\nNote: docx2pdf requires Microsoft Word to be installed."
                
        elif system in ["Linux", "Darwin"]:  # Linux or macOS
            # Try using LibreOffice if available (common on Linux/macOS)
            try:
                # Choose the appropriate command based on OS
                if system == "Darwin":  # macOS
                    lo_commands = ["soffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice"]
                else:  # Linux
                    lo_commands = ["libreoffice", "soffice"]
                
                # Try each possible command
                conversion_successful = False
                errors = []
                
                for cmd_name in lo_commands:
                    try:
                        # Construct LibreOffice conversion command
                        output_dir = os.path.dirname(output_filename)
                        # If output_dir is empty, use current directory
                        if not output_dir:
                            output_dir = '.'
                        # Ensure the directory exists
                        os.makedirs(output_dir, exist_ok=True)
                        
                        cmd = [
                            cmd_name, 
                            '--headless', 
                            '--convert-to', 
                            'pdf', 
                            '--outdir', 
                            output_dir, 
                            filename
                        ]
                        
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                        
                        if result.returncode == 0:
                            # LibreOffice creates the PDF with the same basename
                            base_name = os.path.basename(filename)
                            pdf_base_name = os.path.splitext(base_name)[0] + ".pdf"
                            created_pdf = os.path.join(os.path.dirname(output_filename) or '.', pdf_base_name)
                            
                            # If the created PDF is not at the desired location, move it
                            if created_pdf != output_filename and os.path.exists(created_pdf):
                                shutil.move(created_pdf, output_filename)
                            
                            conversion_successful = True
                            break  # Exit the loop if successful
                        else:
                            errors.append(f"{cmd_name} error: {result.stderr}")
                    except (subprocess.SubprocessError, FileNotFoundError) as e:
                        errors.append(f"{cmd_name} error: {str(e)}")
                
                if conversion_successful:
                    return f"Document successfully converted to PDF: {output_filename}"
                else:
                    # If all LibreOffice attempts failed, try docx2pdf as fallback
                    try:
                        from docx2pdf import convert
                        convert(filename, output_filename)
                        return f"Document successfully converted to PDF: {output_filename}"
                    except (ImportError, Exception) as e:
                        error_msg = "Failed to convert document to PDF using LibreOffice or docx2pdf.\n"
                        error_msg += "LibreOffice errors: " + "; ".join(errors) + "\n"
                        error_msg += f"docx2pdf error: {str(e)}\n"
                        error_msg += "To convert documents to PDF, please install either:\n"
                        error_msg += "1. LibreOffice (recommended for Linux/macOS)\n"
                        error_msg += "2. Microsoft Word (required for docx2pdf on Windows/macOS)"
                        return error_msg
                    
            except Exception as e:
                return f"Failed to convert document to PDF: {str(e)}"
        else:
            return f"PDF conversion not supported on {system} platform"
            
    except Exception as e:
        logger.error(f"Error in PDF conversion: {str(e)}")
        raise APIError(f"PDF conversion failed: {str(e)}")

# MCP tool definitions
@mcp.tool()
async def convert_to_pdf(filename: str, output_filename: Optional[str] = None) -> str:
    """
    Convert a Word document (DOCX) to PDF format.
    
    Args:
        filename: Path to the Word document (.docx file)
        output_filename: Optional path for the output PDF. If not provided, 
                         will use the same name with .pdf extension
    """
    try:
        result = await convert_docx_to_pdf(filename, output_filename)
        return result
    except Exception as e:
        return f"Error converting document to PDF: {str(e)}"

def main():
    parser = argparse.ArgumentParser(description='Run PDF Generator MCP server')
    parser.add_argument('--port', type=int, default=8089, help='Port to run the server on')
    
    args = parser.parse_args()
    
    mcp.settings.port = args.port
    logger.info(f"Starting PDF Generator server with Streamable HTTP transport on port {args.port}")
    mcp.run(transport='streamable-http')

if __name__ == "__main__":
    main()