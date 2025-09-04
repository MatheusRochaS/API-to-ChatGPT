from pydantic import BaseModel
from typing import Optional, Literal, Any, Dict, List

class ProjectCreate(BaseModel):
    name: str
    status: Optional[Literal["Planning","In progress","Paused","Done"]] = "Planning"
    area: Optional[Literal["Work","Study","Personal","Business"]] = None
    due: Optional[str] = None
    priority: Optional[Literal["High","Medium","Low"]] = None
    extra: Optional[Dict[str, Any]] = None

class TaskCreate(BaseModel):
    name: str
    project_name: Optional[str] = None
    project_id: Optional[str] = None
    status: Optional[Literal["Todo","Doing","Done"]] = "Todo"
    due: Optional[str] = None
    priority: Optional[Literal["High","Medium","Low"]] = None
    estimate: Optional[float] = None
    notes: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

class TaskUpdate(BaseModel):
    task_id: str
    name: Optional[str] = None
    status: Optional[Literal["Todo","Doing","Done"]] = None
    due: Optional[str] = None
    priority: Optional[Literal["High","Medium","Low"]] = None
    notes: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

class SortItem(BaseModel):
    property: str
    direction: Literal["ascending","descending"] = "ascending"

class DBQuery(BaseModel):
    database: Literal["projects","tasks"]
    filter: Optional[Dict[str, Any]] = None
    sorts: Optional[List[SortItem]] = None
    page_size: Optional[int] = 50
