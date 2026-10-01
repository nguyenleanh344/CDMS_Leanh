from sqlalchemy import (
    Column,
    String,
    Integer,
    BigInteger,
    DateTime,
    Text,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    Index,
    CheckConstraint,
    ForeignKeyConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB, CHAR
from sqlalchemy.sql import text, func
from app.core.db import Base

# ==========================================
# 1. Schema: emulator 
# ==========================================
class EmulatorProduct(Base):
    __tablename__ = "products"
    __table_args__ = (    
        CheckConstraint("source_version > 0", name='chk_source_version_positive'),
        CheckConstraint("product_id > 0", name='chk_emulator_product_id_positive'),
        {"schema": "emulator"},
    )
    
    product_id = Column(Integer, primary_key=True)
    sku = Column(String(100), nullable=True)
    product_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False)
    source_version = Column(BigInteger, nullable=False)


# ==========================================
# 2. Schema: cdms
# ==========================================
class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint("job_type IN ('EXCEL', 'SYNC')", name="chk_job_type_enum"),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'RETRYING', 'SUCCESS', 'PARTIAL_SUCCESS', 'FAILED')",
            name='chk_job_status_enum'
        ),
        CheckConstraint("attempt_count >= 0", name="chk_job_attempt_count_non_negative"),
        CheckConstraint(
            """
            (job_type = 'EXCEL' AND file_name IS NOT NULL) OR
            (job_type = 'SYNC' AND file_name IS NULL)
            """,
            name='chk_job_type_file_name_consistency'
        ),
        Index(
            'idx_unique_active_sync_job',
            'job_type',
            unique=True,
            postgresql_where=text("job_type = 'SYNC' AND status IN ('PENDING', 'PROCESSING', 'RETRYING')")
        ),
        Index(
            'idx_processing_jobs_worker_poll',
            'status',
            'next_attempt_at',
            'created_at'
        ),
        {"schema": "cdms"}
    )
    
    job_id = Column(UUID(as_uuid=True), primary_key=True)
    job_type = Column(String(8), nullable=False)
    status = Column(String(24), nullable=False)
    parameters = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    file_name = Column(String(255), nullable=True)
    input_complete = Column(Boolean, nullable=False, server_default=text("false"), default=False)
    attempt_count = Column(Integer, nullable=False, server_default=text("0"), default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class InboundEvent(Base):
    __tablename__ = 'inbound_events'
    __table_args__ = (
        ForeignKeyConstraint(['job_id'], ['cdms.processing_jobs.job_id'], name='fk_inbound_events_job'),
        CheckConstraint("channel IN ('WEBHOOK', 'EXCEL', 'POLLING')", name='chk_event_channel_enum'),
        CheckConstraint(
            "status IN ('RECEIVED', 'PROCESSING', 'SUCCESS', 'FAILED', 'RETRYING', 'VALIDATION_ERROR', 'DUPLICATE', 'NO_CHANGE', 'STALE', 'CONFLICT')",
            name='chk_event_status_enum'
        ),
        CheckConstraint("source_version IS NULL OR source_version > 0", name='chk_event_source_version_positive'),
        CheckConstraint("attempt_count >= 0", name='chk_event_attempt_count_non_negative'),
        CheckConstraint("item_index > 0", name='chk_item_index_positive'),
        CheckConstraint(
            """
            (channel = 'WEBHOOK' AND external_event_id IS NOT NULL AND job_id IS NULL AND item_index IS NULL) OR
            (channel IN ('EXCEL', 'POLLING') AND external_event_id IS NULL AND job_id IS NOT NULL AND item_index IS NOT NULL)
            """,
            name='chk_event_channel_ownership'
        ),
        UniqueConstraint('job_id', 'item_index', name='uq_job_item_index'),
        Index(
            'idx_partial_webhook_event',
            'external_event_id',
            unique=True,
            postgresql_where=text("channel = 'WEBHOOK'")
        ),
        Index('idx_events_status_retry_received', 'status', 'next_attempt_at', 'received_at'),
        {"schema": "cdms"}
    )

    event_id = Column(UUID(as_uuid=True), primary_key=True)
    job_id = Column(UUID(as_uuid=True), nullable=True)
    item_index = Column(Integer, nullable=True)
    channel = Column(String(16), nullable=False)
    external_event_id = Column(String(128), nullable=True)
    product_id = Column(Integer, nullable=True)
    source_version = Column(BigInteger, nullable=True)
    raw_payload = Column(JSONB, nullable=False)
    payload = Column(JSONB, nullable=True)
    business_hash = Column(CHAR(64), nullable=True)
    request_fingerprint = Column(CHAR(64), nullable=True)
    status = Column(String(24), nullable=False)
    attempt_count = Column(Integer, nullable=False, server_default=text("0"), default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=True)
    error_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)


class ProductChanges(Base):
    __tablename__ = 'product_changes'
    __table_args__ = (
        ForeignKeyConstraint(['event_id'], ['cdms.inbound_events.event_id'], name='fk_product_changes_event'),
        ForeignKeyConstraint(
            ['product_id'],
            ['cdms.product_current.product_id'],
            name='fk_product_changes_current',
            deferrable=True,
            initially='DEFERRED'
        ),
        UniqueConstraint('product_id', 'source_version', name='uq_product_version_changes'),
        UniqueConstraint('product_id', 'change_id', name='uq_product_change_composite_target'),
        UniqueConstraint('event_id', name='uq_product_changes_event_id'), # Chỉ dùng UniqueConstraint, tránh trùng unique=True ở cột
        CheckConstraint("source_version > 0", name='chk_changes_source_version_positive'),
        CheckConstraint("product_id > 0", name='chk_changes_product_id_positive'),
        Index('idx_changes_stored_change', 'stored_at', 'change_id'),
        {"schema": "cdms"}
    )

    change_id = Column(UUID(as_uuid=True), primary_key=True)
    product_id = Column(Integer, nullable=False)
    source_version = Column(BigInteger, nullable=False)
    event_id = Column(UUID(as_uuid=True), nullable=False)
    payload = Column(JSONB, nullable=False)
    business_hash = Column(CHAR(64), nullable=False)
    stored_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProductCurrent(Base):
    __tablename__ = 'product_current'
    __table_args__ = (
        ForeignKeyConstraint(
            ['product_id', 'last_change_id'],
            ['cdms.product_changes.product_id', 'cdms.product_changes.change_id'],
            name='fk_product_current_last_change',
            deferrable=True,
            initially='DEFERRED'
        ),
        CheckConstraint("source_version > 0", name='chk_current_source_version_positive'),
        CheckConstraint("product_id > 0", name='chk_current_product_id_positive'),
        {"schema": "cdms"}
    )

    product_id = Column(Integer, primary_key=True)
    sku = Column(String(100), nullable=True)
    name = Column(String(255), nullable=True)
    is_active = Column(Boolean, nullable=False)
    source_version = Column(BigInteger, nullable=False)
    business_hash = Column(CHAR(64), nullable=False)
    last_change_id = Column(UUID(as_uuid=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    observed_at = Column(DateTime(timezone=True), nullable=False)
    