"""Run-history API for robot QA results.

Endpoints
---------
POST /runs            record a run (from a robot node, CI job, or script)
GET  /runs            progressive filtering with keyset pagination
GET  /runs/{id}       one run
GET  /stats           pass/fail/warn counts per project
GET  /summary         plain-language status, things needing attention, recent parts
GET  /health          liveness probe
GET  /                dashboard page for non-technical readers

Progressive filtering means every filter is optional and they combine, so a
user can narrow a large history step by step (project -> status -> text ->
date range) and page through it without offset scans.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import db
from .page import INDEX_HTML
from .summary import summarise

DB_PATH = os.environ.get("QA_DB_PATH", "qa_runs.sqlite3")

Status = Literal["pass", "fail", "warn"]
SUMMARY_ROW_CAP = 5000


class RunIn(BaseModel):
    project: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    status: Status
    metric: Optional[float] = None
    message: str = Field(default="", max_length=2000)
    payload: dict = Field(default_factory=dict)


class RunOut(RunIn):
    id: int
    created_at: str


class Page(BaseModel):
    items: list[RunOut]
    next_cursor: Optional[int] = None


def create_app(db_path: Optional[str] = None) -> FastAPI:
    conn = db.connect(db_path or DB_PATH)
    app = FastAPI(title="Robotics QA Dashboard", version="0.1.0")

    @app.get("/health")
    def health() -> dict:
        return {"ok": True}

    @app.post("/runs", response_model=RunOut, status_code=201)
    def create_run(run: RunIn) -> dict:
        with db.cursor(conn) as cur:
            cur.execute(
                "INSERT INTO runs (project, name, status, metric, message, payload)"
                " VALUES (?,?,?,?,?,?)",
                (
                    run.project,
                    run.name,
                    run.status,
                    run.metric,
                    run.message,
                    json.dumps(run.payload),
                ),
            )
            new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM runs WHERE id=?", (new_id,)).fetchone()
        return db.row_to_dict(row)

    @app.get("/runs", response_model=Page)
    def list_runs(
        project: Optional[str] = None,
        status: Optional[Status] = None,
        q: Optional[str] = Query(None, description="text search in name/message"),
        since: Optional[str] = Query(None, description="ISO timestamp, inclusive"),
        until: Optional[str] = Query(None, description="ISO timestamp, inclusive"),
        problems: bool = Query(False, description="only warnings and real problems, not rejected parts"),
        min_metric: Optional[float] = None,
        max_metric: Optional[float] = None,
        limit: int = Query(20, ge=1, le=200),
        cursor: Optional[int] = Query(None, description="return runs with id < cursor"),
    ) -> Page:
        where: list[str] = []
        args: list = []
        if project:
            where.append("project = ?")
            args.append(project)
        if status:
            where.append("status = ?")
            args.append(status)
        if problems:
            # a part correctly rejected to the reject bin is 'fail' but is normal operation
            where.append(
                "(status = 'warn' OR (status = 'fail' AND NOT (project = 'cobot_qa' AND name LIKE 'part:%')))"
            )
        if q:
            like = f"%{_escape_like(q)}%"
            where.append("(name LIKE ? ESCAPE '\\' OR message LIKE ? ESCAPE '\\')")
            args += [like, like]
        if since:
            where.append("created_at >= ?")
            args.append(since)
        if until:
            where.append("created_at <= ?")
            args.append(until)
        if min_metric is not None:
            where.append("metric >= ?")
            args.append(min_metric)
        if max_metric is not None:
            where.append("metric <= ?")
            args.append(max_metric)
        if cursor is not None:
            where.append("id < ?")
            args.append(cursor)

        sql = "SELECT * FROM runs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC LIMIT ?"
        # fetch one extra row to know whether another page exists
        rows = conn.execute(sql, args + [limit + 1]).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [db.row_to_dict(r) for r in rows]
        return Page(items=items, next_cursor=items[-1]["id"] if has_more else None)

    @app.get("/runs/{run_id}", response_model=RunOut)
    def get_run(run_id: int) -> dict:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="run not found")
        return db.row_to_dict(row)

    @app.get("/stats")
    def stats() -> dict:
        rows = conn.execute(
            "SELECT project, status, COUNT(*) AS n FROM runs GROUP BY project, status"
        ).fetchall()
        out: dict[str, dict[str, int]] = {}
        for r in rows:
            out.setdefault(r["project"], {"pass": 0, "fail": 0, "warn": 0})[
                r["status"]
            ] = r["n"]
        return out

    @app.get("/summary")
    def summary(hours: int = Query(24, ge=1, le=24 * 30)) -> dict:
        since = _iso(datetime.now(timezone.utc) - timedelta(hours=hours))
        rows = conn.execute(
            "SELECT * FROM (SELECT * FROM runs WHERE created_at >= ? ORDER BY id DESC LIMIT ?)"
            " ORDER BY id ASC",
            (since, SUMMARY_ROW_CAP),
        ).fetchall()
        return summarise([db.row_to_dict(r) for r in rows], hours=hours)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return INDEX_HTML

    return app


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _iso(dt: datetime) -> str:
    """Same text format SQLite writes into created_at, so string comparison orders correctly."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
