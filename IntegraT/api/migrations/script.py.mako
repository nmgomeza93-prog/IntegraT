"""${message}

Revisión: ${up_revision}
Anterior: ${down_revision | comma,n}
Creada: ${create_date}

REGLA: una migración aplicada NUNCA se edita. Para corregir, crea otra.
MySQL no tiene DDL transaccional: si falla a mitad, revisa y limpia antes de reintentar.
"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
