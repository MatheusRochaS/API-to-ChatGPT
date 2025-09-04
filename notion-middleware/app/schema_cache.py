import time
from typing import Dict, Any, Tuple, Optional
from . import notion_client as notion

# cache: db_id -> (timestamp, schema_json)
_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
TTL = 300  # 5 minutos

async def get_schema(db_id: str) -> Dict[str, Any]:
    now = time.time()
    if db_id in _cache and (now - _cache[db_id][0]) < TTL:
        return _cache[db_id][1]
    data = await notion.notion_get_database(db_id)  # 1 request
    _cache[db_id] = (now, data)
    return data

async def props_by_name(db_id: str) -> Dict[str, Any]:
    schema = await get_schema(db_id)
    return schema.get("properties", {})  # nome -> metadata
