from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# A second engine, synchronous, for everything that runs outside the request
# path: Alembic and the offline ML pipeline. The application's async engine in
# session.py is untouched -- pandas.read_sql and COPY both want a plain DBAPI
# connection, and the ML scripts have no reason to be async.
sync_engine = create_engine(
    settings.sync_database_url,
    pool_pre_ping=True,
)

SyncSessionFactory = sessionmaker(
    bind=sync_engine,
    expire_on_commit=False,
)
