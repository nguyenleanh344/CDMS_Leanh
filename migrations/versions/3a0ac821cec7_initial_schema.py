"""initial schema

Revision ID: 3a0ac821cec7
Revises: 
Create Date: 2026-09-30 21:18:19.306586

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '3a0ac821cec7'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("CREATE SCHEMA IF NOT EXISTS cdms;")
    op.execute("CREATE SCHEMA IF NOT EXISTS emulator;")

    
    op.create_table('processing_jobs',
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('job_type', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('parameters', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=True),
        sa.Column('input_complete', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('attempt_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(job_type = 'EXCEL' AND file_name IS NOT NULL) OR (job_type = 'SYNC' AND file_name IS NULL)",
            name='chk_job_type_file_name_consistency'
        ),
        sa.CheckConstraint("job_type IN ('EXCEL', 'SYNC')", name='chk_job_type_enum'),
        sa.CheckConstraint("status IN ('PENDING', 'PROCESSING', 'RETRYING', 'SUCCESS', 'PARTIAL_SUCCESS', 'FAILED')", name='chk_job_status_enum'),
        sa.CheckConstraint('attempt_count >= 0', name='chk_job_attempt_count_non_negative'),
        sa.PrimaryKeyConstraint('job_id'),
        schema='cdms'
    )
    op.create_index('idx_processing_jobs_worker_poll', 'processing_jobs', ['status', 'next_attempt_at', 'created_at'], unique=False, schema='cdms')
    op.create_index('idx_unique_active_sync_job', 'processing_jobs', ['job_type'], unique=True, schema='cdms', postgresql_where=sa.text("job_type = 'SYNC' AND status IN ('PENDING', 'PROCESSING', 'RETRYING')"))

    op.create_table('inbound_events',
        sa.Column('event_id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=True),
        sa.Column('item_index', sa.Integer(), nullable=True),
        sa.Column('channel', sa.String(length=16), nullable=False),
        sa.Column('external_event_id', sa.String(length=128), nullable=True),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('source_version', sa.BigInteger(), nullable=True),
        sa.Column('raw_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('business_hash', sa.CHAR(length=64), nullable=True),
        sa.Column('request_fingerprint', sa.CHAR(length=64), nullable=True),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('attempt_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_code', sa.String(length=64), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(channel = 'WEBHOOK' AND external_event_id IS NOT NULL AND job_id IS NULL AND item_index IS NULL) OR "
            "(channel IN ('EXCEL', 'POLLING') AND external_event_id IS NULL AND job_id IS NOT NULL AND item_index IS NOT NULL)",
            name='chk_event_channel_ownership'
        ),
        sa.CheckConstraint("channel IN ('WEBHOOK', 'EXCEL', 'POLLING')", name='chk_event_channel_enum'),
        sa.CheckConstraint("status IN ('RECEIVED', 'PROCESSING', 'SUCCESS', 'FAILED', 'RETRYING', 'VALIDATION_ERROR', 'DUPLICATE', 'NO_CHANGE', 'STALE', 'CONFLICT')", name='chk_event_status_enum'),
        sa.CheckConstraint('attempt_count >= 0', name='chk_event_attempt_count_non_negative'),
        sa.CheckConstraint('item_index > 0', name='chk_item_index_positive'),
        sa.CheckConstraint('source_version IS NULL OR source_version > 0', name='chk_event_source_version_positive'),
        sa.PrimaryKeyConstraint('event_id'),
        sa.UniqueConstraint('job_id', 'item_index', name='uq_job_item_index'),
        schema='cdms'
    )
    op.create_index('idx_events_status_retry_received', 'inbound_events', ['status', 'next_attempt_at', 'received_at'], unique=False, schema='cdms')
    op.create_index('idx_partial_webhook_event', 'inbound_events', ['external_event_id'], unique=True, schema='cdms', postgresql_where=sa.text("channel = 'WEBHOOK'"))

    op.create_table('product_current',
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('source_version', sa.BigInteger(), nullable=False),
        sa.Column('business_hash', sa.CHAR(length=64), nullable=False),
        sa.Column('last_change_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('product_id > 0', name='chk_current_product_id_positive'),
        sa.CheckConstraint('source_version > 0', name='chk_current_source_version_positive'),
        sa.PrimaryKeyConstraint('product_id'),
        schema='cdms'
    )

    op.create_table('product_changes',
        sa.Column('change_id', sa.UUID(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('source_version', sa.BigInteger(), nullable=False),
        sa.Column('event_id', sa.UUID(), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('business_hash', sa.CHAR(length=64), nullable=False),
        sa.Column('stored_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('product_id > 0', name='chk_changes_product_id_positive'),
        sa.CheckConstraint('source_version > 0', name='chk_changes_source_version_positive'),
        sa.PrimaryKeyConstraint('change_id'),
        sa.UniqueConstraint('event_id', name='uq_product_changes_event_id'),
        sa.UniqueConstraint('product_id', 'change_id', name='uq_product_change_composite_target'),
        sa.UniqueConstraint('product_id', 'source_version', name='uq_product_version_changes'),
        schema='cdms'
    )
    op.create_index('idx_changes_stored_change', 'product_changes', ['stored_at', 'change_id'], unique=False, schema='cdms')

    op.create_table('products',
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=True),
        sa.Column('product_name', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('source_version', sa.BigInteger(), nullable=False),
        sa.CheckConstraint('product_id > 0', name='chk_emulator_product_id_positive'),
        sa.CheckConstraint('source_version > 0', name='chk_source_version_positive'),
        sa.PrimaryKeyConstraint('product_id'),
        schema='emulator'
    )

    
    op.create_foreign_key(
        'fk_inbound_events_job',
        'inbound_events', 'processing_jobs',
        ['job_id'], ['job_id'],
        source_schema='cdms', referent_schema='cdms'
    )

    op.create_foreign_key(
        'fk_product_changes_event',
        'product_changes', 'inbound_events',
        ['event_id'], ['event_id'],
        source_schema='cdms', referent_schema='cdms'
    )

    op.create_foreign_key(
        'fk_product_changes_current',
        'product_changes', 'product_current',
        ['product_id'], ['product_id'],
        source_schema='cdms', referent_schema='cdms',
        deferrable=True, initially='DEFERRED'
    )

    op.create_foreign_key(
        'fk_product_current_last_change',
        'product_current', 'product_changes',
        ['product_id', 'last_change_id'], ['product_id', 'change_id'],
        source_schema='cdms', referent_schema='cdms',
        deferrable=True, initially='DEFERRED'
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_product_current_last_change', 'product_current', type_='foreignkey', schema='cdms')
    op.drop_constraint('fk_product_changes_current', 'product_changes', type_='foreignkey', schema='cdms')
    op.drop_constraint('fk_product_changes_event', 'product_changes', type_='foreignkey', schema='cdms')
    op.drop_constraint('fk_inbound_events_job', 'inbound_events', type_='foreignkey', schema='cdms')

    op.drop_index('idx_partial_webhook_event', table_name='inbound_events', schema='cdms', postgresql_where=sa.text("channel = 'WEBHOOK'"))
    op.drop_index('idx_events_status_retry_received', table_name='inbound_events', schema='cdms')
    op.drop_table('inbound_events', schema='cdms')
    
    op.drop_table('products', schema='emulator')
    
    op.drop_index('idx_changes_stored_change', table_name='product_changes', schema='cdms')
    op.drop_table('product_changes', schema='cdms')
    
    op.drop_table('product_current', schema='cdms')
    
    op.drop_index('idx_unique_active_sync_job', table_name='processing_jobs', schema='cdms', postgresql_where=sa.text("job_type = 'SYNC' AND status IN ('PENDING', 'PROCESSING', 'RETRYING')"))
    op.drop_index('idx_processing_jobs_worker_poll', table_name='processing_jobs', schema='cdms')
    op.drop_table('processing_jobs', schema='cdms')

    op.execute("DROP SCHEMA IF EXISTS cdms CASCADE;")
    op.execute("DROP SCHEMA IF EXISTS emulator CASCADE;")