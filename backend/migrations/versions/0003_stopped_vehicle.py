"""Allow anomaly types stopped_vehicle and people_on_road.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18 20:00:00

"""
from alembic import op


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

_OLD = "type IN ('high_density', 'camera_offline')"
_NEW = "type IN ('high_density', 'camera_offline', 'stopped_vehicle', 'people_on_road')"


def upgrade():
    op.drop_constraint(op.f('ck_anomalies_type_valid'), 'anomalies', type_='check')
    op.create_check_constraint(op.f('ck_anomalies_type_valid'), 'anomalies', _NEW)


def downgrade():
    op.execute("DELETE FROM anomalies WHERE type IN ('stopped_vehicle', 'people_on_road')")
    op.drop_constraint(op.f('ck_anomalies_type_valid'), 'anomalies', type_='check')
    op.create_check_constraint(op.f('ck_anomalies_type_valid'), 'anomalies', _OLD)
