"""make device nullable

Revision ID: 0805d4bf4d9d
Revises: f7ca57091454
Create Date: 2020-06-15 10:24:59.287323

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0805d4bf4d9d'
down_revision = 'f7ca57091454'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('repair', 'device_id',
               existing_type=sa.INTEGER(),
               nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('repair', 'device_id',
               existing_type=sa.INTEGER(),
               nullable=False)
    # ### end Alembic commands ###
