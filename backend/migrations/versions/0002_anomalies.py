"""Anomalies table (high_density, camera_offline).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05 10:00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('anomalies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('camera_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=32), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint("type IN ('high_density', 'camera_offline')", name=op.f('ck_anomalies_type_valid')),
    sa.CheckConstraint('ended_at IS NULL OR ended_at >= started_at', name=op.f('ck_anomalies_ended_after_start')),
    sa.ForeignKeyConstraint(['camera_id'], ['cameras.id'], name=op.f('fk_anomalies_camera_id_cameras'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_anomalies'))
    )
    with op.batch_alter_table('anomalies', schema=None) as batch_op:
        batch_op.create_index('ix_anomalies_started_at', ['started_at'], unique=False)
        batch_op.create_index('uq_anomalies_active', ['camera_id', 'type'], unique=True,
                              postgresql_where=sa.text('ended_at IS NULL'))


def downgrade():
    with op.batch_alter_table('anomalies', schema=None) as batch_op:
        batch_op.drop_index('uq_anomalies_active', postgresql_where=sa.text('ended_at IS NULL'))
        batch_op.drop_index('ix_anomalies_started_at')

    op.drop_table('anomalies')
