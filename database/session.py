from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from core.config import settings

# Wait, if we use postgres, let's setup the engine. 
# We'll default to a local postgres DB if not provided.
DB_URL = settings.DATABASE_URL
if DB_URL.startswith("sqlite"):
    # Fix for async sqlite
    engine = create_async_engine(DB_URL, echo=False)
else:
    engine = create_async_engine(DB_URL, echo=False)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
