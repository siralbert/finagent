from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse
import openai
import os
import tempfile
import logging
from typing import Optional

logger = logging.getLogger("transcription_api")
router = APIRouter()

def get_openai_client():
    """Initialize OpenAI client for transcription"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OpenAI API key not configured. Please set OPENAI_API_KEY environment variable.")
    
    return openai.OpenAI(api_key=api_key)

@router.post("/")
async def transcribe_audio(
    file: UploadFile = File(...),
    model: str = Form(default="whisper-1"),
    language: Optional[str] = Form(default="en")
):
    """
    Transcribe audio file using OpenAI Whisper API
    
    Args:
        file: Audio file (webm, mp3, wav, etc.)
        model: Whisper model to use (default: whisper-1)
        language: Language code (default: en)
    
    Returns:
        JSON response with transcribed text
    """
    try:
        logger.info(f"Transcription request received - file: {file.filename}, size: {file.size if hasattr(file, 'size') else 'unknown'}, model: {model}")
        
        # Validate file
        if not file:
            raise HTTPException(status_code=400, detail="No audio file provided")
        
        # Check file size (OpenAI has a 25MB limit)
        file_content = await file.read()
        file_size_mb = len(file_content) / (1024 * 1024)
        
        if len(file_content) > 25 * 1024 * 1024:  # 25MB
            raise HTTPException(status_code=400, detail=f"File too large ({file_size_mb:.1f}MB). Maximum size is 25MB.")
        
        if len(file_content) < 1024:  # Less than 1KB
            raise HTTPException(status_code=400, detail="Audio file too short or empty")
        
        logger.info(f"Processing audio file: {file_size_mb:.2f}MB")
        
        # Get OpenAI client
        client = get_openai_client()
        
        # Create temporary file for OpenAI API
        file_extension = get_file_extension(file.filename)
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as temp_file:
            temp_file.write(file_content)
            temp_file_path = temp_file.name
        
        try:
            # Call OpenAI Whisper API
            with open(temp_file_path, 'rb') as audio_file:
                transcription_params = {
                    "model": model,
                    "file": audio_file,
                    "response_format": "json"
                }
                
                # Add language parameter if provided and not auto-detect
                if language and language != "auto":
                    transcription_params["language"] = language
                
                logger.info(f"Sending request to OpenAI Whisper API with model: {model}")
                response = client.audio.transcriptions.create(**transcription_params)
            
            # Extract transcribed text
            transcribed_text = response.text.strip()
            
            if not transcribed_text:
                logger.warning("Empty transcription result - no speech detected")
                return JSONResponse(
                    content={"text": "", "message": "No speech detected in audio"},
                    status_code=200
                )
            
            logger.info(f"Transcription successful - text length: {len(transcribed_text)} characters")
            logger.debug(f"Transcribed text preview: {transcribed_text[:100]}{'...' if len(transcribed_text) > 100 else ''}")
            
            return JSONResponse(
                content={
                    "text": transcribed_text,
                    "language": getattr(response, 'language', language),
                    "duration": getattr(response, 'duration', None),
                    "model": model
                },
                status_code=200
            )
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_file_path)
                logger.debug(f"Cleaned up temporary file: {temp_file_path}")
            except OSError as e:
                logger.warning(f"Failed to cleanup temporary file {temp_file_path}: {e}")
        
    except openai.BadRequestError as e:
        error_msg = f"OpenAI API request error: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=400, detail=f"Audio processing failed: {str(e)}")
    
    except openai.AuthenticationError:
        error_msg = "OpenAI authentication failed - invalid API key"
        logger.error(error_msg)
        raise HTTPException(status_code=401, detail="Invalid OpenAI API key. Please check your configuration.")
    
    except openai.RateLimitError:
        error_msg = "OpenAI rate limit exceeded"
        logger.error(error_msg)
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")
    
    except openai.APIConnectionError:
        error_msg = "Failed to connect to OpenAI API"
        logger.error(error_msg)
        raise HTTPException(status_code=503, detail="Unable to connect to OpenAI API. Please try again.")
    
    except Exception as e:
        error_msg = f"Unexpected transcription error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcription service error: {str(e)}")

def get_file_extension(filename: str) -> str:
    """Get appropriate file extension for audio file"""
    if not filename:
        return ".webm"
    
    filename_lower = filename.lower()
    
    # Map common audio formats
    if filename_lower.endswith(('.webm', '.opus')):
        return '.webm'
    elif filename_lower.endswith(('.mp3', '.mpeg')):
        return '.mp3'
    elif filename_lower.endswith('.wav'):
        return '.wav'
    elif filename_lower.endswith('.m4a'):
        return '.m4a'
    elif filename_lower.endswith('.ogg'):
        return '.ogg'
    elif filename_lower.endswith('.flac'):
        return '.flac'
    else:
        return '.webm'  # Default fallback for web recordings

@router.get("/health")
async def transcription_health_check():
    """Health check endpoint for transcription service"""
    try:
        # Check if OpenAI API key is configured
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return JSONResponse(
                content={
                    "status": "unhealthy", 
                    "error": "OpenAI API key not configured",
                    "service": "transcription"
                },
                status_code=503
            )
        
        # Try to create client (this validates the key format)
        try:
            client = openai.OpenAI(api_key=api_key)
            # We don't make an actual API call here to avoid charges/rate limits
        except Exception as e:
            return JSONResponse(
                content={
                    "status": "unhealthy", 
                    "error": f"OpenAI client initialization failed: {str(e)}",
                    "service": "transcription"
                },
                status_code=503
            )
        
        return JSONResponse(
            content={
                "status": "healthy", 
                "service": "transcription",
                "provider": "OpenAI Whisper",
                "supported_formats": [".webm", ".mp3", ".wav", ".m4a", ".ogg", ".flac"]
            },
            status_code=200
        )
    
    except Exception as e:
        return JSONResponse(
            content={
                "status": "unhealthy", 
                "error": str(e),
                "service": "transcription"
            },
            status_code=503
        )

@router.get("/info")
async def transcription_info():
    """Get information about the transcription service"""
    return {
        "service": "Audio Transcription",
        "provider": "OpenAI Whisper",
        "model": "whisper-1",
        "supported_formats": [
            "webm", "mp3", "wav", "m4a", "ogg", "flac"
        ],
        "max_file_size": "25MB",
        "supported_languages": [
            "en", "es", "fr", "de", "it", "pt", "ru", "ja", "ko", "zh", 
            "ar", "hi", "tr", "pl", "nl", "sv", "da", "no", "fi"
        ],
        "endpoints": {
            "transcribe": "/api/transcribe",
            "health": "/api/transcribe/health",
            "info": "/api/transcribe/info"
        }
    }
