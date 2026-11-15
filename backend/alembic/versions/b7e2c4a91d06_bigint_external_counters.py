"""widen external metric counters to bigint

Revision ID: b7e2c4a91d06
Revises: 79e65b1256f4
Create Date: 2026-11-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b7e2c4a91d06'
down_revision = '79e65b1256f4'
branch_labels = None
depends_on = None


_COLUMNS = [
    ('tracked_channels', 'subscribers'),
    ('tracked_channels', 'total_views'),
    ('tracked_channels', 'video_count'),
    ('tracked_videos', 'views'),
    ('tracked_videos', 'likes'),
    ('tracked_videos', 'comment_count'),
    ('video_stats_snapshots', 'views'),
    ('video_stats_snapshots', 'likes'),
    ('video_stats_snapshots', 'comment_count'),
    ('comments', 'like_count'),
    ('comments', 'reply_count'),
    ('ads_campaign_performance', 'impressions'),
    ('ads_campaign_performance', 'clicks'),
    ('ads_campaign_performance', 'cost_micros'),
    ('ads_campaign_performance', 'video_views'),
]


def upgrade() -> None:
    for table, column in _COLUMNS:
        op.alter_column(table, column, type_=sa.BigInteger(),
                        existing_type=sa.Integer(), existing_nullable=False)


def downgrade() -> None:
    for table, column in reversed(_COLUMNS):
        op.alter_column(table, column, type_=sa.Integer(),
                        existing_type=sa.BigInteger(), existing_nullable=False)
