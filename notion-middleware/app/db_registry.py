import json, time, os
from typing import Optional, Dict

REG_PATH = os.getenv("DB_REGISTRY_PATH", "/tmp/db_registry.json")

_memory_map: Dict[str, str] = {}
_loaded = False

def _load():
    global _loaded, _memory_map
    if _loaded: return
    try:
        with open(REG_PATH, "r", encoding="utf-8") as f:
            _memory_map = json.load(f)
    except FileNotFoundError:
        _memory_map = {}
    _loaded = True

def _save():
    with open(REG_PATH, "w", encoding="utf-8") as f:
        json.dump(_memory_map, f, ensure_ascii=False, indent=2)

def set_db(key: str, db_id: str):
    _load()
    _memory_map[key] = db_id
    _save()

def get_db(key: str) -> Optional[str]:
    _load()
    return _memory_map.get(key)

def all_dbs() -> Dict[str, str]:
    _load()
    return dict(_memory_map)
