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

# ...
async def notion_retrieve_page(page_id: str):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{NOTION_BASE}/pages/{page_id}", headers=HEADERS)
        r.raise_for_status()
        return r.json()

async def notion_list_children(block_id: str, start_cursor: str = None):
    params = {}
    if start_cursor:
        params["start_cursor"] = start_cursor
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{NOTION_BASE}/blocks/{block_id}/children", headers=HEADERS, params=params)
        r.raise_for_status()
        return r.json()

def get_page_title(page_json: dict) -> str:
    props = page_json.get("properties", {})
    # tenta pegar a primeira property tipo "title"
    for v in props.values():
        if v.get("type") == "title":
            items = v.get("title", [])
            if items:
                return items[0].get("plain_text") or items[0].get("text",{}).get("content","")
    # fallback
    return page_json.get("id","")