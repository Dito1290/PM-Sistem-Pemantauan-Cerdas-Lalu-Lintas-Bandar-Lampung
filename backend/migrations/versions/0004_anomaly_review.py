"""Operator review of anomaly indications.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-24 20:00:00

"""
from alembic import op
import sqlalchemy as sa


revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('anomalies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('review_verdict', sa.String(length=8), nullable=True))
        batch_op.add_column(sa.Column('review_note', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('reviewed_by', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_check_constraint(
            op.f('ck_anomalies_review_valid'), "review_verdict IS NULL OR review_verdict IN ('true', 'false')")


def downgrade():
    with op.batch_alter_table('anomalies', schema=None) as batch_op:
        batch_op.drop_constraint(op.f('ck_anomalies_review_valid'), type_='check')
        batch_op.drop_column('reviewed_at')
        batch_op.drop_column('reviewed_by')
        batch_op.drop_column('review_note')
        batch_op.drop_column('review_verdict')
