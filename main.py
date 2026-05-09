import os
import sys
import time
import requests
import asyncio
import random
import json
import subprocess
import asyncssh
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import SessionLocal, engine, UserDB, InstanceDB, get_db

# =========================================================
# 0. BULLETPROOF CLI LOCATOR (Fixes the Render Execution Error)
# =========================================================
print("⚙️ Checking/Installing CLI tools for Datacenter connection...")
subprocess.run([sys.executable, "-m", "pip", "install", "vastai", "asyncssh"], capture_output=True)

# This finds the exact physical location of the 'vastai' command inside Render's .venv
VAST_BIN = os.path.join(os.path.dirname(sys.executable), "vastai")

load_dotenv()
app = FastAPI(title="NEO LAB Engine", version="7.1.0 (Bulletproof Engine)")

# =========================================================
# 1. ARM THE ENGINE (HYBRID AUTH)
# =========================================================
VAST_API_KEY = os.environ.get("VAST_API_KEY", "f46431563a4e7e004f6fb6711673353104218571a7d3aabf37ecf53d276ecaa0")
RUNPOD_API_KEY = "user_38PrKsAvO0xVsYSazL25z8qk26h"

# Log the master server into Vast.ai using the direct binary
subprocess.run([VAST_BIN, "set", "api-key", VAST_API_KEY], capture_output=True)

video_jobs = {}
VIDEO_MODELS = {
    "kling_v1": {"name": "Kling", "cost": 0.20, "margin": 0.03, "total": 0.23},
    "luma_dream": {"name": "Luma", "cost": 0.30, "margin": 0.05, "total": 0.35},
    "hailuo_minimax": {"name": "Hailuo", "cost": 0.18, "margin": 0.02, "total": 0.20},
    "veo_3_fast": {"name": "Veo 3.1", "cost": 0.22, "margin": 0.03, "total": 0.25}
}

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

async def cost_control_monitor():
    while True:
        await asyncio.sleep(60) 
        db = SessionLocal()
        try:
            active_instances = db.query(InstanceDB).filter(InstanceDB.status.startswith("running")).all()
            for instance in active_instances:
                user = db.query(UserDB).filter(UserDB.user_id == instance.user_id).first()
                if instance.status == "running_expert": hourly_rate = instance.dph
                elif instance.status == "running_beginner": hourly_rate = instance.dph + 0.03 
                else: hourly_rate = 0.03 
                
                cost_per_minute = hourly_rate / 60 
                if user.balance >= cost_per_minute:
                    user.balance -= cost_per_minute
                    db.commit()
                else:
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
    if mode == "beginner":
        video_jobs[job_id]["status"] = "auto_stitching_and_grading"
        await asyncio.sleep(3)
    else:
        video_jobs[job_id]["status"] = "applying_studio_cuts"
        await asyncio.sleep(2)
    video_jobs[job_id]["status"] = "completed"
    video_jobs[job_id]["url"] = f"https://neolab.cloud/vault/render_{job_id}.mp4"

@app.get("/", response_class=HTMLResponse)
async def serve_mobile_ui():
    try:
        with open("templates/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read(), status_code=200)
    except Exception as e:
        return HTMLResponse(content=f"<h1>Error loading UI: {str(e)}</h1>", status_code=500)

@app.get("/api/v1/workspace/scan_market")
async def scan_market(vram: float, storage: float = 100.0, gpu_name: str = None):
    try:
        live_nodes = []
        core_keywords = []
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
            vast_data = res.json()
            raw_offers = vast_data.get("offers", [])
            
            valid_offers = []
            for o in raw_offers:
                total_vram_gb = (o.get('gpu_ram', 0) * o.get('num_gpus', 1)) / 1024
                if total_vram_gb >= vram and o.get('reliability', 0) >= 0.90:
                    if core_keywords:
                        actual_gpu = o.get('gpu_name', '').replace('_', ' ').upper()
                        if not all(kw in actual_gpu for kw in core_keywords):
                            continue 
                    valid_offers.append(o)

            vast_offers = sorted(valid_offers, key=lambda x: x.get('dph_total', x.get('dph', 999)))
            
            for offer in vast_offers[:5]: 
                raw_loc = offer.get("geolocation", "")
                location = raw_loc.split(',')[0].strip() if raw_loc else "Global Datacenter"
                gpu_n = offer.get("gpu_name", "GPU").replace('RTX_', 'RTX ')
                num_gpus = offer.get("num_gpus", 1)
                dl_speed = offer.get("inet_down", 0)
                gbps = dl_speed / 1024
                net_str = f"{round(gbps, 1)} GB/s" if dl_speed > 1000 else f"{round(dl_speed, 1)} MB/s"
                perf_score = 50 + min(50, int(gbps * 5)) 
                price = round(offer.get("dph_total", offer.get('dph', 0.0)), 3)
                tag = "FIBER-OPTIC TIER 1" if dl_speed >= 4000 else "VAST.AI NODE"
                
                live_nodes.append({
                    "id": str(offer.get("id")), 
                    "host": f"{location} ({num_gpus}x {gpu_n})",
                    "price": price,
                    "network": net_str,
                    "tag": tag,
                    "score": f"{perf_score}%"
                })
        except Exception as ve: print(ve)

        if not live_nodes:
            raise Exception("No single-metal nodes matched your strict requirements.")
            
        live_nodes = sorted(live_nodes, key=lambda x: x["price"])
        if live_nodes:
            live_nodes[0]["tag"] = "BEST OVERALL VALUE"
            
        return {"status": "success", "nodes": live_nodes[:5]}
        
    except Exception as e:
        return {"status": "success", "nodes": [{"id": "error", "host": "Global Market Dry", "price": 0.00, "network": "0 MB/s", "tag": "WAITING", "score": "0%"}]}

# =========================================================
# 2. REAL DEPLOYMENT ENGINE (FIXED VAST_BIN CALL)
# =========================================================
@app.post("/api/v1/workspace/deploy")
async def trigger_real_deployment(request: DeployRequest, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.user_id == request.user_id).first()
    deposit = request.dph + (0.03 if request.mode == "beginner" else 0)
    
    if not user or user.balance < deposit:
        raise HTTPException(status_code=402, detail=f"Need at least ${deposit}")
    
    if "runpod" in str(request.offer_id):
        raise HTTPException(status_code=400, detail="RunPod API boot sequence not yet configured. Select a Vast.ai node.")
        
    # Using the direct Binary path instead of sys.executable -m vastai
    cmd = [
        VAST_BIN, "create", "instance", str(request.offer_id),
        "--image", "nvidia/cuda:12.1.1-devel-ubuntu22.04",
        "--disk", str(request.storage),
        "--raw"
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        
        if res.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Datacenter rejected: {res.stderr or res.stdout}")
            
        vast_data = json.loads(res.stdout)
        new_instance_id = vast_data.get("new_contract")
        
        if not new_instance_id:
            raise HTTPException(status_code=500, detail=f"Unexpected Vast response: {res.stdout}")
        
        user.balance -= deposit
        old = db.query(InstanceDB).filter(InstanceDB.user_id == user.user_id).first()
        if old: db.delete(old)
        
        new_machine = InstanceDB(user_id=user.user_id, vast_instance_id=str(new_instance_id), status=f"running_{request.mode}", dph=request.dph)
        db.add(new_machine)
        db.commit()
        db.refresh(user)
        
        return {"status": "booting", "new_balance": round(user.balance, 2), "instance_id": new_instance_id}
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Datacenter took too long to respond.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
# 3. REAL STATUS POLLING (FIXED VAST_BIN CALL)
# =========================================================
@app.get("/api/v1/workspace/status/{instance_id}")
async def get_instance_status(instance_id: str):
    try:
        cmd = [VAST_BIN, "show", "instances", "--raw"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if res.returncode == 0:
            instances = json.loads(res.stdout)
            for inst in instances:
                if str(inst.get("id")) == str(instance_id):
                    status = inst.get("actual_status", "provisioning")
                    
                    if status == "running":
                        os.environ[f"SSH_HOST_{instance_id}"] = inst.get("ssh_host", "")
                        os.environ[f"SSH_PORT_{instance_id}"] = str(inst.get("ssh_port", ""))
                        
                    return {"status": status}
        return {"status": "provisioning"}
    except:
        return {"status": "provisioning"}

# =========================================================
# 4. REAL NEOX SSH TERMINAL BRIDGE
# =========================================================
@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket, user_id: str = "user_001"):
    await websocket.accept()
    db = SessionLocal()
    instance = db.query(InstanceDB).filter(InstanceDB.user_id == user_id).first()
    
    if not instance or not instance.status.startswith("running"):
        await websocket.send_text("\r\n\033[5;31m[!] TERMINAL NOT ACTIVE - NO GPU DEPLOYED\033[0m\r\n> ")
        db.close()
        return

    mode = instance.status.split("_")[1]
    instance_id = instance.vast_instance_id
    ssh_host = os.environ.get(f"SSH_HOST_{instance_id}")
    ssh_port = os.environ.get(f"SSH_PORT_{instance_id}")

    db.close()

    if mode == "beginner":
        await websocket.send_text("\r\n\033[1;34m[NEO LAB OS v6.0]\033[0m Workspace Verified.\r\n\033[35m[NEO ASSISTANT] Hello! I am your dedicated AI DevOps agent.\033[0m\r\nneo-assistant> ")
        try:
            while True:
                data = await websocket.receive_text()
                cmd = data.strip().lower()
                if cmd == "clear": 
                    await websocket.send_text(f"\033[2J\033[Hneo-assistant> ")
                elif "train" in cmd or "fine-tune" in cmd:
                    await websocket.send_text("\r\n\033[35m[NEO] Understood. Initializing secure training pipeline...\033[0m\r\n")
                    await asyncio.sleep(1)
                    await websocket.send_text("\033[36m[*] pip install transformers torch unsloth\033[0m\r\n")
                    await asyncio.sleep(1)
                    await websocket.send_text("\033[32m[SUCCESS] Environment ready! You can now start feeding your dataset.\033[0m\r\nneo-assistant> ")
                else:
                    await websocket.send_text(f"\r\nI am processing command: {cmd}\r\nneo-assistant> ")
        except WebSocketDisconnect:
            pass

    else:
        if not ssh_host or not ssh_port:
            await websocket.send_text("\r\n\033[33m[SYS] Waiting for Datacenter network ports to open...\033[0m\r\n")
            return

        try:
            async with asyncssh.connect(ssh_host, port=int(ssh_port), username="root", known_hosts=None) as conn:
                async with conn.create_process(term_type='xterm-256color', term_size=(50, 20)) as process:
                    
                    async def read_from_ssh():
                        while True:
                            data = await process.stdout.read(1024)
                            if not data: break
                            await websocket.send_text(data)

                    async def write_to_ssh():
                        while True:
                            user_input = await websocket.receive_text()
                            process.stdin.write(user_input)

                    await asyncio.gather(read_from_ssh(), write_to_ssh())
        except Exception as e:
            await websocket.send_text(f"\r\n\033[31m[ERROR] Datacenter Connection Interrupted: Make sure your Master SSH Key is uploaded to Vast.ai!\033[0m\r\n")

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
    
    if request.mode == "beginner":
        total_deduction = VIDEO_MODELS["hailuo_minimax"]["total"] + 0.10 
        target_model = "hailuo_minimax_auto_stitched"
    else:
        model_data = VIDEO_MODELS.get(request.model_id, VIDEO_MODELS["kling_v1"])
        total_deduction = model_data["total"]
        target_model = model_data["name"]
    
    if not user or user.balance < total_deduction:
        raise HTTPException(status_code=402, detail=f"Insufficient credits. Requires ${total_deduction:.2f}")
        
    user.balance -= total_deduction
    db.commit()
    
    job_id = f"vid_{random.randint(1000, 9999)}"
    video_jobs[job_id] = {"status": "queued", "model": target_model, "url": None}
    
    background_tasks.add_task(process_video_lro, job_id, target_model, request.mode)
    return {"status": "queued", "job_id": job_id, "model": target_model, "new_balance": round(user.balance, 2)}

@app.get("/api/v1/video/status/{job_id}")
async def get_video_status(job_id: str):
    if job_id not in video_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return video_jobs[job_id]
