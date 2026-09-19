import logging

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend import db
from backend.models import ResearchRequest, ResearchResponse
from backend.graph import run_research, resume_research

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cody-researcher")

app = FastAPI(title="Cody Researcher")


@app.on_event("startup")
def startup():
    db.init_db()


@app.post("/api/research", response_model=ResearchResponse)
async def start_research(req: ResearchRequest, background_tasks: BackgroundTasks):
    if not req.target.strip() or not req.task.strip():
        raise HTTPException(400, "target and task are both required")
    run_id = db.create_run(req.target.strip(), req.task.strip())

    async def _run():
        try:
            await run_research(run_id, req.target.strip(), req.task.strip())
        except Exception as e:
            logger.exception("run %s crashed", run_id)
            db.update_run(run_id, status="failed", error=str(e))
            db.log_event(run_id, "run_crashed", {"error": str(e)})

    background_tasks.add_task(_run)
    return ResearchResponse(run_id=run_id, status="pending")


@app.post("/api/research/{run_id}/resume", response_model=ResearchResponse)
async def resume(run_id: str, background_tasks: BackgroundTasks):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")

    async def _resume():
        try:
            await resume_research(run_id)
        except Exception as e:
            logger.exception("resume %s crashed", run_id)
            db.update_run(run_id, status="failed", error=str(e))

    background_tasks.add_task(_resume)
    return ResearchResponse(run_id=run_id, status="resuming")


@app.get("/api/research/{run_id}")
def get_status(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    citations = db.get_citations(run_id) if run["status"] in (
        "completed", "completed_with_failures", "partial") else []
    return {
        "run": run,
        "citations": citations,
        "pages": db.get_pages(run_id),
    }


@app.get("/api/research/{run_id}/events")
def get_events(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "run not found")
    return {"events": db.get_events(run_id)}


@app.get("/api/research")
def list_runs():
    with db.get_conn() as conn:
        rows = conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 50").fetchall()
        return {"runs": [dict(r) for r in rows]}


app.mount("/assets", StaticFiles(directory="frontend/dist/assets"), name="assets")


@app.get("/")
def index():
    return FileResponse("frontend/dist/index.html")
