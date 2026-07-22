"""Initial production schema frozen at revision 0001.

Revision ID: 0001
Revises: None
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('alert_rules',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('rule_type', sa.String(length=80), nullable=False),
    sa.Column('metric_key', sa.String(length=100), nullable=True),
    sa.Column('comparison_type', sa.String(length=60), nullable=True),
    sa.Column('operator', sa.String(length=12), nullable=False),
    sa.Column('threshold', sa.Numeric(precision=24, scale=8), nullable=False),
    sa.Column('min_spend', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('min_orders', sa.Integer(), nullable=True),
    sa.Column('min_amount', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('room_scope', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('anchor_scope', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('control_scope', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('severity', sa.String(length=24), nullable=False),
    sa.Column('cooldown_minutes', sa.Integer(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('push_enabled', sa.Boolean(), nullable=False),
    sa.Column('suggestion_template', sa.Text(), nullable=False),
    sa.Column('created_by', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alert_rules'))
    )
    op.create_index(op.f('ix_alert_rules_rule_type'), 'alert_rules', ['rule_type'], unique=False)
    op.create_table('metric_definitions',
    sa.Column('metric_key', sa.String(length=100), nullable=False),
    sa.Column('source_field_name', sa.String(length=200), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=False),
    sa.Column('category', sa.String(length=80), nullable=False),
    sa.Column('unit', sa.String(length=30), nullable=False),
    sa.Column('precision', sa.Integer(), nullable=False),
    sa.Column('scope', sa.String(length=30), nullable=False),
    sa.Column('aggregation_strategy', sa.String(length=40), nullable=False),
    sa.Column('numerator_metric_key', sa.String(length=100), nullable=True),
    sa.Column('denominator_metric_key', sa.String(length=100), nullable=True),
    sa.Column('chartable', sa.Boolean(), nullable=False),
    sa.Column('comparable', sa.Boolean(), nullable=False),
    sa.Column('alertable', sa.Boolean(), nullable=False),
    sa.Column('direction', sa.String(length=30), nullable=False),
    sa.Column('default_visible', sa.Boolean(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_metric_definitions')),
    sa.UniqueConstraint('metric_key', name=op.f('uq_metric_definitions_metric_key')),
    sa.UniqueConstraint('source_field_name', name=op.f('uq_metric_definitions_source_field_name'))
    )
    op.create_table('persons',
    sa.Column('display_name', sa.String(length=200), nullable=False),
    sa.Column('base_name', sa.String(length=100), nullable=False),
    sa.Column('prefix', sa.String(length=20), nullable=True),
    sa.Column('primary_role', sa.String(length=40), nullable=True),
    sa.Column('employment_status', sa.String(length=40), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_persons'))
    )
    op.create_index(op.f('ix_persons_base_name'), 'persons', ['base_name'], unique=False)
    op.create_table('roles',
    sa.Column('name', sa.String(length=40), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_roles')),
    sa.UniqueConstraint('name', name=op.f('uq_roles_name'))
    )
    op.create_table('rooms',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('brand', sa.String(length=200), nullable=True),
    sa.Column('category', sa.String(length=200), nullable=True),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('confirmed', sa.Boolean(), nullable=False),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('source_aliases', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rooms')),
    sa.UniqueConstraint('name', name=op.f('uq_rooms_name'))
    )
    op.create_table('shift_rules',
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('start_time', sa.Time(), nullable=True),
    sa.Column('end_time', sa.Time(), nullable=True),
    sa.Column('crosses_midnight', sa.Boolean(), nullable=False),
    sa.Column('is_rest', sa.Boolean(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_shift_rules')),
    sa.UniqueConstraint('name', name=op.f('uq_shift_rules_name'))
    )
    op.create_table('source_configs',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('source_type', sa.String(length=40), nullable=False),
    sa.Column('source_role', sa.String(length=40), nullable=False),
    sa.Column('app_token', sa.String(length=200), nullable=False),
    sa.Column('table_id', sa.String(length=200), nullable=False),
    sa.Column('view_id', sa.String(length=200), nullable=True),
    sa.Column('default_room_name', sa.String(length=200), nullable=True),
    sa.Column('schedule_year', sa.Integer(), nullable=True),
    sa.Column('field_mapping', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_source_configs')),
    sa.UniqueConstraint('source_type', 'app_token', 'table_id', 'source_role', name=op.f('uq_source_configs_source_type'))
    )
    op.create_table('system_settings',
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('value', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('encrypted', sa.Boolean(), nullable=False),
    sa.Column('updated_by', sa.Uuid(), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('key', name=op.f('pk_system_settings'))
    )
    op.create_table('users',
    sa.Column('feishu_user_id', sa.String(length=200), nullable=True),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('avatar_url', sa.Text(), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=True),
    sa.Column('role_name', sa.String(length=40), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    sa.UniqueConstraint('feishu_user_id', name=op.f('uq_users_feishu_user_id'))
    )
    op.create_table('alert_events',
    sa.Column('rule_id', sa.Uuid(), nullable=False),
    sa.Column('dedup_key', sa.String(length=64), nullable=False),
    sa.Column('triggered_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('room_id', sa.Uuid(), nullable=False),
    sa.Column('business_date', sa.Date(), nullable=False),
    sa.Column('hour_slot', sa.String(length=8), nullable=False),
    sa.Column('anchor_name', sa.String(length=200), nullable=True),
    sa.Column('control_name', sa.String(length=200), nullable=True),
    sa.Column('metric_key', sa.String(length=100), nullable=True),
    sa.Column('current_value', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('baseline_value', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('delta_value', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('ratio_percent', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('growth_percent', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('severity', sa.String(length=24), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('suggestion', sa.Text(), nullable=False),
    sa.Column('push_status', sa.String(length=24), nullable=False),
    sa.Column('push_attempts', sa.Integer(), nullable=False),
    sa.Column('pushed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('push_error', sa.Text(), nullable=True),
    sa.Column('acknowledged', sa.Boolean(), nullable=False),
    sa.Column('acknowledged_by', sa.Uuid(), nullable=True),
    sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolution_note', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], name=op.f('fk_alert_events_room_id_rooms')),
    sa.ForeignKeyConstraint(['rule_id'], ['alert_rules.id'], name=op.f('fk_alert_events_rule_id_alert_rules')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_alert_events')),
    sa.UniqueConstraint('dedup_key', name=op.f('uq_alert_events_dedup_key'))
    )
    op.create_index(op.f('ix_alert_events_business_date'), 'alert_events', ['business_date'], unique=False)
    op.create_index(op.f('ix_alert_events_room_id'), 'alert_events', ['room_id'], unique=False)
    op.create_index(op.f('ix_alert_events_rule_id'), 'alert_events', ['rule_id'], unique=False)
    op.create_table('anchor_schedules',
    sa.Column('source_config_id', sa.Uuid(), nullable=False),
    sa.Column('source_record_id', sa.String(length=300), nullable=False),
    sa.Column('room_id', sa.Uuid(), nullable=False),
    sa.Column('schedule_date', sa.Date(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('month', sa.Integer(), nullable=False),
    sa.Column('day', sa.Integer(), nullable=False),
    sa.Column('hour_slot', sa.String(length=8), nullable=False),
    sa.Column('hour_order', sa.Integer(), nullable=False),
    sa.Column('planned_anchor_raw', sa.String(length=200), nullable=True),
    sa.Column('planned_anchor_canonical', sa.String(length=200), nullable=True),
    sa.Column('planned_anchor_base_names', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('schedule_status', sa.String(length=30), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], name=op.f('fk_anchor_schedules_room_id_rooms')),
    sa.ForeignKeyConstraint(['source_config_id'], ['source_configs.id'], name=op.f('fk_anchor_schedules_source_config_id_source_configs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_anchor_schedules')),
    sa.UniqueConstraint('room_id', 'schedule_date', 'hour_slot', name=op.f('uq_anchor_schedules_room_id'))
    )
    op.create_index(op.f('ix_anchor_schedules_hour_slot'), 'anchor_schedules', ['hour_slot'], unique=False)
    op.create_index(op.f('ix_anchor_schedules_room_id'), 'anchor_schedules', ['room_id'], unique=False)
    op.create_index(op.f('ix_anchor_schedules_schedule_date'), 'anchor_schedules', ['schedule_date'], unique=False)
    op.create_table('audit_logs',
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('action', sa.String(length=100), nullable=False),
    sa.Column('object_type', sa.String(length=100), nullable=False),
    sa.Column('object_id', sa.String(length=200), nullable=True),
    sa.Column('before_summary', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('after_summary', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_audit_logs_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)
    op.create_table('person_aliases',
    sa.Column('person_id', sa.Uuid(), nullable=False),
    sa.Column('alias', sa.String(length=200), nullable=False),
    sa.Column('normalized_alias', sa.String(length=200), nullable=False),
    sa.Column('source', sa.String(length=40), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['person_id'], ['persons.id'], name=op.f('fk_person_aliases_person_id_persons')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_person_aliases')),
    sa.UniqueConstraint('normalized_alias', name=op.f('uq_person_aliases_normalized_alias'))
    )
    op.create_index(op.f('ix_person_aliases_person_id'), 'person_aliases', ['person_id'], unique=False)
    op.create_table('raw_source_records',
    sa.Column('source_config_id', sa.Uuid(), nullable=False),
    sa.Column('source_record_id', sa.String(length=300), nullable=False),
    sa.Column('source_created_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('source_modified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('raw_fields', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('payload_hash', sa.String(length=64), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['source_config_id'], ['source_configs.id'], name=op.f('fk_raw_source_records_source_config_id_source_configs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_raw_source_records')),
    sa.UniqueConstraint('source_config_id', 'source_record_id', name=op.f('uq_raw_source_records_source_config_id'))
    )
    op.create_index(op.f('ix_raw_source_records_payload_hash'), 'raw_source_records', ['payload_hash'], unique=False)
    op.create_index(op.f('ix_raw_source_records_source_config_id'), 'raw_source_records', ['source_config_id'], unique=False)

    op.create_table('staff_schedules',
    sa.Column('source_config_id', sa.Uuid(), nullable=False),
    sa.Column('source_record_id', sa.String(length=300), nullable=False),
    sa.Column('person_id', sa.Uuid(), nullable=False),
    sa.Column('schedule_date', sa.Date(), nullable=False),
    sa.Column('role', sa.String(length=40), nullable=False),
    sa.Column('employment_status', sa.String(length=40), nullable=True),
    sa.Column('shift_raw', sa.String(length=100), nullable=True),
    sa.Column('shift_name', sa.String(length=100), nullable=True),
    sa.Column('shift_start', sa.Time(), nullable=True),
    sa.Column('shift_end', sa.Time(), nullable=True),
    sa.Column('crosses_midnight', sa.Boolean(), nullable=False),
    sa.Column('is_rest', sa.Boolean(), nullable=False),
    sa.Column('time_configured', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['person_id'], ['persons.id'], name=op.f('fk_staff_schedules_person_id_persons')),
    sa.ForeignKeyConstraint(['source_config_id'], ['source_configs.id'], name=op.f('fk_staff_schedules_source_config_id_source_configs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_staff_schedules')),
    sa.UniqueConstraint('person_id', 'schedule_date', name=op.f('uq_staff_schedules_person_id'))
    )
    op.create_index(op.f('ix_staff_schedules_person_id'), 'staff_schedules', ['person_id'], unique=False)
    op.create_index(op.f('ix_staff_schedules_schedule_date'), 'staff_schedules', ['schedule_date'], unique=False)
    op.create_table('sync_runs',
    sa.Column('source_config_id', sa.Uuid(), nullable=False),
    sa.Column('mode', sa.String(length=24), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('records_read', sa.Integer(), nullable=False),
    sa.Column('records_created', sa.Integer(), nullable=False),
    sa.Column('records_updated', sa.Integer(), nullable=False),
    sa.Column('records_unchanged', sa.Integer(), nullable=False),
    sa.Column('records_invalid', sa.Integer(), nullable=False),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.Column('triggered_by', sa.String(length=200), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['source_config_id'], ['source_configs.id'], name=op.f('fk_sync_runs_source_config_id_source_configs')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sync_runs'))
    )
    op.create_index(op.f('ix_sync_runs_source_config_id'), 'sync_runs', ['source_config_id'], unique=False)
    op.create_table('user_room_permissions',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('room_id', sa.Uuid(), nullable=False),
    sa.Column('can_export', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], name=op.f('fk_user_room_permissions_room_id_rooms')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_room_permissions_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_room_permissions')),
    sa.UniqueConstraint('user_id', 'room_id', name=op.f('uq_user_room_permissions_user_id'))
    )
    op.create_index(op.f('ix_user_room_permissions_room_id'), 'user_room_permissions', ['room_id'], unique=False)
    op.create_index(op.f('ix_user_room_permissions_user_id'), 'user_room_permissions', ['user_id'], unique=False)
    op.create_table('live_points',
    sa.Column('raw_source_record_id', sa.Uuid(), nullable=False),
    sa.Column('room_id', sa.Uuid(), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('business_date', sa.Date(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('month', sa.Integer(), nullable=False),
    sa.Column('hour_slot', sa.String(length=8), nullable=True),
    sa.Column('hour_order', sa.Integer(), nullable=True),
    sa.Column('anchor_raw', sa.String(length=200), nullable=True),
    sa.Column('anchor_canonical', sa.String(length=200), nullable=True),
    sa.Column('anchor_base_name', sa.String(length=100), nullable=True),
    sa.Column('anchor_members', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('anchor_note', sa.String(length=300), nullable=True),
    sa.Column('control_raw', sa.String(length=200), nullable=True),
    sa.Column('control_canonical', sa.String(length=200), nullable=True),
    sa.Column('control_base_name', sa.String(length=100), nullable=True),
    sa.Column('auto_check_status', sa.String(length=40), nullable=True),
    sa.Column('valid', sa.Boolean(), nullable=False),
    sa.Column('invalid_reason', sa.Text(), nullable=True),
    sa.Column('raw_payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['raw_source_record_id'], ['raw_source_records.id'], name=op.f('fk_live_points_raw_source_record_id_raw_source_records')),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], name=op.f('fk_live_points_room_id_rooms')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_live_points')),
    sa.UniqueConstraint('raw_source_record_id', name=op.f('uq_live_points_raw_source_record_id'))
    )
    op.create_index('ix_live_points_anchor_date', 'live_points', ['anchor_base_name', 'business_date'], unique=False)
    op.create_index(op.f('ix_live_points_business_date'), 'live_points', ['business_date'], unique=False)
    op.create_index('ix_live_points_control_date', 'live_points', ['control_base_name', 'business_date'], unique=False)
    op.create_index(op.f('ix_live_points_hour_slot'), 'live_points', ['hour_slot'], unique=False)
    op.create_index('ix_live_points_room_date_hour', 'live_points', ['room_id', 'business_date', 'hour_order'], unique=False)
    op.create_index(op.f('ix_live_points_room_id'), 'live_points', ['room_id'], unique=False)
    op.create_index('ix_live_points_room_observed', 'live_points', ['room_id', 'observed_at'], unique=False)
    op.create_index(op.f('ix_live_points_valid'), 'live_points', ['valid'], unique=False)
    op.create_table('hourly_facts',
    sa.Column('room_id', sa.Uuid(), nullable=False),
    sa.Column('business_date', sa.Date(), nullable=False),
    sa.Column('year', sa.Integer(), nullable=False),
    sa.Column('month', sa.Integer(), nullable=False),
    sa.Column('hour_slot', sa.String(length=8), nullable=False),
    sa.Column('hour_order', sa.Integer(), nullable=False),
    sa.Column('hour_start_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('hour_end_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('latest_point_id', sa.Uuid(), nullable=True),
    sa.Column('latest_observed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actual_anchor_canonical', sa.String(length=200), nullable=True),
    sa.Column('actual_anchor_base_names', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('actual_control_canonical', sa.String(length=200), nullable=True),
    sa.Column('planned_anchor_canonical', sa.String(length=200), nullable=True),
    sa.Column('planned_anchor_base_names', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('anchor_schedule_status', sa.String(length=30), nullable=True),
    sa.Column('anchor_match_status', sa.String(length=40), nullable=False),
    sa.Column('control_shift_name', sa.String(length=100), nullable=True),
    sa.Column('control_is_scheduled', sa.Boolean(), nullable=True),
    sa.Column('control_is_rest', sa.Boolean(), nullable=True),
    sa.Column('control_may_be_on_duty', sa.Boolean(), nullable=True),
    sa.Column('data_status', sa.String(length=24), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['latest_point_id'], ['live_points.id'], name=op.f('fk_hourly_facts_latest_point_id_live_points')),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], name=op.f('fk_hourly_facts_room_id_rooms')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_hourly_facts')),
    sa.UniqueConstraint('room_id', 'business_date', 'hour_slot', name=op.f('uq_hourly_facts_room_id'))
    )
    op.create_index(op.f('ix_hourly_facts_business_date'), 'hourly_facts', ['business_date'], unique=False)
    op.create_index(op.f('ix_hourly_facts_hour_slot'), 'hourly_facts', ['hour_slot'], unique=False)
    op.create_index(op.f('ix_hourly_facts_room_id'), 'hourly_facts', ['room_id'], unique=False)
    op.create_table('live_point_metrics',
    sa.Column('live_point_id', sa.Uuid(), nullable=False),
    sa.Column('metric_key', sa.String(length=100), nullable=False),
    sa.Column('numeric_value', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('raw_value', sa.Text(), nullable=True),
    sa.Column('parse_status', sa.String(length=24), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['live_point_id'], ['live_points.id'], name=op.f('fk_live_point_metrics_live_point_id_live_points')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_live_point_metrics')),
    sa.UniqueConstraint('live_point_id', 'metric_key', name=op.f('uq_live_point_metrics_live_point_id'))
    )
    op.create_index(op.f('ix_live_point_metrics_live_point_id'), 'live_point_metrics', ['live_point_id'], unique=False)
    op.create_index(op.f('ix_live_point_metrics_metric_key'), 'live_point_metrics', ['metric_key'], unique=False)
    op.create_table('hourly_metrics',
    sa.Column('hourly_fact_id', sa.Uuid(), nullable=False),
    sa.Column('metric_key', sa.String(length=100), nullable=False),
    sa.Column('numeric_value', sa.Numeric(precision=24, scale=8), nullable=True),
    sa.Column('value_source', sa.String(length=40), nullable=False),
    sa.Column('quality_status', sa.String(length=40), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['hourly_fact_id'], ['hourly_facts.id'], name=op.f('fk_hourly_metrics_hourly_fact_id_hourly_facts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_hourly_metrics')),
    sa.UniqueConstraint('hourly_fact_id', 'metric_key', name=op.f('uq_hourly_metrics_hourly_fact_id'))
    )
    op.create_index(op.f('ix_hourly_metrics_hourly_fact_id'), 'hourly_metrics', ['hourly_fact_id'], unique=False)
    op.create_index(op.f('ix_hourly_metrics_metric_key'), 'hourly_metrics', ['metric_key'], unique=False)


def downgrade() -> None:
    op.drop_table('hourly_metrics')
    op.drop_table('live_point_metrics')
    op.drop_table('hourly_facts')
    op.drop_table('live_points')
    op.drop_table('user_room_permissions')
    op.drop_table('sync_runs')
    op.drop_table('staff_schedules')
    op.drop_table('raw_source_records')
    op.drop_table('person_aliases')
    op.drop_table('audit_logs')
    op.drop_table('anchor_schedules')
    op.drop_table('alert_events')
    op.drop_table('users')
    op.drop_table('system_settings')
    op.drop_table('source_configs')
    op.drop_table('shift_rules')
    op.drop_table('rooms')
    op.drop_table('roles')
    op.drop_table('persons')
    op.drop_table('metric_definitions')
    op.drop_table('alert_rules')
