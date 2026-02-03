from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import os, sys, json, uuid, subprocess, threading, time, shutil
from typing import Optional, Dict, Any, Union, List
from pathlib import Path

app = FastAPI()

BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

BASE_DIR = os.path.dirname(__file__)
PYTHON = os.environ.get("SORA_PYTHON", sys.executable)

# --- Scripts you run ---
SORA_SCRIPT = os.environ.get(
    "SORA_SCRIPT",
    os.path.join(BASE_DIR, "scripts", "sora_autopilot_selenium.py")
)

VEO_SCRIPT = os.environ.get(
    "VEO_SCRIPT",
    os.path.join(BASE_DIR, "scripts", "veo_autopilot.py")
)

MEDIA_SCRIPT = os.environ.get(
    "SORA_MEDIA_SCRIPT",
    os.path.join(BASE_DIR, "scripts", "media_pipeline.py")
)

YOUTUBE_SCRIPT = os.environ.get(
    "YOUTUBE_SCRIPT",
    os.path.join(BASE_DIR, "scripts", "youtube_upload_autopilot.py")
)

# --- In-memory job stores ---
JOBS: Dict[str, Dict[str, Any]] = {}        # for /run_async
MEDIA_JOBS: Dict[str, Dict[str, Any]] = {}  # for /process
YOUTUBE_JOBS: Dict[str, Dict[str, Any]] = {}  # for /upload_youtube


# -----------------------
# Shared: webhook POST helper
# -----------------------
def post_webhook(url: str, payload: dict, job_id: str | None = None, store: Dict[str, Any] | None = None):
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

            if job_id and store is not None:
                store[job_id]["webhook"] = {"ok": True, "status": resp.status, "body": body[:2000]}

    except Exception as e:
        print(f"[webhook] FAILED POST {url}: {repr(e)}")
        if job_id and store is not None:
            store[job_id]["webhook"] = {"ok": False, "error": repr(e)}


def parse_marker(stdout: str, marker="__RESULT__=") -> dict:
    idx = (stdout or "").rfind(marker)
    if idx == -1:
        return {}
    raw = stdout[idx + len(marker):].strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"parseError": "failed to parse __RESULT__", "raw": raw[:4000]}


# ============================================================
# 1) SORA route: /run_async  (generate + download)
# ============================================================
class Job(BaseModel):
    prompt: str
    storyId: str
    scene: int
    rowId: Optional[Union[str, int]] = None
    webhookUrl: Optional[str] = None
    chromeProfile: Optional[str] = None
    frame_1: Optional[str] = None
    frame_2: Optional[str] = None
    project_url: Optional[str] = None  


def run_job_background(job_id: str, job: Job):
    try:
        story_id = job.storyId.strip()
        scene = int(job.scene)
        row_id = str(job.rowId).strip() if job.rowId is not None else ""
        prompt = (job.prompt or "").strip()
        chrome_profile = (job.chromeProfile or "").strip()
        frame_1 = (job.frame_1 or "").strip()
        frame_2 = (job.frame_2 or "").strip()
        project_url = (job.project_url or "").strip()


        JOBS[job_id]["status"] = "running"
        JOBS[job_id]["started_at"] = time.time()

        env = os.environ.copy()
        if chrome_profile:
            # Resolve profile path. If it's a name, verify existence in PROFILES_ROOT.
            # Note: PROFILES_ROOT is defined later in this file, but available at runtime.
            # To be safe, we re-derive or check if global exists.
            profiles_root_Runtime = globals().get("PROFILES_ROOT", os.path.join(BASE_DIR, "chrome_profiles"))
            
            # Check if direct path or name
            if os.path.isabs(chrome_profile) and os.path.isdir(chrome_profile):
                 env["SORA_CHROME_PROFILE"] = chrome_profile
            else:
                 candidate = os.path.join(profiles_root_Runtime, chrome_profile)
                 if os.path.isdir(candidate):
                     env["SORA_CHROME_PROFILE"] = candidate
                 else:
                     print(f"[WARN] Chrome profile '{chrome_profile}' not found in {profiles_root_Runtime}. Using default.", flush=True)

        # Dispatch logic based on profile name prefix
        target_script = SORA_SCRIPT
        is_veo_profile = chrome_profile and chrome_profile.lower().startswith(("veo", "flow"))
        wants_frames = bool(frame_1 or frame_2)
        if is_veo_profile or wants_frames:
            target_script = VEO_SCRIPT
            reason = "profile prefix" if is_veo_profile else "frame inputs"
            print(f"[Dispatcher] Using VEO_SCRIPT ({reason}): {target_script}", flush=True)
        else:
            print(f"[Dispatcher] Using SORA_SCRIPT: {target_script}", flush=True)

        cmd = [PYTHON, target_script, prompt, row_id, story_id, str(scene)]
        if target_script == VEO_SCRIPT and frame_1 and frame_2:
            cmd.extend([frame_1, frame_2])
        print(f"[Job {job_id}] Running: {' '.join(cmd[:2])} ...", flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)

        out = proc.stdout or ""
        err = proc.stderr or ""
        parsed = parse_marker(out)

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

        # ✅ only callback after finished download
        finished = bool(result.get("result", {}).get("finished"))
        if job.webhookUrl and result["ok"] and finished:
            callback_payload = {"jobId": job_id, "status": JOBS[job_id]["status"], **result}
            post_webhook(job.webhookUrl, callback_payload, job_id=job_id, store=JOBS)
    
    except Exception as e:
        import traceback
        error_msg = f"Job {job_id} crashed: {e}\n{traceback.format_exc()}"
        print(f"[ERROR] {error_msg}", flush=True)
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["finished_at"] = time.time()
        JOBS[job_id]["result"] = {
            "ok": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


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

    threading.Thread(target=run_job_background, args=(job_id, job), daemon=True).start()

    return {
        "ok": True,
        "jobId": job_id,
        "status": "queued",
        "storyId": story_id,
        "scene": scene,
        "rowId": (job.rowId or ""),
        "message": "Job accepted. Will callback webhookUrl ONLY when finished=true.",
    }


@app.get("/status/{job_id}")
def status(job_id: str):
    j = JOBS.get(job_id)
    if not j:
        return {"ok": False, "error": "job not found", "jobId": job_id}
    return {
        "ok": True,
        "jobId": job_id,
        "status": j["status"],
        "created_at": j.get("created_at"),
        "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"),
        "result": j.get("result"),
    }


# ============================================================
# 2) MEDIA route: /process  (merge/captions/music)
# ============================================================
class ClipItem(BaseModel):
    scene: Optional[int] = None
    local_path: str


class MediaJob(BaseModel):
    storyId: str
    clips: List[Union[str, ClipItem]] = Field(default_factory=list)

    musicPath: Optional[str] = None
    outputDir: Optional[str] = None

    webhookUrl: Optional[str] = None


def normalize_clips(clips: List[Union[str, ClipItem]]) -> List[str]:
    out: List[str] = []
    for c in clips:
        if isinstance(c, str):
            p = c.strip()
            if p:
                out.append(p)
        else:
            p = (c.local_path or "").strip()
            if p:
                out.append(p)
    return out


def run_media_background(job_id: str, job: MediaJob):
    story_id = job.storyId.strip()
    clips = normalize_clips(job.clips)
    music = (job.musicPath or "").strip()
    output_dir = (job.outputDir or "").strip()

    MEDIA_JOBS[job_id]["status"] = "running"
    MEDIA_JOBS[job_id]["started_at"] = time.time()

    if not output_dir:
        output_dir = os.path.join(BASE_DIR, "outputs", story_id)
    os.makedirs(output_dir, exist_ok=True)

    # create input json for media script (clean)
    payload = {
        "jobId": job_id,
        "storyId": story_id,
        "clips": clips,
        "musicPath": music or None,
        "outputDir": output_dir,
    }
    input_json_path = os.path.join(output_dir, f"media_input_{job_id}.json")
    with open(input_json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    cmd = [PYTHON, MEDIA_SCRIPT, input_json_path]
    print(f"DEBUG: cmd={cmd}", flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, env=os.environ.copy())

    out = proc.stdout or ""
    err = proc.stderr or ""
    print(f"DEBUG: proc.returncode={proc.returncode}, out={repr(out)}, err={repr(err)}", flush=True)
    parsed = parse_marker(out)

    ok = (proc.returncode == 0) and bool(parsed.get("merged_done"))

    result = {
        "ok": ok,
        "exitCode": proc.returncode,
        "jobId": job_id,
        "storyId": story_id,
        "stdout": out[-8000:],
        "stderr": err[-8000:],
        "result": parsed or {},
    }

    MEDIA_JOBS[job_id]["status"] = "done" if ok else "error"
    MEDIA_JOBS[job_id]["finished_at"] = time.time()
    MEDIA_JOBS[job_id]["result"] = result

    if job.webhookUrl:
        callback_payload = {"jobId": job_id, "status": MEDIA_JOBS[job_id]["status"], **result}
        post_webhook(job.webhookUrl, callback_payload, job_id=job_id, store=MEDIA_JOBS)

    # Always notify the media_done webhook
    media_done_payload = {"jobId": job_id, "status": MEDIA_JOBS[job_id]["status"], **result}
    post_webhook("http://localhost:5678/webhook/media_done", media_done_payload, job_id=job_id, store=MEDIA_JOBS)


@app.post("/process")
def process(job: MediaJob):
    story_id = (job.storyId or "").strip()
    clips = normalize_clips(job.clips)

    if not story_id:
        return {"ok": False, "error": "storyId is empty"}
    if not clips:
        return {"ok": False, "error": "clips is empty"}

    # optional: validate files exist
    missing = [p for p in clips if not Path(p).exists()]
    if missing:
        return {"ok": False, "error": f"missing clips: {missing[:3]}{'...' if len(missing) > 3 else ''}"}

    job_id = uuid.uuid4().hex
    MEDIA_JOBS[job_id] = {
        "status": "queued",
        "job": job.model_dump(),
        "created_at": time.time(),
        "result": None,
    }

    threading.Thread(target=run_media_background, args=(job_id, job), daemon=True).start()

    return {
        "ok": True,
        "jobId": job_id,
        "status": "queued",
        "storyId": story_id,
        "clipCount": len(clips),
        "message": "Media job accepted. Will callback webhookUrl when merged_done=true.",
    }


@app.get("/process_status/{job_id}")
def process_status(job_id: str):
    j = MEDIA_JOBS.get(job_id)
    if not j:
        return {"ok": False, "error": "job not found", "jobId": job_id}
    return {
        "ok": True,
        "jobId": job_id,
        "status": j["status"],
        "created_at": j.get("created_at"),
        "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"),
        "result": j.get("result"),
    }

@app.get("/routes")
def routes():
    result = []
    for r in app.router.routes:
        # Skip routes without methods (like Mount for static files)
        if not hasattr(r, 'methods'):
            continue
        methods = ','.join(sorted(r.methods or []))
        result.append(f"{r.path} [{methods}]")
    return sorted(result)


# ============================================================
# 4) YOUTUBE UPLOAD route: /upload_youtube
# ============================================================
class YouTubeJob(BaseModel):
    videoPath: str
    title: str
    description: str
    storyId: str
    visibility: Optional[str] = "public"  # public, unlisted, or private
    chromeProfile: Optional[str] = None
    webhookUrl: Optional[str] = None


def run_youtube_background(job_id: str, job: YouTubeJob):
    try:
        video_path = job.videoPath.strip()
        title = job.title.strip()
        description = job.description.strip()
        story_id = job.storyId.strip()
        visibility = (job.visibility or "public").strip().lower()
        chrome_profile = (job.chromeProfile or "").strip()

        YOUTUBE_JOBS[job_id]["status"] = "running"
        YOUTUBE_JOBS[job_id]["started_at"] = time.time()

        env = os.environ.copy()
        if chrome_profile:
            # Resolve profile path. If it's a name, verify existence in PROFILES_ROOT.
            profiles_root_Runtime = globals().get("PROFILES_ROOT", os.path.join(BASE_DIR, "chrome_profiles"))
            
            # Check if direct path or name
            if os.path.isabs(chrome_profile) and os.path.isdir(chrome_profile):
                env["YT_CHROME_PROFILE"] = chrome_profile
            else:
                candidate = os.path.join(profiles_root_Runtime, chrome_profile)
                if os.path.isdir(candidate):
                    env["YT_CHROME_PROFILE"] = candidate
                else:
                    print(f"[WARN] Chrome profile '{chrome_profile}' not found in {profiles_root_Runtime}. Using default.", flush=True)

        cmd = [PYTHON, YOUTUBE_SCRIPT, video_path, title, description, story_id, visibility]
        print(f"[YouTube Job {job_id}] Running: {' '.join(cmd[:2])} ... (visibility: {visibility})", flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env)

        out = proc.stdout or ""
        err = proc.stderr or ""
        parsed = parse_marker(out)

        result = {
            "ok": proc.returncode == 0,
            "exitCode": proc.returncode,
            "jobId": job_id,
            "storyId": story_id,
            "videoPath": video_path,
            "title": title,
            "stdout": out[-8000:],
            "stderr": err[-8000:],
            "result": parsed or {},
        }

        YOUTUBE_JOBS[job_id]["status"] = "done" if result["ok"] else "error"
        YOUTUBE_JOBS[job_id]["finished_at"] = time.time()
        YOUTUBE_JOBS[job_id]["result"] = result

        # Webhook callback
        finished = bool(result.get("result", {}).get("finished"))
        if job.webhookUrl and result["ok"] and finished:
            callback_payload = {"jobId": job_id, "status": YOUTUBE_JOBS[job_id]["status"], **result}
            post_webhook(job.webhookUrl, callback_payload, job_id=job_id, store=YOUTUBE_JOBS)
    
    except Exception as e:
        import traceback
        error_msg = f"YouTube Job {job_id} crashed: {e}\n{traceback.format_exc()}"
        print(f"[ERROR] {error_msg}", flush=True)
        YOUTUBE_JOBS[job_id]["status"] = "error"
        YOUTUBE_JOBS[job_id]["finished_at"] = time.time()
        YOUTUBE_JOBS[job_id]["result"] = {
            "ok": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@app.post("/upload_youtube")
def upload_youtube(job: YouTubeJob):
    video_path = (job.videoPath or "").strip()
    title = (job.title or "").strip()
    description = (job.description or "").strip()
    story_id = (job.storyId or "").strip()

    if not video_path:
        return {"ok": False, "error": "videoPath is empty"}
    if not os.path.exists(video_path):
        return {"ok": False, "error": f"Video file not found: {video_path}"}
    if not title:
        return {"ok": False, "error": "title is empty"}
    if not story_id:
        return {"ok": False, "error": "storyId is empty"}

    job_id = uuid.uuid4().hex

    YOUTUBE_JOBS[job_id] = {
        "status": "queued",
        "job": job.model_dump(),
        "created_at": time.time(),
        "result": None,
    }

    threading.Thread(target=run_youtube_background, args=(job_id, job), daemon=True).start()

    return {
        "ok": True,
        "jobId": job_id,
        "status": "queued",
        "storyId": story_id,
        "videoPath": video_path,
        "message": "YouTube upload job accepted. Will callback webhookUrl when finished=true.",
    }


@app.get("/upload_youtube_status/{job_id}")
def upload_youtube_status(job_id: str):
    j = YOUTUBE_JOBS.get(job_id)
    if not j:
        return {"ok": False, "error": "job not found", "jobId": job_id}
    return {
        "ok": True,
        "jobId": job_id,
        "status": j["status"],
        "created_at": j.get("created_at"),
        "started_at": j.get("started_at"),
        "finished_at": j.get("finished_at"),
        "result": j.get("result"),
    }



# ============================================================
# 3) CHROME PROFILE MANAGEMENT
# ============================================================
PROFILES_ROOT = os.path.join(BASE_DIR, "chrome_profiles")
os.makedirs(PROFILES_ROOT, exist_ok=True)

class ProfileReq(BaseModel):
    name: str

@app.get("/list_profiles")
def list_profiles():
    """List all available chrome profile directories."""
    if not os.path.exists(PROFILES_ROOT):
        return {"profiles": []}
    
    profiles = []
    for item in os.listdir(PROFILES_ROOT):
        p = os.path.join(PROFILES_ROOT, item)
        if os.path.isdir(p):
            # Check if running (naive check if lock file exists, optional)
            profiles.append(item)
    return {"profiles": sorted(profiles)}

@app.post("/create_profile")
def create_profile(req: ProfileReq):
    name = req.name.strip()
    if not name:
        return {"ok": False, "error": "Name cannot be empty"}
    
    # Sanitize name
    safe_name = "".join([c for c in name if c.isalnum() or c in ('-', '_')]).strip()
    if not safe_name:
         return {"ok": False, "error": "Invalid profile name"}

    target = os.path.join(PROFILES_ROOT, safe_name)
    if os.path.exists(target):
         return {"ok": False, "error": "Profile already exists"}
    
    try:
        os.makedirs(target)
        return {"ok": True, "name": safe_name}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/delete_profile")
def delete_profile(req: ProfileReq):
    name = req.name.strip()
    target = os.path.join(PROFILES_ROOT, name)
    if not os.path.exists(target):
        return {"ok": False, "error": "Profile not found"}
    
    try:
        shutil.rmtree(target)
        return {"ok": True, "name": name}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/launch_profile")
def launch_profile(req: ProfileReq):
    """
    Launch a browser window for this profile (headful) so user can login/manage.
    This spawns a background process.
    """
    name = req.name.strip()
    profile_path = os.path.join(PROFILES_ROOT, name)
    if not os.path.exists(profile_path):
        return {"ok": False, "error": "Profile not found"}
    
    # We need a script to launch the browser. 
    # We'll use a new script 'launch_browser.py' or inline valid python code.
    # Let's point to a new script.
    launcher_script = os.path.join(BASE_DIR, "scripts", "launch_browser.py")
    
    cmd = [PYTHON, launcher_script, profile_path]
    
    try:
        # Popen without waiting
        subprocess.Popen(cmd, env=os.environ.copy())
        return {"ok": True, "message": f"Launched profile {name}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
