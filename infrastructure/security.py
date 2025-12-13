from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from jose import jwt
from passlib.context import CryptContext
import hashlib

# Configuration (In production, these should be in env vars)
SECRET_KEY = "your-secret-key-keep-it-secret"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    # bcrypt 4.x compatibility: explicitly handle password length
    bcrypt__ident="2b"
)

def _prepare_password(password: str) -> str:
    """
    Prepare password for bcrypt to handle strings > 72 bytes.
    bcrypt has a 72-byte password limit. If password is longer,
    we pre-hash it with SHA256 to get a safe length string.
    SHA256 hex digest is 64 chars (64 bytes in UTF-8).
    """
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        # Pre-hash with SHA256 to get a safe length string
        # hexdigest() returns 64 chars
        return hashlib.sha256(password_bytes).hexdigest()
    return password

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash"""
    return pwd_context.verify(_prepare_password(plain_password), hashed_password)

def get_password_hash(password: str) -> str:
    """Generate password hash"""
    return pwd_context.hash(_prepare_password(password))

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# Force CI update