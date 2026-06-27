from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from core.config import settings
from database.session import engine, Base
from api.endpoints import router as api_router
from contextlib import asynccontextmanager

from sqlalchemy import text

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Attempt to run automated migration to add user_email column for SQLite
        try:
            await conn.execute(text("ALTER TABLE research_jobs ADD COLUMN user_email VARCHAR"))
        except Exception:
            # Column already exists
            pass
    yield
    # Shutdown
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
