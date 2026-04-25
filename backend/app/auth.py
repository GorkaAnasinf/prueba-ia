from fastapi import Security, Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPBearer, HTTPAuthorizationCredentials
from .config import settings

api_key_header = APIKeyHeader(name="X-API-Key")
bearer_scheme = HTTPBearer(auto_error=False)


def require_api_key(api_key: str = Security(api_key_header)) -> str:
    if api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    return api_key


def require_bearer_key(credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme)) -> str:
    if not credentials or credentials.credentials != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return credentials.credentials
