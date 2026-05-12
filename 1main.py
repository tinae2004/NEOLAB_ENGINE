import os
import sys
import time
import requests
import asyncio
import random
import json
import subprocess
import asyncssh
import base64

from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

# Import from your newly separated files!
from database import SessionLocal, engine, UserDB, InstanceDB, get_db
from config import VAST_API_KEY, VIDEO_MODELS, NEOX_B64_KEY
from schemas import VoucherClaim, VideoGenRequest, DeployRequest

# =========================================================
# NEO LAB ENGINE v9.0
# MODULARIZED SENIOR ARCHITECTURE
# =========================================================

print("⚙️ Installing runtime tools...")
subprocess.run([sys.executable, "-m", "pip", "install", "vastai", "asyncssh"], capture_output=True)

VAST_BIN = os.path.join(os.path.dirname(sys.executable), "vastai")

app = FastAPI(title="NEO LAB ENGINE", version="9.0")

# Global Vast.ai Login
subprocess.run([VAST_BIN, "set", "api-key", VAST_API_KEY], capture_output=True)

video_jobs = {}

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

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
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
