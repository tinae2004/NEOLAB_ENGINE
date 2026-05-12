import os
import sys
import time
import requests
import asyncio
import random
import json
import subprocess
import base64

# =========================================================
# 0. BULLETPROOF CLI LOCATOR & INSTALLER
# =========================================================
print("⚙️ Checking/Installing CLI tools for Datacenter connection...")
# This runs FIRST, before Python tries to import them!
subprocess.run([sys.executable, "-m", "pip", "install", "vastai", "asyncssh", "python-dotenv", "pydantic", "sqlalchemy", "mistralai"], capture_output=True)

# Now we can safely import asyncssh without crashing Render!
import asyncssh
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import SessionLocal, engine, UserDB, InstanceDB, get_db

VAST_BIN = os.path.join(os.path.dirname(sys.executable), "vastai")

load_dotenv()
app = FastAPI(title="NEO LAB Engine", version="10.0 (Ultimate Master Merge)")

# =========================================================
# 1. ARM THE ENGINE (HYBRID AUTH & LOCKED KEY)
# =========================================================
VAST_API_KEY = os.environ.get("VAST_API_KEY", "f46431563a4e7e004f6fb6711673353104218571a7d3aabf37ecf53d276ecaa0")
RUNPOD_API_KEY = "user_38PrKsAvO0xVsYSazL25z8qk26h"

# 🚨 THE MASTER BASE64 KEY (LOCKED IN) 🚨
NEOX_B64_KEY = "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlKS0FJQkFBS0NBZ0VBbjMyYUo1bGlYOGc5djZCeFVnQm1OL3plZEdPUU9nZ2ZrdjhxR1ZsanFITjh3TW5GCjRmVHRnK2ZYRjNFVHB0Q296WC8rVHdQRllsWVlJNzNsRmZDM2dkK0pINHhjeUlzSGNwczQxem1HYjB1UjFDdUUKeUpxWWxta2dxSERXQVhsOXhoZDJ0NEFyOUhML1ZVZUs0a0xMOVJNS2lLdGxTaGszUk5PTmN6eExFNFExMHVwcQpjejRrMzB3S1p0clJsam0vb0xmUW9GNVp6aHpOMGFqVTdlR2VuaVZpK1RkQ0kvakIyOVFKNkNURFA3T1l3NGh4ClhBWFhrZzh3akVsYkxuKzNHYXVZZCt2ZnFHQlpQVjNJUHRRbjljaTNWaVh6OGZmaXpNc0Nza0NQa2RacExlRmYKK3UxK2UwN0NCNHZlMnBHNS91TFB1a1VUNnlmam9pWmgwUVFyNTZTUE9OaGRJejNuM1U1eFVaWklQZ3o5NUhhYQpjTGdLZ1BqaEpVclk5VkVrMGt3cE9FUEtyUlJEWU1Pdno2MVhPN2NlZEE0amN2S0ZRSUpFOElIRmw0ZGVzUmJpCmNBVkxYUXRrbVAwbnAveWpraTZ6RUJHS0dVOGZmYXVSakZxQlM2M2FoTzBqQ0J0dSt2bm52UFZOZnRiWitXNDcKU2RJZDJUd3lHR1o2MmppK2lBL1hCVXpJV05qRnFVU2pJcjlJQXBlWFlIZ3B4VlM2SEt4MU1CenFjRk55U0FPdApzOHZidFpzQmtyQU1scWwrcll2L2FlSDk5Lzl2dUJYcENMTHFXZXFzUTI4ZUplMHNIaHB1cVN5Y3ZQNTVRZVZsCkdJN25hQ29lZjlsM1pqcHNLTDFBZ1BYSXZlWDBKM0YrUll3WUNPL0tDRHloSjN6SEhQeXBBRXV1NW1VQ0F3RUEKQVFLQ0FnQW5oZGdjSlFuNFEyWnQ1TVFBTnFJZUVMZE5yMWlQMFBDR0hGNWgzc0Z2L29KMVFlc2NKZlp2NEJWdwp0VEJSLzlZODZwRnFJanlaTkUyU0dkNDV0Q2U5Y3RnSHJlQldRQUd0K0dJN0Q0SE5kYlFqR0UrMDZINlVrMk9vCjZpRldSeldRVDhNM0VQZVRnYVhkaTdlU2Ywd01wTlhRN1d4UjB2TGJ4dk1BRWZwbTBUWUhXTmpkU3hLWEZVQmsKb2FnYmFwOGVwRDU2WnpjbytRRldDZGtPUkFGckhrZXJDM01EK0FLT1I3cld3TGx6d1QxRGd6M1lPSWhscFFiNgpWTGxZU2dUbFF4MHE1cFJMcE9pb2FPT1ZFanorenVrRDI2N2FrUHV1bFVaTFJ1MXREZTJObFpLVDI2T2l5ZThTCk1LcWVqa3RCcXhJZ0Rqc3o1SFFuL0F2MFlHekNlNXZvYlhqQmpOQk15OTljcUE0STFaUUwrRDNsQVYwR2tNM1cKR2xaTzEzSzFFOGNYVjhWejhISWpNeGZIQTlYVGVFYmowbzc0c2NSTnFiWEhVQ0VBelZaVmxqTVlsVEZSV2JMbgp6VWFXUmdydFB4aWc3TW1mWjZqRmhWdDE2bU0ycERpQ1JQSGp2STBDYzVadlFMTlY2c3plbVphRTVYYkJpeitzCm1wU3o4Tk1RRC94b0lZdHpRVUlTeE1ic2ZVZ0REc05QRTVXeEtYaUZNNFZ2WUpBbHZKRXVQVDRsdERvTno5aFQKNzBBcm41UW11VzI4T2hRWlVEUlEwR3hVVnd3dFBuT1pzeTZ4bWF3VlZXUGRZVVBKUEZrNWYwVGV4T2t5aHJDVwpNZENjVDB4bmpla05EZXZDUEE1QXBVUWo2Y29oYlR3SXB4aFlnUmdCTzVjaFhmdmVkd0tDQVFFQTJhNmMxMjFXCnRqVkJjOTQwL1hSUzhneTZzMkpNc3JWaTN3QXRsYjFnZUxBV28wSnNRZmtreHdQT3dDN3RUa0NpNG5UUktCR04KTnBLaHV5cUlSVWhlcksyYk1sc1NNTUZyRzkyZWE1OHBqK0F3dGpINFlrQVBMZHZXeExnL1dpTXlmVFZKaDdKNgppSHJkVlpGN29TRC90MU05Q3A3aW5KczhmSGs5Qk91dUlzR280WGJjVTVLa0tkSzQxcFpTRERrMFdyUXpCdXIrCi9pZWc1TEtNTmVNbTMrL2dVSjZQRWhxMVpZeWJJZm5nRFVZRjRsRmxpNHRvaEt5QUZDRFF2NkVnWlAvUjM1SGIKVGx1enlVWGtvcWV4dW5DN2N4K2oyYUFkdWM4aXZ0Tmk4ZkdGQ1VQS3BRYlorczNMRUtsQlp0dkZ1N0JPZzhHdAo5U3pFbW95TDJrQkRJd0tDQVFFQXU1QzJ0MC84SEJuMUpCVk1ZazdwVW40eHloQUhGMitWdXNvbTdFZWs3WDJ6CnF3cnNoMG1jczJSSndwTmxjb2pWd05uR2IvWGw4WGFmQjUxSm1pd0RDcXdmRVBaRFdnT2VsSS8reUVHald3emQKRTQ5Qld3Nzg5SmpMRlhYakFVK3l5VXpwWjhrdGorcFJxcGkvRFllL1FNWWk4YnFVOEJ4bGgrVE9nN0I0cVpQSQpBRFRETXpWczJ4Q0tzb3VmOXZjUHBHL2psaEpGa1RFdzhjeGFGWVZ2R1EvdjBJKy9TdE0rOXBGbUw5RHpxaDY0ClRLbWQyV1RkTTlHaVFRMkNRbVNIbEMyV2hVbTJOSk41cDZmcWpLcDBCRjN1ajc0US9JOUFDWEJCVUxvUU9kMEMKM0JZem04emwrb0xhOXBXbFZ2R0t6UzBib2VQektwTzZQU1FieGltczF3S0NBUUVBdjBoZUVEdkhSNk95bVZPNApzc09tSTRhbUJQMnJNaHFNQURPUzJ4TW5rOFlBam9QT3g0WmNGL216azFOcE9pczROdEM1L29DMTJ5K3NxT0N1CkVGdVF2aUpyenlzUjUvLyswK1RCMGdaeHFqa3g5TmdpVUl2RUN1TTBiWGNPVEhIRGF4MEpPUkhQOU9BcVlJZlAKNEg0ejF1OXhJMFVORXRxaW95cVNRU0dzeW1Qc3Qvc1BqdXk4RHZoWmJrOTNWOEJvemcrdEN6WXl6amthZS95ZAprcmpCcjJTRmM3SnhQRkoxOWY5QlR2RFpQakM2K08zWDBuQzFibWg2djdVNldqb0hVbGt1SGt4NEx2b01HU0N1CjBYT1VqS1dGUXB1YUNxRlZuYkp6OE1XbUc3N0V6YWhoaVBSbFZhdkM5aWdWRFlLdjFjY09wMTdwTXhtY3hjWWQKR3JML2l3S0NBUUFncDdkSC93THptWWxXZU9iTmp0T01hekFiNytKc01COHZZQmFhdUhaOGFwQW5UVVdVNERvSgorWUhtQUdkL0kxZWp0Y2FZbzRVZkh2bmRCNE5TOWlxcFp3SVpuK1psKzQ5V2FpTi9sZjNzMGphRE8wT3pxTTVkCmYyU01IZlFodkZCeVA1TzdZQWt3cnlqOHZJODJ1ZFdRWDI2aUMwdjI2ZHE3YUJpVVVOc1JHd3VORGFLV2ZjeXYKN3hkV3NueHRNT0ptVEp5ZytobG1oOXZ2blJacC9NczAzOU51eWpnUnZPbVBZQTBjY2hLYUliTVFsYzlIbEFuMwpCWjVzR1AvK3N5WHZwR2c2V0hVQ2ZsS0YzL1F6L1ZFcG1YajVTYXdIYktGSGcyVzd1a2tzNmMrZnBiWGlnQy9pCkIzbzd5QjM3SHg1OVRrY3JUbFo5cVM2WmlublRiRm9OQW9JQkFIY1ZzSndndmYrRk9yVmswc2JELzBFK3BXOG0KVkQ1Z2R2c2g3dFBrclRYbUYyV2J2V0hCdHZWbVVOcC9lL0tZMXBkTk1XNnVZVGphR2JJSVRWbmNOdFFFK21EUwoxRWdFMC95QmZsZVh4aGl6SGRPR1hhbXBTa0x1NGJXblZFN05mNUhnL212UlBLaXc2cFNpU2VRVjdLZXM1QTJ5ClVXSnVyRXFHa0VSMHdOZGtFMzdORDU2bHVIaXRxN21KL3crdVVWT1AvWWx3YlNqSmZ2bXhSTkRyYzYxMW56MEEKOTB5Rzcram5GVW1nT25EZUU4L09JbGxXb2VKRGFZRVVjKzhnZDA4SGhuVWcrekpvWityU0Z6R3dyREtCRzF6bQpMemJrM0t6N3JnajB1R2hpcXdjQ29uamFoT2pkMUR2U2FzeTRwamdJTnltVUYrK245R1RKQnVkN3pKMD0KLS0tLS1FTkQgUlNBIFBSSVZBVEUgS0VZLS0tLS0="

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
                    subprocess.run([VAST_BIN, "destroy", "instance", str(instance.vast_instance_id)])
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

        try:
            rp_url = f"https://api.runpod.io/graphql?api_key={RUNPOD_API_KEY}"
            query = "{ gpuTypes { id displayName memoryInGb lowestPrice(input: {gpuCount: 1}) { minimumPrice } } }"
            rp_response = requests.post(rp_url, json={"query": query}, headers={"Content-Type": "application/json"}, timeout=10)
            rp_data = rp_response.json()
            
            if "data" in rp_data and "gpuTypes" in rp_data["data"]:
                for gpu in rp_data["data"]["gpuTypes"]:
                    if gpu.get("memoryInGb", 0) >= vram:
                        if core_keywords:
                            actual = gpu.get("displayName", "").upper()
                            if not all(kw in actual for kw in core_keywords):
                                continue
                        lowest = gpu.get("lowestPrice")
                        if lowest and lowest.get("minimumPrice"):
                            live_nodes.append({
                                "id": f"runpod_{gpu.get('id')}",
                                "host": f"RunPod Secure (1x {gpu.get('displayName').replace('NVIDIA ', '')})",
                                "price": round(lowest.get("minimumPrice"), 3),
                                "network": "10.0 GB/s",
                                "tag": "RUNPOD ENTERPRISE",
                                "score": "100%"
                            })
        except Exception as rp_e: pass

        if not live_nodes:
            raise Exception("No single-metal nodes matched your strict requirements.")
            
        live_nodes = sorted(live_nodes, key=lambda x: x["price"])
        if live_nodes:
            live_nodes[0]["tag"] = "BEST OVERALL VALUE"
            
        return {"status": "success", "nodes": live_nodes[:5]}
        
    except Exception as e:
        return {"status": "success", "nodes": [{"id": "error", "host": "Global Market Dry", "price": 0.00, "network": "0 MB/s", "tag": "WAITING", "score": "0%"}]}
