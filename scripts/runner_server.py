from fastapi import FastAPI
from pydantic import BaseModel
import os, sys, json, uuid, subprocess, threading, time
from typing import Optional, Dict, Any, Union

app = FastAPI()

class Job(BaseModel):
    prompt: str
    storyId: str
    scene: int
    rowId: Optional[Union[str, int]] = None
    webhookUrl: Optional[str] = None

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

PYTHON = os.environ.get("SORA_PYTHON", sys.executable)
SCRIPT = os.environ.get("SORA_SCRIPT", os.path.join(BASE_DIR, "scripts", "sora_autopilot_selenium.py"))

# in-memory job store (simple + works)
JOBS: Dict[str, Dict[str, Any]] = {}

def post_webhook(url: str, payload: dict, job_id: str | None = None):
    """Send POST to n8n webhook and log response/errors."""
    try:
        import urllib.request

        clean_url = (url or "").strip()
        if not clean_url:
            print("[webhook] empty url, skipping")
            return

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            clean_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            print(f"[webhook] POST {clean_url} -> {resp.status} {resp.reason} | {body[:300]}")

            if job_id:
                JOBS[job_id]["webhook"] = {"ok": True, "status": resp.status, "body": body[:2000]}

    except Exception as e:
        print(f"[webhook] FAILED POST {url}: {repr(e)}")
        if job_id:
            JOBS[job_id]["webhook"] = {"ok": False, "error": repr(e)}


def run_job_background(job_id: str, job: Job):
    story_id = job.storyId.strip()
    scene = int(job.scene)
    row_id = str(job.rowId).strip() if job.rowId is not None else ""
    prompt = (job.prompt or "").strip()

    JOBS[job_id]["status"] = "running"
    JOBS[job_id]["started_at"] = time.time()

    cmd = [PYTHON, SCRIPT, prompt, row_id, story_id, str(scene)]

    proc = subprocess.run(cmd, capture_output=True, text=True, env=os.environ.copy())

    out = proc.stdout or ""
    err = proc.stderr or ""

    # Try to parse JSON marker line from selenium output (we will add it in the script)
    marker = "__RESULT__="
    parsed = None
    idx = out.rfind(marker)
    if idx != -1:
        raw = out[idx + len(marker):].strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = {"parseError": "failed to parse __RESULT__", "raw": raw}

    result = {
        "ok": proc.returncode == 0,
        "exitCode": proc.returncode,
        "jobId": job_id,
        "rowId": row_id,
        "storyId": story_id,
        "scene": scene,
        "stdout": out[-8000:],
        "stderr": err[-8000:],
        "result": parsed or {},
    }

    JOBS[job_id]["status"] = "done" if result["ok"] else "error"
    JOBS[job_id]["finished_at"] = time.time()
    JOBS[job_id]["result"] = result

    # webhook callback if provided
    if job.webhookUrl:
        callback_payload = {
            "jobId": job_id,
            "status": JOBS[job_id]["status"],
            **result,
        }
        post_webhook(job.webhookUrl, callback_payload, job_id=job_id)

@app.post("/run_async")
def run_async(job: Job):
    prompt = (job.prompt or "").strip()
    story_id = (job.storyId or "").strip()
    scene = int(job.scene)

    if not prompt:
        return {"ok": False, "error": "prompt is empty"}
    if not story_id:
        return {"ok": False, "error": "storyId is empty"}
    if scene <= 0:
        return {"ok": False, "error": "scene must be >= 1"}

    job_id = uuid.uuid4().hex

    JOBS[job_id] = {
        "status": "queued",
        "job": job.model_dump(),
        "created_at": time.time(),
        "result": None,
    }

    t = threading.Thread(target=run_job_background, args=(job_id, job), daemon=True)
    t.start()

    # IMPORTANT: return immediately so n8n never times out
    return {
        "ok": True,
        "jobId": job_id,
        "status": "queued",
        "storyId": story_id,
        "scene": scene,
        "rowId": (job.rowId or ""),
        "message": "Job accepted. Will callback webhookUrl when done (if provided).",
    }

@app.get("/status/{job_id}")
def status(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        return {"ok": False, "error": "job not found", "jobId": job_id}
    # return lightweight
    return {
        "ok": True,
        "jobId": job_id,
        "status": j["status"],
        "created_at": j.get("created_at"),
        "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"),
        "result": j.get("result"),
    }
