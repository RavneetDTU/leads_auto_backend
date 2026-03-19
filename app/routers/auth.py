from fastapi import APIRouter, HTTPException, Depends
from app.models import UserLogin, UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login", response_model=UserResponse)
async def login(credentials: UserLogin):
    # TODO: Implement actual firebase auth verification or lookup in users collection
    # For V1 demo/assumption friendly:
    
    # Mock check (replace with DB check)
    if credentials.email == "agent@company.com" and credentials.password == "123456":
         return UserResponse(
             token="mock_jwt_token_123",
             user={
                 "id": "mock_user_id_1",
                 "name": "Agent Name",
                 "email": credentials.email
             }
         )
    
    raise HTTPException(status_code=401, detail="Invalid credentials")
