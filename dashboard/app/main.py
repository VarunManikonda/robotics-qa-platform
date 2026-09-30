"""Run-history API for robot QA results.

Endpoints
---------
POST /runs            record a run (from a robot node, CI job, or script)
GET  /runs            progressive filtering with keyset pagination
GET  /runs/{id}       one run
GET  /stats           pass/fail/warn counts per project
GET  /health          liveness probe
GET  /                small HTML dashboard

Progressive filtering means every filter is optional and they combine, so a
user can narrow a large history step by step (project -> status -> text ->
date range) and page through it without offset scans.
"""

from __future__ import annotations

import json
import os
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import db

DB_PATH = os.environ.get("QA_DB_PATH", "qa_runs.sqlite3")

Status = Literal["pass", "fail", "warn"]


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

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML

    return app


def _escape_like(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


_INDEX_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Robotics QA Dashboard</title>
<style>
 body{font:14px system-ui,sans-serif;margin:0;padding:16px;color:#1a1a1a;background:#fafafa}
 h1{font-size:18px;margin:0 0 12px}
 .bar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px}
 input,select,button{padding:6px 8px;font:inherit}
 table{border-collapse:collapse;width:100%;background:#fff}
 th,td{border-bottom:1px solid #e5e5e5;padding:6px 8px;text-align:left}
 .pass{color:#1a7f37}.fail{color:#cf222e}.warn{color:#9a6700}
 #stats span{margin-right:16px}
</style></head><body>
<h1>Robotics QA Dashboard</h1>
<div id="stats"></div>
<div class="bar">
 <select id="project"><option value="">all projects</option>
  <option>cobot_qa</option><option>amr_health</option></select>
 <select id="status"><option value="">any status</option>
  <option>pass</option><option>fail</option><option>warn</option></select>
 <input id="q" placeholder="search name or message">
 <button onclick="load(true)">Apply</button>
 <button id="more" onclick="load(false)" hidden>Load more</button>
</div>
<table><thead><tr><th>#</th><th>time</th><th>project</th><th>run</th><th>status</th>
<th>metric</th><th>message</th></tr></thead><tbody id="rows"></tbody></table>
<script>
let cursor=null;
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
async function load(reset){
  if(reset){cursor=null;document.getElementById('rows').innerHTML=''}
  const p=new URLSearchParams({limit:20});
  for(const k of ['project','status','q']){const v=document.getElementById(k).value;if(v)p.set(k,v)}
  if(cursor)p.set('cursor',cursor);
  const r=await (await fetch('/runs?'+p)).json();
  const tb=document.getElementById('rows');
  for(const i of r.items){tb.insertAdjacentHTML('beforeend',
   `<tr><td>${i.id}</td><td>${esc(i.created_at)}</td><td>${esc(i.project)}</td>
    <td>${esc(i.name)}</td><td class="${i.status}">${i.status}</td>
    <td>${i.metric??''}</td><td>${esc(i.message)}</td></tr>`)}
  cursor=r.next_cursor;document.getElementById('more').hidden=!cursor;
  const s=await (await fetch('/stats')).json();
  document.getElementById('stats').innerHTML=Object.entries(s).map(([k,v])=>
   `<span><b>${esc(k)}</b>: <span class="pass">${v.pass} pass</span> /
    <span class="fail">${v.fail} fail</span> / <span class="warn">${v.warn} warn</span></span>`).join('');
}
load(true);
</script></body></html>
"""

