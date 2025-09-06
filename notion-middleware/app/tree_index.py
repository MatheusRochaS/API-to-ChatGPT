# app/tree_index.py
import os, json, time
from typing import Dict, Any, Optional, List
from . import notion_client as notion

INDEX_PATH = os.getenv("TREE_INDEX_PATH", "/tmp/page_index.json")
# 7 dias por padrão (pode sobrescrever em Secrets como TREE_INDEX_TTL=604800)
TTL_SECONDS = int(os.getenv("TREE_INDEX_TTL", "604800"))

# --------------- utilidades de arquivo -----------------

def _load() -> Dict[str, Any]:
    """
    Carrega o índice do disco e aplica retrocompatibilidade:
    - se existir "root", converte para "roots": [root]
    - garante chaves "roots" e "nodes"
    """
    if not os.path.exists(INDEX_PATH):
        return {"created_at": 0, "roots": [], "nodes": {}}

    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # retrocompat: root -> roots
    if "root" in data and "roots" not in data:
        data["roots"] = [data["root"]]
        data.pop("root", None)

    if "roots" not in data:
        data["roots"] = []
    if "nodes" not in data:
        data["nodes"] = {}

    return data


def _save(data: Dict[str, Any]):
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# --------------- coleta (walk) -----------------

async def _walk_and_collect(root_page_id: str) -> Dict[str, Any]:
    """
    Retorna apenas os nodes desta raiz (não salva).
    nodes[id] = { id, type: "page"|"database", title, parent_id }
    Varre recursivamente:
      - páginas
      - qualquer bloco que tenha filhos (has_children)
      - child_page, child_database e link_to_page
    """
    nodes: Dict[str, Any] = {}

    async def walk(page_id: str, parent_id: Optional[str]):
        # 1) registra a própria página
        page = await notion.notion_retrieve_page(page_id)
        title = notion.get_page_title(page)
        nodes[page_id] = {
            "id": page_id,
            "type": "page",
            "title": title,
            "parent_id": parent_id,
        }

        # 2) processa os filhos de um BLOCO genérico (serve para nested blocks)
        async def walk_block_children(block_id: str, parent_of_found: str):
            cursor = None
            while True:
                data = await notion.notion_list_children(block_id, start_cursor=cursor)
                for blk in data.get("results", []):
                    typ = blk.get("type")

                    # a) páginas filhas "reais"
                    if typ == "child_page":
                        cid = blk["id"]
                        ctitle = blk.get("child_page", {}).get("title") or "Untitled"
                        nodes[cid] = {
                            "id": cid,
                            "type": "page",
                            "title": ctitle,
                            "parent_id": parent_of_found,
                        }
                        await walk(cid, parent_of_found)

                    # b) bancos embutidos/filhos
                    elif typ == "child_database":
                        did = blk["id"]
                        dtitle = blk.get("child_database", {}).get("title") or "Database"
                        nodes[did] = {
                            "id": did,
                            "type": "database",
                            "title": dtitle,
                            "parent_id": parent_of_found,
                        }

                    # c) links para página ou database
                    elif typ == "link_to_page":
                        link = blk.get("link_to_page", {}) or {}
                        # link para PÁGINA
                        if link.get("page_id"):
                            lpid = link["page_id"]
                            ltitle = "Untitled"
                            try:
                                p = await notion.notion_retrieve_page(lpid)
                                ltitle = notion.get_page_title(p) or "Untitled"
                            except Exception:
                                pass
                            nodes[lpid] = {
                                "id": lpid,
                                "type": "page",
                                "title": ltitle,
                                "parent_id": parent_of_found,
                            }
                            # segue o link (assim indexamos a árvore real)
                            await walk(lpid, parent_of_found)

                        # link para DATABASE
                        elif link.get("database_id"):
                            ldid = link["database_id"]
                            ltitle = "Database"
                            try:
                                if hasattr(notion, "notion_retrieve_database"):
                                    meta = await notion.notion_retrieve_database(ldid)
                                    if isinstance(meta, dict):
                                        tarr = meta.get("title", [])
                                        if isinstance(tarr, list) and tarr:
                                            ltitle = "".join(
                                                [t.get("plain_text", "") for t in tarr]
                                            ) or "Database"
                            except Exception:
                                pass
                            nodes[ldid] = {
                                "id": ldid,
                                "type": "database",
                                "title": ltitle,
                                "parent_id": parent_of_found,
                            }

                    # d) QUALQUER bloco que tenha filhos — precisamos entrar!
                    if blk.get("has_children"):
                        # alguns blocos “container” (toggle, synced_block, column, callout, etc.) guardam páginas/databases lá dentro
                        await walk_block_children(blk["id"], parent_of_found)

                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")

        # 3) varre os filhos da PÁGINA (que também é um "bloco raiz")
        await walk_block_children(page_id, page_id)

    await walk(root_page_id, None)
    return nodes

# --------------- APIs de índice -----------------

async def build_index(root_page_id: str) -> Dict[str, Any]:
    """
    (modo single-root) Recria o índice APENAS com esta raiz.
    Mantido por retrocompatibilidade.
    """
    nodes = await _walk_and_collect(root_page_id)
    index = {
        "created_at": int(time.time()),
        "roots": [root_page_id],
        "nodes": nodes,
    }
    _save(index)
    return index


async def build_index_merge(root_page_id: str) -> Dict[str, Any]:
    """
    (modo multi-root) Mescla os nós desta raiz ao índice existente.
    Se a raiz ainda não estiver em 'roots', adiciona.
    """
    existing = _load()
    new_nodes = await _walk_and_collect(root_page_id)

    # merge leve — sobrescreve nós com mesmo id (última versão vence)
    existing["nodes"].update(new_nodes)

    if root_page_id not in existing["roots"]:
        existing["roots"].append(root_page_id)

    existing["created_at"] = int(time.time())
    _save(existing)
    return existing


def get_index() -> Dict[str, Any]:
    """
    Retorna o índice atual do disco (sem forçar rebuild).
    TTL é usado por quem chama para decidir se reindexa.
    """
    return _load()


def resolve_by_title_or_path(q: str) -> Optional[Dict[str, Any]]:
    """
    Busca por título (case-insensitive) ou por caminho "A/B/C".
    Retorna o primeiro match que satisfaz a cadeia de pais (se houver).
    """
    data = _load()
    nodes = data.get("nodes", {})

    ql = q.strip().lower()
    # 1) match exato por título
    for node in nodes.values():
        if node.get("title", "").strip().lower() == ql:
            return node

    # 2) caminho A/B/C
    parts = [p.strip().lower() for p in q.split("/") if p.strip()]
    if parts:
        bottom = parts[-1]
        candidates = [n for n in nodes.values()
                      if n.get("title", "").strip().lower() == bottom]
        for cand in candidates:
            ok = True
            pid = cand.get("parent_id")
            # verifica pais na ordem reversa
            for prev in reversed(parts[:-1]):
                if not pid or pid not in nodes:
                    ok = False
                    break
                parent = nodes[pid]
                if parent.get("title", "").strip().lower() != prev:
                    ok = False
                    break
                pid = parent.get("parent_id")
            if ok:
                return cand

    return None


# --------------- Busca leve (substring) -----------------

def search(q: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Retorna até `limit` nós cujo título contém o termo (case-insensitive).
    """
    data = _load()
    nodes = data.get("nodes", {})
    ql = (q or "").strip().lower()
    if not ql:
        return []

    matches = []
    for n in nodes.values():
        title = (n.get("title") or "").strip()
        if ql in title.lower():
            matches.append(n)

    # ordena por: começa com termo > contém termo
    matches.sort(key=lambda n: (
        0 if (n.get("title","").lower().startswith(ql)) else 1,
        n.get("title","").lower()
    ))
    return matches[: max(1, int(limit))]
