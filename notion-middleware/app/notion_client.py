import httpx
from .settings import settings

NOTION_BASE = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {settings.NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}

async def notion_query_database(db_id: str, payload: dict):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{NOTION_BASE}/databases/{db_id}/query", headers=HEADERS, json=payload)
        r.raise_for_status()
        return r.json()

async def notion_create_page(payload: dict):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{NOTION_BASE}/pages", headers=HEADERS, json=payload)
        r.raise_for_status()
        return r.json()

async def notion_update_page(page_id: str, payload: dict):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.patch(f"{NOTION_BASE}/pages/{page_id}", headers=HEADERS, json=payload)
        r.raise_for_status()
        return r.json()

async def notion_get_database(db_id: str):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{NOTION_BASE}/databases/{db_id}", headers=HEADERS)
        r.raise_for_status()
        return r.json()
