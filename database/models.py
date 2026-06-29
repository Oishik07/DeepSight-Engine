import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
import sqlalchemy.types as types
from database.session import Base
import json

# Fallback for SQLite which doesn't support JSONB out of the box
class JSONType(types.TypeDecorator):
    impl = types.String

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(JSONB())
        else:
            return dialect.type_descriptor(String())

    def process_bind_param(self, value, dialect):
        if value is not None:
            if dialect.name != 'postgresql':
                return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            if dialect.name != 'postgresql':
                return json.loads(value)
        return value

class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    goal = Column(String, nullable=False)
    status = Column(String, default="PENDING")  # PENDING, IN_PROGRESS, COMPLETED, FAILED
    final_report = Column(JSONType, nullable=True)
    user_email = Column(String, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class LLMUsageDaily(Base):
    __tablename__ = "llm_usage_daily"
    __table_args__ = (
        UniqueConstraint("usage_date", "provider", "model", "api_key_hash", name="uq_llm_usage_daily_key"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    usage_date = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    api_key_hash = Column(String, nullable=False)
    api_key_label = Column(String, nullable=False)
    tokens_used = Column(Integer, default=0)
    request_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    rate_limit_count = Column(Integer, default=0)
    last_status = Column(String, default="healthy")
    last_error = Column(String, nullable=True)
    blocked_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
