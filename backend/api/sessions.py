from __future__ import annotations

from datetime import datetime
from typing import Generator, List, Optional
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from backend.models import sessions as session_store

router = APIRouter(prefix="/sessions", tags=["sessions"])


def db_conn(request: Request) -> Generator[psycopg.Connection, None, None]:
    dsn = getattr(request.app.state, "dsn", None)
    if not dsn:
        raise HTTPException(status_code=500, detail="Database DSN not configured")
    conn = psycopg.connect(dsn)
    try:
        yield conn
    finally:
        conn.close()


class SessionSummary(BaseModel):
    id: UUID
    title: Optional[str] = Field(None, description="Session title")
    updated_at: datetime
    pinned: bool
    archived: bool
    message_count: int


class SessionMessage(BaseModel):
    id: UUID
    role: str
    content: Optional[str]
    create_time: Optional[datetime]
    idx: int
    conversation_id: UUID


class SessionDetail(BaseModel):
    id: UUID
    title: Optional[str] = Field(None, description="Session title")
    created_at: datetime
    updated_at: datetime
    pinned: bool
    archived: bool
    conversation_id: UUID
    message_count: int
    messages: List[SessionMessage]


class SessionCreateRequest(BaseModel):
    title: Optional[str] = Field(None, description="Optional session title")


class SessionPatchRequest(BaseModel):
    title: Optional[str] = Field(None, description="Optional new title")
    pinned: Optional[bool] = Field(None, description="Pin or unpin the session")
    archived: Optional[bool] = Field(None, description="Archive/unarchive the session")


def _to_detail(data: dict) -> SessionDetail:
    messages = [
        SessionMessage(
            id=msg["id"],
            role=msg["role"],
            content=msg.get("content"),
            create_time=msg.get("create_time"),
            idx=msg["idx"],
            conversation_id=msg["conversation_id"],
        )
        for msg in data.get("messages", [])
    ]
    return SessionDetail(
        id=data["id"],
        title=data.get("title"),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        pinned=data["pinned"],
        archived=data["archived"],
        conversation_id=data["conversation_id"],
        message_count=data.get("message_count", len(messages)),
        messages=messages,
    )


@router.get("", response_model=List[SessionSummary])
def list_sessions(
    include_archived: bool = Query(False, description="Include archived sessions in the list"),
    conn: psycopg.Connection = Depends(db_conn),
) -> List[SessionSummary]:
    rows = session_store.list_sessions(conn, include_archived=include_archived)
    return [SessionSummary(**row) for row in rows]


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: UUID,
    include_archived: bool = Query(False, description="Allow fetching archived sessions"),
    conn: psycopg.Connection = Depends(db_conn),
) -> SessionDetail:
    try:
        data = session_store.fetch_session_details(conn, session_id, include_archived=include_archived)
    except session_store.SessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_detail(data)


@router.post("", response_model=SessionDetail, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreateRequest,
    conn: psycopg.Connection = Depends(db_conn),
) -> SessionDetail:
    session_id, conversation_id = session_store.create_session(conn, title=payload.title)
    conn.commit()
    data = session_store.fetch_session_details(conn, session_id, include_archived=True)
    data["conversation_id"] = conversation_id
    return _to_detail(data)


@router.patch("/{session_id}", response_model=SessionDetail)
def patch_session(
    session_id: UUID,
    payload: SessionPatchRequest,
    conn: psycopg.Connection = Depends(db_conn),
) -> SessionDetail:
    try:
        updated = session_store.patch_session(
            conn,
            session_id,
            title=payload.title,
            pinned=payload.pinned,
            archived=payload.archived,
        )
        conn.commit()
    except session_store.SessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_detail(updated)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: UUID,
    conn: psycopg.Connection = Depends(db_conn),
) -> None:
    try:
        session_store.soft_archive_session(conn, session_id)
        conn.commit()
    except session_store.SessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

