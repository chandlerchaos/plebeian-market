"""Configure relays.

Revision ID: f0ccfd30d79e
Revises: 0d4d373978f2
Create Date: 2023-04-19 14:32:43.420133

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f0ccfd30d79e'
down_revision = '0d4d373978f2'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('relays',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('url', sa.String(length=128), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('relays', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_relays_url'), ['url'], unique=True)

    op.create_table('user_relays',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('relay_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['relay_id'], ['relays.id'], ),
    sa.PrimaryKeyConstraint('user_id', 'relay_id')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('user_relays')
    with op.batch_alter_table('relays', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_relays_url'))

    op.drop_table('relays')
    # ### end Alembic commands ###
