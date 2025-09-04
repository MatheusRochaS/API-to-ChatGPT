from fastapi import Header, HTTPException
from typing import Optional
from .settings import settings

def check_auth(authorization: Optional[str]):
    if not settings.MIDDLEWARE_API_KEY:
        return  # sem chave → sem auth (não recomendado)
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != settings.MIDDLEWARE_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
