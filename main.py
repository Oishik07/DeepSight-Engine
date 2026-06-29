from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from core.config import settings
from database.session import engine, Base
from api.endpoints import router as api_router
from contextlib import asynccontextmanager

from sqlalchemy import text

import os
import asyncio
import logging
import urllib.request

logger = logging.getLogger("uvicorn.error")

async def run_keep_alive():
    """
    Background task to ping the Render URL every 3 minutes.
    This keeps the Render instance active 24/7.
    """
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        logger.info("RENDER_EXTERNAL_URL is not set. Skipping keep-alive heartbeats.")
        return

    ping_url = f"{url.rstrip('/')}/api/health"
    logger.info(f"Starting keep-alive heartbeats for Render at {ping_url}")
    
    # Wait 10 seconds after startup before starting to ping
    await asyncio.sleep(10)
    
    while True:
        try:
            def ping():
                req = urllib.request.Request(
                    ping_url,
                    headers={"User-Agent": "DeepSight-Engine-Heartbeat"}
                )
                with urllib.request.urlopen(req, timeout=10) as response:
                    return response.status
            
            status = await asyncio.to_thread(ping)
            logger.info(f"Keep-alive heartbeat status: {status}")
        except Exception as e:
            logger.error(f"Keep-alive heartbeat failed: {e}")
            
        # Sleep for 3 minutes (180 seconds)
        await asyncio.sleep(180)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Attempt to run automated migration in a separate transaction
    # so if it fails, it doesn't roll back the table creation!
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE research_jobs ADD COLUMN user_email VARCHAR"))
    except Exception:
        # Column already exists
        pass

    # Start the keep-alive background task
    keep_alive_task = asyncio.create_task(run_keep_alive())
    
    yield
    # Shutdown
    keep_alive_task.cancel()
    try:
        await keep_alive_task
    except asyncio.CancelledError:
        pass
    await engine.dispose()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.include_router(api_router, prefix="/api")

# Serve the frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/")
async def serve_frontend():
    return FileResponse("frontend/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
