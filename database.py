from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

DATABASE_URL = "postgresql+asyncpg://Pranav:123@db:5432/vault_ledger"

# 1. The Connection String
# We use 'db' as the hostname because that will be the name of our Postgres container in Docker.
# Format: postgresql://[user]:[password]@[container_name]:[port]/[database_name]


# 2. The Engine (The Pipeline)
# This manages the pool of persistent connections to the database.
engine = create_async_engine(DATABASE_URL,echo=True)

# 3. The Session Factory (The Faucets)
# This creates temporary connections for single HTTP requests.
# - autocommit=False: Guarantees transactions won't save until we explicitly call session.commit()
# - autoflush=False: Prevents SQLAlchemy from sending premature background queries
SessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False   # in regular SQLAlchemy, after a commit, 
    #  SQLAlchemy "expires" all your objects so they reload from DB on next access. In async, that lazy reload triggers an implicit I/O outside an active session, which crashes. This flag keeps your objects usable after commit.
)



async def get_session():
    """
    This is the Dependency Injection function. 
    FastAPI calls this every time an endpoint asks for a database session.
    """
    async with SessionLocal() as session:
        yield session