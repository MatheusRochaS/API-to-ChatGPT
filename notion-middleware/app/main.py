from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
from .models import ProjectCreate, TaskCreate, TaskUpdate, DBQuery
from .settings import settings
from .auth import check_auth
from . import notion_client as notion

app = FastAPI(
    title="ChatGPT ↔ Notion Middleware",
    version="1.0.0",
    description="Middleware para o seu Custom GPT manipular o Notion.",
)

# CORS (caso queira testar via browser/Postman sem bloqueios)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ajuste se quiser restringir
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def build_project_properties(b: ProjectCreate):
    props = {"Name": {"title": [{"text": {"content": b.name}}]}}
    if b.status:   props["Status"] = {"select": {"name": b.status}}
    if b.area:     props["Area"]   = {"select": {"name": b.area}}
    if b.due:      props["Due"]    = {"date": {"start": b.due}}
    if b.priority: props["Priority"]= {"select": {"name": b.priority}}
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
    if b.notes:     props["Notes"] = {"rich_text": [{"text": {"content": b.notes}}]}
    if b.extra:     props.update(b.extra)
    return props

async def find_project_id_by_name(name: str) -> Optional[str]:
    payload = {"filter": {"property": "Name", "title": {"equals": name}}, "page_size": 1}
    data = await notion.notion_query_database(settings.PROJECTS_DB, payload)
    results = data.get("results", [])
    return results[0]["id"] if results else None

@app.get("/health")
async def health():
    return {"ok": True}

@app.post("/project.create")
async def project_create(body: ProjectCreate, authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    payload = {
        "parent": {"database_id": settings.PROJECTS_DB},
        "properties": build_project_properties(body)
    }
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
    payload = {
        "parent": {"database_id": settings.TASKS_DB},
        "properties": build_task_properties(body, project_id)
    }
    try:
        return await notion.notion_create_page(payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.patch("/task.update")
async def task_update(body: TaskUpdate, authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    # Monta somente os campos enviados
    tmp = TaskCreate(name=body.name or "TMP")
    props = build_task_properties(tmp, project_page_id=None)
    if body.name is None: props.pop("Name", None)
    if body.status:    props["Status"]   = {"select": {"name": body.status}}
    if body.due:       props["Due"]      = {"date": {"start": body.due}}
    if body.priority:  props["Priority"] = {"select": {"name": body.priority}}
    if body.notes:     props["Notes"]    = {"rich_text": [{"text": {"content": body.notes}}]}
    if body.extra:     props.update(body.extra)
    try:
        return await notion.notion_update_page(body.task_id, {"properties": props})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/db.query")
async def db_query(body: DBQuery, authorization: Optional[str] = Header(default=None)):
    check_auth(authorization)
    db = settings.PROJECTS_DB if body.database == "projects" else settings.TASKS_DB
    payload = {}
    if body.filter is not None: payload["filter"] = body.filter
    if body.sorts is not None:
        payload["sorts"] = [{"property": s.property, "direction": s.direction} for s in body.sorts]
    payload["page_size"] = body.page_size or 50
    try:
        return await notion.notion_query_database(db, payload)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
