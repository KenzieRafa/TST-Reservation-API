"""API Dependencies - Authentication"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from uuid import UUID

from domain.auth import User, UserInDB
from infrastructure.security import SECRET_KEY, ALGORITHM, get_password_hash
from api.schemas import TokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Mock database for users
# In production, this would be a database call
_fake_users_db = {
    "admin": {
        "username": "admin",
        "full_name": "Admin User",
        "email": "admin@example.com",
        "plain_password": "admin123",  # Will be hashed on first access
        "disabled": False,
        "user_id": "123e4567-e89b-12d3-a456-426614174000" # Fixed UUID for admin
    }
}

# Public alias for backwards compatibility
fake_users_db = _fake_users_db

# Cache for hashed passwords
_password_hash_cache = {}

def _get_hashed_password(username: str) -> str:
    """Lazily hash passwords on first access"""
    if username not in _password_hash_cache:
        user = _fake_users_db.get(username)
        if user and "plain_password" in user:
            _password_hash_cache[username] = get_password_hash(user["plain_password"])
    return _password_hash_cache.get(username, "")

def get_user(db, username: str):
    if username in db:
        user_dict = db[username].copy()
        # Replace plain_password with hashed_password
        if "plain_password" in user_dict:
            user_dict["hashed_password"] = _get_hashed_password(username)
            del user_dict["plain_password"]
        return UserInDB(**user_dict)
    return None

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception
    
    user = get_user(_fake_users_db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(current_user: User = Depends(get_current_user)):
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
