import os
import sys
import time
import json
import subprocess
import asyncio

# =========================================================
# 0. BULLETPROOF CLI LOCATOR
# =========================================================
print("⚙️ Checking/Installing CLI tools for Datacenter connection...")
subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"], capture_output=True)
subprocess.run([sys.executable, "-m", "pip", "install", "vastai", "asyncssh", "python-dotenv", "pydantic", "sqlalchemy", "jinja2"], capture_output=True)

import asyncssh
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, WebSocket, WebSocketDisconnect, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import SessionLocal, engine, UserDB, InstanceDB, get_db

VAST_BIN = os.path.join(os.path.dirname(sys.executable), "vastai")

# =========================================================
# 1. ARM THE ENGINE
# =========================================================
load_dotenv()

# 🚨 FIX: Scrub hidden spaces/newlines and arm the Vast CLI
VAST_API_KEY = os.environ.get("VAST_API_KEY", "f46431563a4e7e004f6fb6711673353104218571a7d3aabf37ecf53d276ecaa0").strip()
if VAST_API_KEY:
    subprocess.run([VAST_BIN, "set", "api-key", VAST_API_KEY])

app = FastAPI(title="NEO LAB Engine", version="12.1 (Native PTY Shell Patch)")
templates = Jinja2Templates(directory="templates")

# 🚨 THE MASTER PADLOCK (INJECTED INTO EVERY VAST RENTAL) 🚨
NEOX_PUB_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICCKfdAADwhtvZYe2swhZq2yssmFuG3d3Uvt1jcebGvSLg neox_master_key"

class DeployRequest(BaseModel):
    user_id: str
    dph: float
    mode: str
    offer_id: str
    storage: int

# =========================================================
# 2. FRONTEND DASHBOARD ROUTE
# =========================================================
@app.get("/")
async def serve_dashboard(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# =========================================================
# 3. DATACENTER DEPLOYMENT LOGIC
# =========================================================
@app.post("/api/v1/workspace/deploy")
async def trigger_real_deployment(request: DeployRequest, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.user_id == request.user_id).first()
    deposit = request.dph + (0.03 if request.mode == "beginner" else 0)
    
    if not user or user.balance < deposit:
        raise HTTPException(status_code=402, detail=f"Need at least ${deposit}")
    
    # 🚨 INJECTING THE PADLOCK (PUBLIC KEY) INTO VAST INSTANCE ON BOOT 🚨
    onstart_script = f"mkdir -p ~/.ssh && echo '{NEOX_PUB_KEY}' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && service ssh start"

    cmd = [
        VAST_BIN, "create", "instance", str(request.offer_id),
        "--image", "nvidia/cuda:12.1.1-devel-ubuntu22.04",
        "--disk", str(request.storage),
        "--onstart-cmd", onstart_script,
        "--raw"
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if res.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Datacenter rejected: {res.stderr or res.stdout}")
            
        vast_data = json.loads(res.stdout)
        new_instance_id = vast_data.get("new_contract")
        
        user.balance -= deposit
        old = db.query(InstanceDB).filter(InstanceDB.user_id == user.user_id).first()
        if old: db.delete(old)
        
        new_machine = InstanceDB(user_id=user.user_id, vast_instance_id=str(new_instance_id), status=f"running_{request.mode}", dph=request.dph)
        db.add(new_machine)
        db.commit()
        
        return {"status": "booting", "new_balance": round(user.balance, 2), "instance_id": new_instance_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/workspace/status/{instance_id}")
async def get_instance_status(instance_id: str, db: Session = Depends(get_db)):
    cmd = [VAST_BIN, "show", "instances", "--raw"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            instances = json.loads(res.stdout)
            for inst in instances:
                if str(inst.get("id")) == str(instance_id):
                    state = inst.get("actual_status", "loading")
                    return {"status": state}
        return {"status": "loading"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

# =========================================================
# 4. IMMORTAL NEOX SSH TERMINAL BRIDGE 
# =========================================================
@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket, user_id: str = "user_001"):
    await websocket.accept()
    db = SessionLocal()
    instance = db.query(InstanceDB).filter(InstanceDB.user_id == user_id).first()
    
    if not instance or not instance.status.startswith("running"):
        await websocket.send_text("\r\n\033[5;31m[!] TERMINAL NOT ACTIVE - NO GPU DEPLOYED\033[0m\r\n")
        db.close()
        return

    mode = instance.status.split("_")[1]
    instance_id = instance.vast_instance_id
    db.close()

    if mode == "beginner":
        await websocket.send_text("\r\n\033[1;34m[NEO LAB OS v6.0]\033[0m Workspace Verified.\r\n\033[35m[NEO ASSISTANT] Hello! I am your AI DevOps agent.\r\nneo-assistant> ")
        while True:
            try:
                cmd = (await websocket.receive_text()).strip().lower()
                if cmd == "clear": await websocket.send_text("\033[2J\033[Hneo-assistant> ")
                else: await websocket.send_text(f"\r\nProcessing: {cmd}\r\nneo-assistant> ")
            except WebSocketDisconnect: return
    else:
        # 🚨 DYNAMICALLY PULL THE VAST PROXY PORT 🚨
        cmd = [VAST_BIN, "show", "instances", "--raw"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        ssh_host, ssh_port = None, None
        if res.returncode == 0:
            instances = json.loads(res.stdout)
            for inst in instances:
                if str(inst.get("id")) == str(instance_id):
                    ssh_host = inst.get("ssh_host")
                    ssh_port = inst.get("ssh_port")
                    break
                    
        if not ssh_host or not ssh_port:
            await websocket.send_text("\r\n\033[33m[SYS] Waiting for Datacenter network ports to open...\033[0m\r\n")
            return

        # 🚨 LOAD THE PRIVATE KEY FROM THE SERVER ENVIRONMENT 🚨
        private_key_str = os.environ.get("NEOX_PRIVATE_KEY")
        if not private_key_str:
            await websocket.send_text("\r\n\033[31m[CRITICAL] NEOX_PRIVATE_KEY missing from environment!\033[0m\r\n")
            return
            
        try:
            if not private_key_str.endswith('\n'):
                private_key_str += '\n'
            master_key = asyncssh.import_private_key(private_key_str)
        except Exception as key_err:
            await websocket.send_text(f"\r\n\033[31m[CRITICAL] Private Key Error: {str(key_err)}\033[0m\r\n")
            return

        try:
            async with asyncssh.connect(ssh_host, port=int(ssh_port), username="root", client_keys=[master_key], known_hosts=None, login_timeout=15) as conn:
                async with conn.create_process(term_type='xterm-256color', term_size=(80, 24), encoding='utf-8') as process:
                    await websocket.send_text("\r\n\033[32m[SUCCESS] Route Opened. Tunnel Active.\033[0m\r\n")
                    
                    async def read_from_ssh():
                        try:
                            while True:
                                data = await process.stdout.read(4096)
                                if not data: break
                                await websocket.send_text(data)
                        except Exception: pass

                    async def write_to_ssh():
                        try:
                            while True:
                                user_input = await websocket.receive_text()
                                if "neox destroy" in user_input.strip().lower():
                                    await websocket.send_text("\r\n\033[31m[SYS] KILL SWITCH ACTIVATED. Destroying Metal...\033[0m\r\n")
                                    subprocess.run([VAST_BIN, "destroy", "instance", str(instance_id)])
                                    return "DESTROY"
                                
                                process.stdin.write(user_input)
                        except WebSocketDisconnect: pass

                    read_task = asyncio.create_task(read_from_ssh())
                    write_task = asyncio.create_task(write_to_ssh())
                    done, pending = await asyncio.wait([read_task, write_task], return_when=asyncio.FIRST_COMPLETED)
                    for task in pending: task.cancel()
                    
        except Exception as e:
            error_msg = str(e).split('\n')[0][:40] 
            await websocket.send_text(f"\r\n\033[31m[ERROR] Datacenter Connection Interrupted: {error_msg}\033[0m\r\n")

# =========================================================
# 5. MARKET SCANNING & VIDEO LAB 
# =========================================================
@app.get("/api/v1/workspace/scan_market")
async def scan_market(vram: int = 24, storage: int = 100, gpu_name: str = ""):
    cmd = [
        VAST_BIN, "search", "offers",
        f"gpu_ram>={vram} disk_space>={storage} rentable=True verified=True",
        "-o", "dph"
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            lines = res.stdout.strip().split('\n')[1:] # Skip header
            nodes = []
            for line in lines[:5]: # Get top 5 cheapest
                parts = line.split()
                if len(parts) > 8:
                    nodes.append({
                        "id": parts[0],
                        "host": f"{parts[4]}x {parts[5]}", 
                        "price": float(parts[8]),
                        "network": parts[10] + " Mbps",
                        "score": parts[7],
                        "tag": "BEST OVERALL VALUE" if len(nodes) == 0 else "AVAILABLE"
                    })
            return {"status": "success", "nodes": nodes}
        return {"status": "error", "nodes": []}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

video_jobs = {}

async def process_video_lro(job_id: str, model_name: str, mode: str):
    await asyncio.sleep(2)
    video_jobs[job_id]["status"] = f"allocating_{model_name}_nodes"
    await asyncio.sleep(4)
    video_jobs[job_id]["status"] = "rendering_frames"
    await asyncio.sleep(3)
    video_jobs[job_id]["status"] = "auto_stitching_and_grading" if mode == "beginner" else "applying_studio_cuts"
    await asyncio.sleep(3)
    video_jobs[job_id]["status"] = "completed"

@app.post("/api/v1/video/render")
async def trigger_video_render(prompt: str, model: str, mode: str, background_tasks: BackgroundTasks):
    job_id = f"vid_{int(time.time())}"
    video_jobs[job_id] = {"status": "queued", "model": model}
    background_tasks.add_task(process_video_lro, job_id, model, mode)
    return {"job_id": job_id, "status": "queued"}

@app.get("/api/v1/video/status/{job_id}")
async def get_video_status(job_id: str):
    if job_id in video_jobs:
        return video_jobs[job_id]
    raise HTTPException(status_code=404, detail="Job not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
