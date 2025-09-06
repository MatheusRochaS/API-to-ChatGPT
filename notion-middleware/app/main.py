from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
import os

from .models import ProjectCreate, TaskCreate, TaskUpdate   # <- NÃO importamos mais DBQuery aqui
from .settings import settings
from .auth import check_auth
from . import notion_client as notion
from . import db_registry
from . import schema_cache
from . import tree_index

# =========================
# MODELOS (LEGADO + NOVOS)
# =========================

class DBMap(BaseModel):
    map: Dict[str, str]  # {"projects":"<id>", "tasks":"<id>", ...}

# --- LEGADO: usado por /db.query (específico projects/tasks) ---
class SortItem(BaseModel):
    property: str
    direction: Optional[str] = "ascending"  # "ascending" | "descending"

class DBQueryLegacy(BaseModel):
    database: Optional[str] = None       # "projects" | "tasks"
    filter: Optional[Dict[str, Any]] = None
    sorts: Optional[List[SortItem]] = None
    page_size: Optional[int] = 50

# --- NOVOS: genéricos para qualquer DB ---
class RowCreate(BaseModel):
    # Passe OU 'database' (chave registrada) OU 'database_id' (ID direto)
    database: Optional[str] = None
    database_id: Optional[str] = None
    # Propriedades já no formato Notion (compatível com /pages)
    properties: Dict[str, Any]
    # Se quiser validar/auto-ajustar nomes via schema cache (0 = off)
    validate_schema_ttl: int = 0

class RowUpdate(BaseModel):
    page_id: str
    properties: Dict[str, Any]
    validate_schema_ttl: int = 0

class DBQueryGeneric(BaseModel):
    database: Optional[str] = None       # chave ("projects","tasks",... configuradas em /config/databases")
    database_id: Optional[str] = None    # ID direto
    filter: Optional[Dict[str, Any]] = None
    sorts: Optional[List[SortItem]] = None
    page_size: Optional[int] = 50

class TreeIndexRequest(BaseModel):
    root_page_id: str

# =========================
# APP
# =========================

app = FastAPI(
    title="ChatGPT ↔ Notion Middleware",
    version="1.1.0",
    description="Middleware para o seu Custom GPT manipular o Notion.",
)

# CORS (para facilitar testes)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # ajuste se quiser restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# HELPERS
# =========================

def build_project_properties(b: ProjectCreate):
    props = {"Name": {"title": [{"text": {"content": b.name}}]}}
    if b.status:   props["Status"]   = {"select": {"name": b.status}}
    if b.area:     props["Area"]     = {"select": {"name": b.area}}
    if b.due:      props["Due"]      = {"date": {"start": b.due}}
    if b.priority: props["Priority"] = {"select": {"name": b.priority}}
    if b.extra:    props.update(b.extra)
    return props

def build_task_properties(b: TaskCreate, project_page_id: Optional[str]):
    props = {"Name": {"title": [{"text": {"content": b.name}}]}}
    if project_page_id:
        props["Project"] = {"relation": [{"id": project_page_id}]}
    if b.status:    props["Status"]   = {"select": {"name": b.status}}
    if b.due:       props["Due"]      = {"date": {"start": b.due}}
    if b.priority:  props["Priority"] = {"select": {"name": b.priority}}
    if b.estimate is not None: props["Estimate"] = {"number": b.estimate}
    if b.notes:     props["Notes"]    = {"rich_text": [{"text": {"content": b.notes}}]}
    if b.extra:     props.update(b.extra)
    return props

def _resolve_db_id(database: Optional[str], database_id: Optional[str]) -> str:
    if database_id:
        return database_id
    if not database:
        raise HTTPException(400, "Informe 'database' (chave) ou 'database_id'.")
    db_id = db_registry.get_db(database)
    if not db_id:
        raise HTTPException(400, f"Database key '{database}' não registrado. Use /config/databases.")
    return db_id

async def _maybe_fix_property_names(db_id: str, props: Dict[str, Any], ttl: int) -> Dict[str, Any]:
    """
    Se ttl > 0, busca o schema (cacheado) e tenta ajustar nomes
    de propriedades (case-insensitive). Máx. 1 GET /databases/{id} por TTL.
    """
    if ttl <= 0:
        return props
    notion_props = await schema_cache.props_by_name(db_id)  # 1 call a cada TTL
    valid_names = {name.lower(): name for name in notion_props.keys()}
    fixed = {}
    for k, v in props.items():
        target = valid_names.get(k.lower())
        fixed[(target or k)] = v
    return fixed

async def find_project_id_by_name(name: str) -> Optional[str]:
    payload = {"filter": {"property": "Name", "title": {"equals": name}}, "page_size": 1}
    data = await notion.notion_query_database(settings.PROJECTS_DB, payload)
    results = data.get("results", [])
    return results[0]["id"] if results else None

# =========================
# ENDPOINTS BÁSICOS
# =========================

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/project.create")
async def project_create(body: ProjectCreate, authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    payload = {"parent": {"database_id": settings.PROJECTS_DB},"properties": build_project_properties(body)}
    try:
        return await notion.notion_create_page(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/task.create")
async def task_create(body: TaskCreate, authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    project_id = body.project_id
    if not project_id and body.project_name:
        project_id = await find_project_id_by_name(body.project_name)
    payload = {"parent": {"database_id": settings.TASKS_DB},"properties": build_task_properties(body, project_id)}
    try:
        return await notion.notion_create_page(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/task.update")
async def task_update(body: TaskUpdate, authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    tmp = TaskCreate(name=body.name or "TMP")
    props = build_task_properties(tmp, project_page_id=None)
    if body.name is None: props.pop("Name", None)
    if body.status:   props["Status"]   = {"select": {"name": body.status}}
    if body.due:      props["Due"]      = {"date": {"start": body.due}}
    if body.priority: props["Priority"] = {"select": {"name": body.priority}}
    if body.notes:    props["Notes"]    = {"rich_text": [{"text": {"content": body.notes}}]}
    if body.extra:    props.update(body.extra)
    try:
        return await notion.notion_update_page(body.task_id, {"properties": props})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================
# CONFIG DB KEYS
# =========================

@app.post("/config/databases")
async def config_databases(body: DBMap, authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    for k, v in body.map.items():
        db_registry.set_db(k, v)
    return {"ok": True, "registered": db_registry.all_dbs()}

@app.get("/config/databases")
async def list_databases(authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    return db_registry.all_dbs()

# =========================
# LEGADO: /db.query (projects|tasks)
# =========================

@app.post("/db.query")
async def db_query_legacy(body: DBQueryLegacy, authorization: Optional[str] = Header(default=None)):
    """
    Mantido por compatibilidade. Usa settings.PROJECTS_DB/TASKS_DB conforme 'database'.
    """
    check_auth(authorization)
    if body.database == "projects":
        db = settings.PROJECTS_DB
    elif body.database == "tasks":
        db = settings.TASKS_DB
    else:
        raise HTTPException(400, "Use 'database' como 'projects' ou 'tasks'. Para geral, chame /db.query.generic.")

    payload: Dict[str, Any] = {}
    if body.filter is not None:
        payload["filter"] = body.filter
    if body.sorts is not None:
        payload["sorts"] = [{"property": s.property, "direction": s.direction or "ascending"} for s in body.sorts]
    payload["page_size"] = body.page_size or 50

    try:
        return await notion.notion_query_database(db, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================
# GENÉRICOS (qualquer DB)
# =========================

@app.post("/row.create")
async def row_create(body: RowCreate, authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    db_id = _resolve_db_id(body.database, body.database_id)
    props = await _maybe_fix_property_names(db_id, body.properties, body.validate_schema_ttl)
    payload = {"parent": {"database_id": db_id}, "properties": props}
    try:
        return await notion.notion_create_page(payload)
    except Exception as e:
        if body.validate_schema_ttl <= 0:
            try:
                props2 = await _maybe_fix_property_names(db_id, body.properties, ttl=300)
                payload["properties"] = props2
                return await notion.notion_create_page(payload)
            except Exception as e2:
                raise HTTPException(status_code=500, detail=str(e2))
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/row.update")
async def row_update(body: RowUpdate, authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    try:
        return await notion.notion_update_page(body.page_id, {"properties": body.properties})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/db.query.generic")
async def db_query_generic(body: DBQueryGeneric, authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    db_id = _resolve_db_id(body.database, body.database_id)
    payload: Dict[str, Any] = {}
    if body.filter is not None:
        payload["filter"] = body.filter
    if body.sorts is not None:
        payload["sorts"] = [{"property": s.property, "direction": s.direction or "ascending"} for s in body.sorts]
    payload["page_size"] = body.page_size or 50
    try:
        return await notion.notion_query_database(db_id, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================
# ÁRVORE / ÍNDICE
# =========================

@app.post("/tree.index")
async def tree_index_build(body: TreeIndexRequest, authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    idx = await tree_index.build_index(body.root_page_id)
    return {"ok": True, "nodes": len(idx.get("nodes", {})), "created_at": idx["created_at"]}

@app.post("/tree.index.bootstrap")
async def tree_index_bootstrap(authorization: Optional[str] = Header(default=None)):
    """
    Indexa as raízes definidas nos Secrets:
      - MAIN_HOME_PAGE_ID
      - TEAMSPACE_HOME_PAGE_ID
    Faz merge das duas no índice único.
    """
    check_auth(authorization)
    main_id = os.getenv("MAIN_HOME_PAGE_ID")
    team_id = os.getenv("TEAMSPACE_HOME_PAGE_ID")
    if not main_id and not team_id:
        raise HTTPException(400, "Defina MAIN_HOME_PAGE_ID e/ou TEAMSPACE_HOME_PAGE_ID nos Secrets.")

    result = {"indexed": [], "nodes_total": 0}
    if main_id:
        idx = await tree_index.build_index_merge(main_id)
        result["indexed"].append(main_id)
        result["nodes_total"] = len(idx.get("nodes", {}))
    if team_id:
        idx = await tree_index.build_index_merge(team_id)
        if team_id not in result["indexed"]:
            result["indexed"].append(team_id)
        result["nodes_total"] = len(idx.get("nodes", {}))
    return result

@app.get("/tree.lookup")
async def tree_lookup(q: str = Query(..., description="title or path like A/B/C"),
                      authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    node = tree_index.resolve_by_title_or_path(q)
    if not node:
        raise HTTPException(404, f"Not found in index: {q}. Reindex if structure changed.")
    return node

@app.get("/tree.index.info")
async def tree_index_info(authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    data = tree_index.get_index()
    return {
        "created_at": data.get("created_at"),
        "roots": data.get("roots", []),
        "nodes": len(data.get("nodes", {}))
    }
