import asyncio
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID
from fastapi import FastAPI, Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import paymentsrequest,paymentsresponse

# Database and Model Imports
from database import engine,get_session
from models import Transaction,Base

# --- Machine Learning Placeholder Logic ---
# In a real setup, you would load your saved scikit-learn model here:
# import joblib
# model = joblib.load("sales_model.pkl")

def compute_merchant_forecast(historical_data: list) -> dict:
    """
    PURE SYNCHRONOUS CPU WORK.
    This function handles heavy math or ML predictions (e.g., scikit-learn linear regression).
    Because it is plain 'def', we run it inside an executor so it doesn't freeze FastAPI.
    """
    # 1. Take the data passed from the DB query
    # 2. Convert to a Pandas DataFrame or feed directly into model
    # 3. Return the clean prediction dictionary
    
    total_revenue = sum(row.amount for row in historical_data if row.status == "SUCCESS")
    predicted_next_week = total_revenue * 1.05  # Simple placeholder math for now
    
    return {
        "historical_total_revenue": float(total_revenue),
        "forecasted_next_week_revenue": float(predicted_next_week),
        "status": "computed_via_thread_pool"
    }

# --- Application Lifecycle ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Auto-create tables on container startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all) #Base.metadata is a built-in registry where SQLAlchemy stores a master list of all the Python table models you have created (like your Transaction model).
        #run_sync acts as a special translator gateway. It takes that synchronous table-creation function, temporarily opens up a safe synchronous gateway over your async connection, executes the table creation, and closes the gateway.
        
    yield

app = FastAPI(lifespan=lifespan)

# --- 1. THE ASYNC PAYMENT PATHWAY (I/O Bound) ---
@app.post("/payments")
async def create_transaction(
    payload : paymentsrequest,
    idempotency_key: Annotated[str, Header()],
    session: AsyncSession = Depends(get_session)
):
    try:
        UUID(idempotency_key)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")

    new_tx = Transaction(
    idempotency_key=idempotency_key,
    merchant_id=payload.merchant_id,
    amount=payload.amount,
    currency=payload.currency,
    status="PENDING"
)
    try:
        session.add(new_tx) #"session.add() places a Python object into the SQLAlchemy Session’s tracking system, marking it as Pending. It does not immediately send any SQL commands to the database, nor does it insert a row. It simply tells the Unit of Work pattern that this object needs to be persisted. The actual SQL INSERT statement is deferred until the session is explicitly or implicitly flushed or committed."
        await session.commit() # database permanantly writes the transaction to the disk
        await session.refresh(new_tx)
        return {"status": "SUCCESS", "transaction_id": str(new_tx.transaction_id)}
    except Exception as e:
     await session.rollback()
     raise HTTPException(status_code=500, detail=str(e))  # show real error

# --- 2. THE ANALYTICS & ML PATHWAY (Async DB + Sync ML) ---
@app.get("/merchants/{merchant_id}/analytics")
async def get_merchant_analytics(
    merchant_id: str,
    session: AsyncSession = Depends(get_session)
):
    # STEP A: Use asyncpg to fetch the historical data without blocking the app
    # (Using a standard SQLAlchemy async select query)
    from sqlalchemy import select
    result = await session.execute(
        select(Transaction).where(Transaction.merchant_id == merchant_id)
    )
    historical_rows = result.scalars().all()

    if not historical_rows:
        raise HTTPException(status_code=404, detail="No transactional history found for merchant")

    # STEP B: Hand off the heavy ML/Math calculation to a background thread pool
    loop = asyncio.get_running_loop()
    
    # run_in_executor takes: (Executor [None uses default], Function Name, Function Arguments...)
    ml_results = await loop.run_in_executor(
        None, 
        compute_merchant_forecast, 
        historical_rows
    )

    # STEP C: Return combined results safely
    return {
        "merchant_id": merchant_id,
        "metrics": ml_results
    }


 