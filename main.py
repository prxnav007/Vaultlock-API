from fastapi import FastAPI, Header,HTTPException
from model import PaymentsRequest
from model import PaymentsResponse
from typing import Annotated
from uuid import UUID


app=FastAPI()

@app.post("/Payments",response_model=PaymentsResponse)
async def create_transaction(request : PaymentsRequest,Idempotency_key : Annotated[str ,Header()]):
 try:
  UUID(Idempotency_key)
 except ValueError: #UUID() throws a value error
  raise HTTPException(status_code=400,detail="Idempotency_key must be a valid UUID")
 return {
    "userid": request.userid,
    "amount": request.amount,
    "status": "PENDING",  # You define the status here
    "Idempotency_key": Idempotency_key,
    "currency" : request.currency
}
