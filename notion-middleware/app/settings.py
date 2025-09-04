from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseModel):
    NOTION_TOKEN: str = os.getenv("NOTION_TOKEN", "")
    PROJECTS_DB: str = os.getenv("NOTION_PROJECTS_DB_ID", "")
    TASKS_DB: str = os.getenv("NOTION_TASKS_DB_ID", "")
    MIDDLEWARE_API_KEY: str = os.getenv("MIDDLEWARE_API_KEY", "")

settings = Settings()

for k, v in settings.model_dump().items():
    if not v:
        raise RuntimeError(f"Falta configurar variável: {k}")
