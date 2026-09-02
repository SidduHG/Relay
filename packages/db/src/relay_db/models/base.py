"""The shared declarative base every model inherits from.

migrations/env.py points target_metadata at Base.metadata — that's what
makes `alembic revision --autogenerate` able to diff "what the models say
the schema should be" against "what Postgres actually has" and write the
difference as a migration.
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Fixed naming for every constraint Alembic generates. Without this,
# Postgres names constraints itself (e.g. "users_email_key"), which is
# fine until a later migration needs to drop or alter one — you'd have to
# go look up the name it happened to get. Fixed names are guessable and
# grep-able instead.
_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_NAMING_CONVENTION)
