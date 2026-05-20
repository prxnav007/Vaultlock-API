
from pydantic import BaseModel,Field
from uuid import UUID

class PaymentsRequest(BaseModel):
  userid : str
  amount : float = Field(..., gt=0, description="Must be > 0")
  currency: str = Field(...,max_length=3,min_length=3) 

  
class PaymentsResponse(BaseModel):
  userid:str
  currency: str = Field(...,max_length=3,min_length=3) 
  status :str
  amount :float=Field(...,gt=0,description="Must be greater >0")
  Idempotency_key: UUID

