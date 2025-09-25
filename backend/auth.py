from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import os
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Security configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

# JWT Configuration from environment
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-super-secret-jwt-key-change-this-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Admin user configuration
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
CREATE_ADMIN_ON_STARTUP = os.getenv("CREATE_ADMIN_ON_STARTUP", "true").lower() == "true"


class AuthService:
    def __init__(self):
        # In production, this should be stored in database
        # For now, using in-memory storage for admin user
        self.users = {}
        if CREATE_ADMIN_ON_STARTUP:
            self._create_admin_user()

    def _create_admin_user(self):
        """Create admin user on startup if configured"""
        hashed_password = self.get_password_hash(ADMIN_PASSWORD)
        self.users[ADMIN_USERNAME] = {
            "username": ADMIN_USERNAME,
            "email": ADMIN_EMAIL,
            "hashed_password": hashed_password,
            "is_admin": True,
            "created_at": datetime.utcnow(),
            "is_active": True
        }
        logger.info(f"Admin user '{ADMIN_USERNAME}' created successfully")

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against its hash"""
        return pwd_context.verify(plain_password, hashed_password)

    def get_password_hash(self, password: str) -> str:
        """Generate password hash"""
        return pwd_context.hash(password)

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Authenticate user with username and password"""
        user = self.users.get(username)
        if not user:
            return None
        if not self.verify_password(password, user["hashed_password"]):
            return None
        if not user.get("is_active", False):
            return None
        return user

    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None):
        """Create JWT access token"""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire, "type": "access"})
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return encoded_jwt

    def create_refresh_token(self, data: dict):
        """Create JWT refresh token"""
        to_encode = data.copy()
        expire = datetime.utcnow() + timedelta(days=JWT_REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({"exp": expire, "type": "refresh"})
        encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            username: str = payload.get("sub")
            if username is None:
                return None
            
            # Check if user still exists and is active
            user = self.users.get(username)
            if not user or not user.get("is_active", False):
                return None
                
            return payload
        except JWTError as e:
            logger.error(f"JWT verification failed: {e}")
            return None

    def get_current_user(self, credentials: HTTPAuthorizationCredentials = Depends(security)) -> Dict[str, Any]:
        """Dependency to get current authenticated user"""
        token = credentials.credentials
        payload = self.verify_token(token)
        
        if payload is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        username = payload.get("sub")
        user = self.users.get(username)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user

    def require_admin(self, current_user: Dict[str, Any]) -> Dict[str, Any]:
        """Dependency to require admin access"""
        if not current_user.get("is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        return current_user

    def create_user(self, username: str, email: str, password: str, is_admin: bool = False) -> Dict[str, Any]:
        """Create a new user"""
        if username in self.users:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists"
            )
        
        hashed_password = self.get_password_hash(password)
        user = {
            "username": username,
            "email": email,
            "hashed_password": hashed_password,
            "is_admin": is_admin,
            "created_at": datetime.utcnow(),
            "is_active": True
        }
        
        self.users[username] = user
        logger.info(f"User '{username}' created successfully")
        
        # Return user without password hash
        return {k: v for k, v in user.items() if k != "hashed_password"}

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username (without password hash)"""
        user = self.users.get(username)
        if user:
            return {k: v for k, v in user.items() if k != "hashed_password"}
        return None

    def list_users(self) -> list:
        """List all users (without password hashes)"""
        return [
            {k: v for k, v in user.items() if k != "hashed_password"}
            for user in self.users.values()
        ]

    def update_user(self, username: str, **updates) -> Dict[str, Any]:
        """Update user information"""
        user = self.users.get(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Hash password if provided
        if "password" in updates:
            updates["hashed_password"] = self.get_password_hash(updates.pop("password"))
        
        # Update user data
        user.update(updates)
        logger.info(f"User '{username}' updated successfully")
        
        # Return user without password hash
        return {k: v for k, v in user.items() if k != "hashed_password"}

    def delete_user(self, username: str) -> bool:
        """Delete user"""
        if username not in self.users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prevent deleting admin user
        if username == ADMIN_USERNAME:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete admin user"
            )
        
        del self.users[username]
        logger.info(f"User '{username}' deleted successfully")
        return True


# Global auth service instance
auth_service = AuthService()


def get_current_user_dep(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """Dependency to get current authenticated user."""
    return auth_service.get_current_user(credentials)


def require_admin_dep(
    current_user: Dict[str, Any] = Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Dependency to require admin access."""
    return auth_service.require_admin(current_user)
