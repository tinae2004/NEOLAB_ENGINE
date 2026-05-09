import os
import sys
import time
import requests
import asyncio
import random
import json
import subprocess
import asyncssh

from fastapi import (
    FastAPI,
    BackgroundTasks,
    HTTPException,
    Depends,
    WebSocket,
    WebSocketDisconnect
)
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import (
    SessionLocal,
    engine,
    UserDB,
    InstanceDB,
    get_db
)

# =========================================================
# NEO LAB ENGINE v8.2
# THE MASTER LOCK (TITANIUM TUNNEL + DEEP LOGGING)
# TRAP REMOVED: No Public Key checks on the server
# =========================================================

print("⚙️ Installing runtime tools...")
subprocess.run([sys.executable, "-m", "pip", "install", "vastai", "asyncssh"], capture_output=True)

VAST_BIN = os.path.join(os.path.dirname(sys.executable), "vastai")

load_dotenv()
app = FastAPI(title="NEO LAB ENGINE", version="8.2")

# =========================================================
# ENVIRONMENT VARIABLES & MASTER KEYS
# =========================================================
VAST_API_KEY = os.environ.get("VAST_API_KEY", "f46431563a4e7e004f6fb6711673353104218571a7d3aabf37ecf53d276ecaa0")
RUNPOD_API_KEY = "user_38PrKsAvO0xVsYSazL25z8qk26h"

# Global Vast.ai Login
subprocess.run([VAST_BIN, "set", "api-key", VAST_API_KEY], capture_output=True)

video_jobs = {}
VIDEO_MODELS = {
    "kling_v1": {"name": "Kling", "total": 0.23},
    "luma_dream": {"name": "Luma", "total": 0.35},
    "hailuo_minimax": {"name": "Hailuo", "total": 0.20},
    "veo_3_fast": {"name": "Veo 3.1", "total": 0.25}
}

# =========================================================
# REQUEST SCHEMAS
# =========================================================
class VoucherClaim(BaseModel):
    user_id: str
    voucher_code: str

class VideoGenRequest(BaseModel):
    user_id: str
    prompt: str
    model_id: str
    mode: str

class DeployRequest(BaseModel):
    user_id: str
    dph: float
    mode: str 
    offer_id: str
    storage: float

# =========================================================
# BILLING MONITOR
# =========================================================
async def cost_control_monitor():
    while True:
        await asyncio.sleep(60) 
        db = SessionLocal()
        try:
            active_instances = db.query(InstanceDB).filter(InstanceDB.status.startswith("running")).all()
            for instance in active_instances:
                user = db.query(UserDB).filter(UserDB.user_id == instance.user_id).first()
                if not user: continue
                
                hourly_rate = instance.dph + (0.03 if instance.status == "running_beginner" else 0)
                cost_per_minute = hourly_rate / 60 
                
                if user.balance >= cost_per_minute:
                    user.balance -= cost_per_minute
                    db.commit()
                else:
                    # Instantly kill machine if funds run out
                    subprocess.run([VAST_BIN, "destroy", "instance", str(instance.vast_instance_id)])
                    instance.status = "destroyed"
                    db.commit()
        finally:
            db.close()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cost_control_monitor())

async def process_video_lro(job_id: str, model_name: str, mode: str):
    await asyncio.sleep(2)
    video_jobs[job_id]["status"] = f"allocating_{model_name}_nodes"
    await asyncio.sleep(4)
    video_jobs[job_id]["status"] = "rendering_frames"
    await asyncio.sleep(3)
    video_jobs[job_id]["status"] = "auto_stitching_and_grading" if mode == "beginner" else "applying_studio_cuts"
    await asyncio.sleep(3)
    video_jobs[job_id]["status"] = "completed"
    video_jobs[job_id]["url"] = f"https://neolab.cloud/vault/render_{job_id}.mp4"

# =========================================================
# UI SERVE
# =========================================================
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error loading UI: {str(e)}</h1>", status_code=500)

# =========================================================
# MARKET SCANNER
# =========================================================
@app.get("/api/v1/workspace/scan_market")
async def scan_market(vram: float, storage: float = 100.0, gpu_name: str = None):
    try:
        live_nodes = []
        core_keywords = []
        BANNED_HOSTS = [385807] 
        
        if gpu_name and gpu_name != "Auto VRAM Search":
            ignore_words = {"NVIDIA", "AMD", "RTX", "GTX", "TI", "SUPER", "D", "ADA", "RADEON"}
            for word in gpu_name.upper().split():
                if word not in ignore_words and not word.endswith("GB"):
                    core_keywords.append(word)

        try:
            vast_url = "https://console.vast.ai/api/v0/bundles/"
            query = {"rentable": {"eq": True}, "disk_space": {"gte": storage}, "num_gpus": {"eq": 1}}
            headers = {"Authorization": f"Bearer {VAST_API_KEY}"}
            
            res = requests.get(vast_url, params={"q": json.dumps(query)}, headers=headers, timeout=15)
            raw_offers = res.json().get("offers", [])
            
            valid_offers = []
            for o in raw_offers:
                if o.get('host_id', 0) in BANNED_HOSTS: continue 
                    
                total_vram_gb = (o.get('gpu_ram', 0) * o.get('num_gpus', 1)) / 1024
                if total_vram_gb >= vram and o.get('reliability', 0) >= 0.98:
                    if core_keywords:
                        actual_gpu = o.get('gpu_name', '').replace('_', ' ').upper()
                        if not all(kw in actual_gpu for kw in core_keywords): continue 
                    valid_offers.append(o)

            vast_offers = sorted(valid_offers, key=lambda x: x.get('dph_total', x.get('dph', 999)))
            
            for offer in vast_offers[:25]: 
                raw_loc = offer.get("geolocation", "")
                location = raw_loc.split(',')[0].strip() if raw_loc else "Global"
                gpu_n = offer.get("gpu_name", "GPU").replace('RTX_', 'RTX ')
                dl_speed = offer.get("inet_down", 0)
                net_str = f"{round(dl_speed / 1024, 1)} GB/s" if dl_speed > 1000 else f"{round(dl_speed, 1)} MB/s"
                
                live_nodes.append({
                    "id": str(offer.get("id")), 
                    "host": f"{location} (1x {gpu_n})",
                    "price": round(offer.get("dph_total", offer.get('dph', 0.0)), 3),
                    "network": net_str,
                    "tag": "FIBER-OPTIC TIER 1" if dl_speed >= 4000 else "VAST.AI NODE",
                    "score": f"{50 + min(50, int((dl_speed / 1024) * 5))}%"
                })
        except Exception as ve: print(ve)

        if not live_nodes: raise Exception("No metal matched requirements.")
        live_nodes = sorted(live_nodes, key=lambda x: x["price"])
        if live_nodes: live_nodes[0]["tag"] = "BEST OVERALL VALUE"
        return {"status": "success", "nodes": live_nodes[:25]}
    except Exception as e:
        return {"status": "success", "nodes": [{"id": "error", "host": "Market Dry", "price": 0.00, "network": "0 MB/s", "tag": "WAIT", "score": "0%"}]}

# =========================================================
# GPU DEPLOYMENT
# =========================================================
@app.post("/api/v1/workspace/deploy")
async def trigger_real_deployment(request: DeployRequest, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.user_id == request.user_id).first()
    deposit = request.dph + (0.03 if request.mode == "beginner" else 0)
    
    if not user or user.balance < deposit:
        raise HTTPException(status_code=402, detail=f"Need at least ${deposit}")
        
    cmd = [
        VAST_BIN, "create", "instance", str(request.offer_id),
        "--image", "nvidia/cuda:11.8.0-devel-ubuntu22.04",
        "--disk", str(request.storage),
        "--raw"
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        if res.returncode != 0: raise HTTPException(status_code=500, detail=f"Datacenter rejected: {res.stderr}")
            
        new_instance_id = json.loads(res.stdout).get("new_contract")
        if not new_instance_id: raise HTTPException(status_code=500, detail="Unexpected Vast response.")
        
        user.balance -= deposit
        old = db.query(InstanceDB).filter(InstanceDB.user_id == user.user_id).first()
        if old: db.delete(old)
        
        new_machine = InstanceDB(user_id=user.user_id, vast_instance_id=str(new_instance_id), status=f"running_{request.mode}", dph=request.dph)
        db.add(new_machine)
        db.commit()
        
        return {"status": "booting", "new_balance": round(user.balance, 2), "instance_id": new_instance_id}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Datacenter took too long to respond.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/workspace/status/{instance_id}")
async def get_instance_status(instance_id: str):
    try:
        res = subprocess.run([VAST_BIN, "show", "instances", "--raw"], capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            for inst in json.loads(res.stdout):
                if str(inst.get("id")) == str(instance_id):
                    return {"status": inst.get("actual_status", "provisioning")}
        return {"status": "provisioning"}
    except: return {"status": "provisioning"}

# =========================================================
# IMMORTAL NEOX TUNNEL (DEEP LOGGING EDITION)
# =========================================================
@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket, user_id: str = "user_001"):
    await websocket.accept()
    db = SessionLocal()
    
    try:
        instance = db.query(InstanceDB).filter(InstanceDB.user_id == user_id).first()
        if not instance or not instance.status.startswith("running"):
            await websocket.send_text("\r\n\033[5;31m[!] TERMINAL NOT ACTIVE - NO GPU DEPLOYED\033[0m\r\n> ")
            return

        mode = instance.status.split("_")[1]
        instance_id = instance.vast_instance_id

        if mode == "beginner":
            await websocket.send_text("\r\n\033[1;34m[NEO LAB OS v6.0]\033[0m Workspace Verified.\r\n\033[35m[NEO ASSISTANT] Hello! I am your AI DevOps agent.\033[0m\r\nneo-assistant> ")
            while True:
                cmd = (await websocket.receive_text()).strip().lower()
                if cmd == "clear": await websocket.send_text(f"\033[2J\033[Hneo-assistant> ")
                else: await websocket.send_text(f"\r\nProcessing: {cmd}\r\nneo-assistant> ")
        else:
            await websocket.send_text("\r\n\033[36m[SYS] Locating Datacenter Node...\033[0m\r\n")
            
            ssh_host, ssh_port = None, None
            res = subprocess.run([VAST_BIN, "show", "instances", "--raw"], capture_output=True, text=True)
            if res.returncode == 0:
                for inst in json.loads(res.stdout):
                    if str(inst.get("id")) == str(instance_id):
                        ssh_host = inst.get("ssh_host")
                        ssh_port = inst.get("ssh_port")

            if not ssh_host or not ssh_port:
                await websocket.send_text("\r\n\033[33m[SYS] Datacenter IP not assigned yet. Wait 30s and try again.\033[0m\r\n")
                return

            priv_key_data = os.environ.get("NEOX_PRIVATE_KEY")
            if not priv_key_data:
                await websocket.send_text("\r\n\033[31m[CRITICAL] NEOX_PRIVATE_KEY missing from Render Environment!\033[0m\r\n")
                return
                
            master_key = asyncssh.import_private_key(priv_key_data)

            while True:
                try:
                    await websocket.send_text(f"\r\n\033[34m[SYS] Probing {ssh_host}:{ssh_port}...\033[0m\r")
                    async with asyncssh.connect(ssh_host, port=int(ssh_port), username="root", client_keys=[master_key], known_hosts=None, login_timeout=15) as conn:
                        async with conn.create_process(term_type='xterm-256color', term_size=(50, 20)) as process:
                            await websocket.send_text("\r\n\033[32m[SUCCESS] Datacenter Door Unlocked. Tunnel Established.\033[0m\r\n")
                            
                            async def read_from_ssh():
                                while True:
                                    data = await process.stdout.read(1024)
                                    if not data: break
                                    await websocket.send_text(data)

                            async def write_to_ssh():
                                while True:
                                    user_input = await websocket.receive_text()
                                    if "neox destroy" in user_input.strip().lower():
                                        await websocket.send_text("\r\n\033[31m[SYS] KILL SWITCH ACTIVATED. Destroying Metal...\033[0m\r\n")
                                        subprocess.run([VAST_BIN, "destroy", "instance", str(instance_id)])
                                        
                                        db_temp = SessionLocal()
                                        inst_to_del = db_temp.query(InstanceDB).filter(InstanceDB.vast_instance_id == str(instance_id)).first()
                                        if inst_to_del:
                                            db_temp.delete(inst_to_del)
                                            db_temp.commit()
                                        db_temp.close()
                                        
                                        await websocket.send_text("\033[32m[SUCCESS] Billing Stopped.\033[0m\r\n")
                                        return "DESTROY"
                                        
                                    process.stdin.write(user_input)

                            read_task = asyncio.create_task(read_from_ssh())
                            write_task = asyncio.create_task(write_to_ssh())
                            done, pending = await asyncio.wait([read_task, write_task], return_when=asyncio.FIRST_COMPLETED)
                            
                            for task in pending: task.cancel()
                            if write_task in done and write_task.result() == "DESTROY": return 
                            await websocket.send_text("\r\n\033[33m[SYS] Network drop detected. Reconnecting...\033[0m\r\n")

                except Exception as e:
                    error_msg = str(e).split('\n')[0][:40] 
                    await websocket.send_text(f"\r\n\033[33m[SYS] OS Download in progress... ({error_msg}) Retrying in 10s.\033[0m\r")
                    await asyncio.sleep(10)

    except WebSocketDisconnect: pass
    except Exception as e: print(f"Tunnel Logic Error: {e}")
    finally: db.close()

# =========================================================
# BILLING & VIDEO LAB 
# =========================================================
@app.post("/api/v1/billing/claim-voucher")
async def claim_voucher(request: VoucherClaim, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.user_id == request.user_id).first()
    if not user:
        user = UserDB(user_id=request.user_id, balance=0.0)
        db.add(user)
    user.balance += 5.00
    db.commit()
    db.refresh(user)
    return {"status": "success", "new_balance": round(user.balance, 2)}

@app.post("/api/v1/video/generate")
async def generate_video(request: VideoGenRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.user_id == request.user_id).first()
    target_model = VIDEO_MODELS.get(request.model_id, VIDEO_MODELS["kling_v1"])["name"]
    total_deduction = VIDEO_MODELS.get(request.model_id, VIDEO_MODELS["kling_v1"])["total"]
    
    if not user or user.balance < total_deduction:
        raise HTTPException(status_code=402, detail=f"Insufficient credits.")
        
    user.balance -= total_deduction
    db.commit()
    
    job_id = f"vid_{random.randint(1000, 9999)}"
    video_jobs[job_id] = {"status": "queued", "model": target_model, "url": None}
    background_tasks.add_task(process_video_lro, job_id, target_model, request.mode)
    return {"status": "queued", "job_id": job_id, "model": target_model, "new_balance": round(user.balance, 2)}

@app.get("/api/v1/video/status/{job_id}")
async def get_video_status(job_id: str):
    if job_id not in video_jobs: raise HTTPException(status_code=404, detail="Job not found")
    return video_jobs[job_id]
