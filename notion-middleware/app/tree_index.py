import os, json, time
from typing import Dict, Any, List, Optional, Tuple
from . import notion_client as notion

INDEX_PATH = os.getenv("TREE_INDEX_PATH", "/tmp/page_index.json")
TTL_SECONDS = int(os.getenv("TREE_INDEX_TTL", "604800"))  # 7Dias

def _load() -> Dict[str, Any]:
    if not os.path.exists(INDEX_PATH):
        return {"created_at": 0, "root": None, "nodes": {}}
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def _save(data: Dict[str, Any]):
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def build_index(root_page_id: str) -> Dict[str, Any]:
    """
    Faz uma varredura recursiva dos filhos (blocks) da root e salva:
    nodes[<id>] = {"id","type","title","parent_id"}
    Também inclui databases encontrados (object=database) via search filtrando parent.
    """
    nodes: Dict[str, Any] = {}
    # 1) Indexar páginas/blocos a partir da root via /blocks/{id}/children
    async def walk(page_id: str, parent_id: Optional[str]):
        # retrieve page para pegar título
        page = await notion.notion_retrieve_page(page_id)
        title = notion.get_page_title(page)
        nodes[page_id] = {"id": page_id, "type": "page", "title": title, "parent_id": parent_id}

        # listar filhos em blocos (pode paginar)
        cursor = None
        while True:
            data = await notion.notion_list_children(page_id, start_cursor=cursor)
            for blk in data.get("results", []):
                typ = blk.get("type")
                if typ == "child_page":
                    cid = blk["id"]
                    # child_page tem seu próprio título
                    ctitle = blk.get("child_page", {}).get("title") or "Untitled"
                    nodes[cid] = {"id": cid, "type": "page", "title": ctitle, "parent_id": page_id}
                    await walk(cid, page_id)
                elif typ == "child_database":
                    did = blk["id"]
                    dtitle = blk.get("child_database", {}).get("title") or "Database"
                    nodes[did] = {"id": did, "type": "database", "title": dtitle, "parent_id": page_id}
            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")

    await walk(root_page_id, None)

    # 2) Salvar
    index = {"created_at": int(time.time()), "root": root_page_id, "nodes": nodes}
    _save(index)
    return index

def get_index(fresh: bool = False) -> Dict[str, Any]:
    data = _load()
    if fresh:
        return data
    if int(time.time()) - data.get("created_at", 0) < TTL_SECONDS:
        return data
    return data  # o caller decide se reindexa

def resolve_by_title_or_path(q: str) -> Optional[Dict[str, Any]]:
    """
    Busca simples por título (case-insensitive). Para 'path' (ex.: "Projetos/PROJ X"),
    você pode enviar 'A/B/C' e faremos uma correspondência progressiva baseada nos pais.
    Aqui, começamos com uma correspondência simples por título.
    """
    data = _load()
    ql = q.strip().lower()
    # 1) match exato por título
    for node in data.get("nodes", {}).values():
        if node.get("title", "").strip().lower() == ql:
            return node
    # 2) se contiver barras, fazer match por partes (simples)
    parts = [p.strip().lower() for p in q.split("/") if p.strip()]
    if parts:
        nodes = data.get("nodes", {})
        # procurar bottom name
        bottom = parts[-1]
        candidates = [n for n in nodes.values() if n.get("title","").strip().lower() == bottom]
        # opcional: checar cadeia de parents
        for cand in candidates:
            ok = True
            pid = cand.get("parent_id")
            for prev in reversed(parts[:-1]):
                found = pid and nodes.get(pid) and nodes[pid]["title"].strip().lower() == prev
                if not found:
                    ok = False
                    break
                pid = nodes[pid].get("parent_id")
            if ok:
                return cand
    return None
