import os
import asyncio
import random
import json
import subprocess
import base64
import requests

import asyncssh
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from database import SessionLocal, UserDB, InstanceDB, get_db

load_dotenv()
app = FastAPI(title="NEO LAB Engine", version="11.0 (Clean Slate Master)")

# On Render, the vastai CLI is available globally once installed via requirements.txt
VAST_BIN = "vastai"

# =========================================================
# 1. ARM THE ENGINE
# =========================================================
VAST_API_KEY = os.environ.get("VAST_API_KEY", "f46431563a4e7e004f6fb6711673353104218571a7d3aabf37ecf53d276ecaa0")
RUNPOD_API_KEY = "user_38PrKsAvO0xVsYSazL25z8qk26h"

subprocess.run([VAST_BIN, "set", "api-key", VAST_API_KEY], capture_output=True)

# 🚨 THE MASTER BASE64 KEY (100% LOCKED IN) 🚨
NEOX_B64_KEY = "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlKS0FJQkFBS0NBZ0VBbjMyYUo1bGlYOGc5djZCeFVnQm1OL3plZEdPUU9nZ2ZrdjhxR1ZsanFITjh3TW5GCjRmVHRnK2ZYRjNFVHB0Q296WC8rVHdQRllsWVlJNzNsRmZDM2dkK0pINHhjeUlzSGNwczQxem1HYjB1UjFDdUUKeUpxWWxta2dxSERXQVhsOXhoZDJ0NEFyOUhML1ZVZUs0a0xMOVJNS2lLdGxTaGszUk5PTmN6eExFNFExMHVwcQpjejRrMzB3S1p0clJsam0vb0xmUW9GNVp6aHpOMGFqVTdlR2VuaVZpK1RkQ0kvakIyOVFKNkNURFA3T1l3NGh4ClhBWFhrZzh3akVsYkxuKzNHYXVZZCt2ZnFHQlpQVjNJUHRRbjljaTNWaVh6OGZmaXpNc0Nza0NQa2RacExlRmYKK3UxK2UwN0NCNHZlMnBHNS91TFB1a1VUNnlmam9pWmgwUVFyNTZTUE9OaGRJejNuM1U1eFVaWklQZ3o5NUhhYQpjTGdLZ1BqaEpVclk5VkVrMGt3cE9FUEtyUlJEWU1Pdno2MVhPN2NlZEE0amN2S0ZRSUpFOElIRmw0ZGVzUmJpCmNBVkxYUXRrbVAwbnAveWpraTZ6RUJHS0dVOGZmYXVSakZxQlM2M2FoTzBqQ0J0dSt2bm52UFZOZnRiWitXNDcKU2RJZDJUd3lHR1o2MmppK2lBL1hCVXpJV05qRnFVU2pJcjlJQXBlWFlIZ3B4VlM2SEt4MU1CenFjRk55U0FPdApzOHZidFpzQmtyQU1scWwrcll2L2FlSDk5Lzl2dUJYcENMTHFXZXFzUTI4ZUplMHNIaHB1cVN5Y3ZQNTVRZVZsCkdJN25hQ29lZjlsM1pqcHNLTDFBZ1BYSXZlWDBKM0YrUll3WUNPL0tDRHloSjN6SEhQeXBBRXV1NW1VQ0F3RUEKQVFLQ0FnQW5oZGdjSlFuNFEyWnQ1TVFBTnFJZUVMZE5yMWlQMFBDR0hGNWgzc0Z2L29KMVFlc2NKZlp2NEJWdwp0VEJSLzlZODZwRnFJanlaTkUyU0dkNDV0Q2U5Y3RnSHJlQldRQUd0K0dJN0Q0SE5kYlFqR0UrMDZINlVrMk9vCjZpRldSeldRVDhNM0VQZVRnYVhkaTdlU2Ywd01wTlhRN1d4UjB2TGJ4dk1BRWZwbTBUWUhXTmpkU3hLWEZVQmsKb2FnYmFwOGVwRDU2WnpjbytRRldDZGtPUkFGckhrZXJDM01EK0FLT1I3cld3TGx6d1QxRGd6M1lPSWhscFFiNgpWTGxZU2dUbFF4MHE1cFJMcE9pb2FPT1ZFanorenVrRDI2N2FrUHV1bFVaTFJ1MXREZTJObFpLVDI2T2l5ZThTCk1LcWVqa3RCcXhJZ0Rqc3o1SFFuL0F2MFlHekNlNXZvYlhqQmpOQk15OTljcUE0STFaUUwrRDNsQVYwR2tNM1cKR2xaTzEzSzFFOGNYVjhWejhISWpNeGZIQTlYVGVFYmowbzc0c2NSTnFiWEhVQ0VBelZaVmxqTVlsVEZSV2JMbgp6VWFXUmdydFB4aWc3TW1mWjZqRmhWdDE2bU0ycERpQ1JQSGp2STBDYzVadlFMTlY2c3plbVphRTVYYkJpeitzCm1wU3o4Tk1RRC94b0lZdHpRVUlTeE1ic2ZVZ0REc05QRTVXeEtYaUZNNFZ2WUpBbHZKRXVQVDRsdERvTno5aFQKNzBBcm41UW11VzI4T2hRWlVEUlEwR3hVVnd3dFBuT1pzeTZ4bWF3VlZXUGRZVVBKUEZrNWYwVGV4T2t5aHJDVwpNZENjVDB4bmpla05EZXZDUEE1QXBVUWo2Y29oYlR3SXB4aFlnUmdCTzVjaFhmdmVkd0tDQVFFQTJhNmMxMjFXCnRqVkJjOTQwL1hSUzhneTZzMkpNc3JWaTN3QXRsYjFnZUxBV28wSnNRZmtreHdQT3dDN3RUa0NpNG5UUktCR04KTnBLaHV5cUlSVWhlcksyYk1sc1NNTUZyRzkyZWE1OHBqK0F3dGpINFlrQVBMZHZXeExnL1dpTXlmVFZKaDdKNgppSHJkVlpGN29TRC90MU05Q3A3aW5KczhmSGs5Qk91dUlzR280WGJjVTVLa0tkSzQxcFpTRERrMFdyUXpCdXIrCi9pZWc1TEtNTmVNbTMrL2dVSjZQRWhxMVpZeWJJZm5nRFVZRjRsRmxpNHRvaEt5QUZDRFF2NkVnWlAvUjM1SGIKVGx1enlVWGtvcWV4dW5DN2N4K2oyYUFkdWM4aXZ0Tmk4ZkdGQ1VQS3BRYlorczNMRUtsQlp0dkZ1N0JPZzhHdAo5U3pFbW95TDJrQkRJd0tDQVFFQXU1QzJ0MC84SEJuMUpCVk1ZazdwVW40eHloQUhGMitWdXNvbTdFZWs3WDJ6CnF3cnNoMG1jczJSSndwTmxjb2pWd05uR2IvWGw4WGFmQjUxSm1pd0RDcXdmRVBaRFdnT2VsSS8reUVHald3emQKRTQ5Qld3Nzg5SmpMRlhYakFVK3l5VXpwWjhrdGorcFJxcGkvRFllL1FNWWk4YnFVOEJ4bGgrVE9nN0I0cVpQSQpBRFRETXpWczJ4Q0tzb3VmOXZjUHBHL2psaEpGa1RFdzhjeGFGWVZ2R1EvdjBJKy9TdE0rOXBGbUw5RHpxaDY0ClRLbWQyV1RkTTlHaVFRMkNRbVNIbEMyV2hVbTJOSk41cDZmcWpLcDBCRjN1ajc0US9JOUFDWEJCVUxvUU9kMEMKM0JZem04emwrb0xhOXBXbFZ2R0t6UzBib2VQektwTzZQU1FieGltczF3S0NBUUVBdjBoZUVEdkhSNk95bVZPNApzc09tSTRhbUJQMnJNaHFNQURPUzJ4TW5rOFlBam9QT3g0WmNGL216azFOcE9pczROdEM1L29DMTJ5K3NxT0N1CkVGdVF2aUpyenlzUjUvLyswK1RCMGdaeHFqa3g5TmdpVUl2RUN1TTBiWGNPVEhIRGF4MEpPUkhQOU9BcVlJZlAKNEg0ejF1OXhJMFVORXRxaW95cVNRU0dzeW1Qc3Qvc1BqdXk4RHZoWmJrOTNWOEJvemcrdEN6WXl6amthZS95ZAprcmpCcjJTRmM3SnhQRkoxOWY5QlR2RFpQakM2K08zWDBuQzFibWg2djdVNldqb0hVbGt1SGt4NEx2b01HU0N1CjBYT1VqS1dGUXB1YUNxRlZuYkp6OE1XbUc3N0V6YWhoaVBSbFZhdkM5aWdWRFlLdjFjY09wMTdwTXhtY3hjWWQKR3JML2l3S0NBUUFncDdkSC93THptWWxXZU9iTmp0T01hekFiNytKc01COHZZQmFhdUhaOGFwQW5UVVdVNERvSgorWUhtQUdkL0kxZWp0Y2FZbzRVZkh2bmRCNE5TOWlxcFp3SVpuK1psKzQ5V2FpTi9sZjNzMGphRE8wT3pxTTVkCmYyU01IZlFodkZCeVA1TzdZQWt3cnlqOHZJODJ1ZFdRWDI2aUMwdjI2ZHE3YUJpVVVOc1JHd3VORGFLV2ZjeXYKN3hkV3NueHRNT0ptVEp5ZytobG1oOXZ2blJacC9NczAzOU51eWpnUnZPbVBZQTBjY2hLYUliTVFsYzlIbEFuMwpCWjVzR1AvK3N5WHZwR2c2V0hVQ2ZsS0YzL1F6L1ZFcG1YajVTYXdIYktGSGcyVzd1a2tzNmMrZnBiWGlnQy9pCkIzbzd5QjM3SHg1OVRrY3JUbFo5cVM2WmlublRiRm9OQW9JQkFIY1ZzSndndmYrRk9yVmswc2JELzBFK3BXOG0KVkQ1Z2R2c2g3dFBrclRYbUYyV2J2V0hCdHZWbVVOcC9lL0tZMXBkTk1XNnVZVGphR2JJSVRWbmNOdFFFK21EUwoxRWdFMC95QmZsZVh4aGl6SGRPR1hhbXBTa0x1NGJXblZFN05mNUhnL212UlBLaXc2cFNpU2VRVjdLZXM1QTJ5ClVXSnVyRXFHa0VSMHdOZGtFMzdORDU2bHVIaXRxN21KL3crdVVWT1AvWWx3YlNqSmZ2bXhSTkRyYzYxMW56MEEKOTB5Rzcram5GVW1nT25EZUU4L09JbGxXb2VKRGFZRVVjKzhnZDA4SGhuVWcrekpvWityU0Z6R3dyREtCRzF6bQpMemJrM0t6N3JnajB1R2hpcXdjQ29uamFoT2pkMUR2U2FzeTRwamdJTnltVUYrK245R1RKQnVkN3pKMD0KLS0tLS1FTkQgUlNBIFBSSVZBVEUgS0VZLS0tLS0="

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

@app.get("/", response_class=HTMLResponse)
async def serve_mobile_ui():
    return HTMLResponse(content="<h1>NEO LAB SYSTEM ONLINE</h1><p>Engine 11.0 is active.</p>", status_code=200)

@app.get("/api/v1/workspace/scan_market")
async def scan_market(vram: float, storage: float = 100.0, gpu_name: str = None):
    try:
        live_nodes = []
        vast_url = "https://console.vast.ai/api/v0/bundles/"
        query = {"rentable": {"eq": True}, "disk_space": {"gte": storage}, "num_gpus": {"eq": 1}}
        headers = {"Authorization": f"Bearer {VAST_API_KEY}"}
        
        res = requests.get(vast_url, params={"q": json.dumps(query)}, headers=headers, timeout=15)
        vast_data = res.json()
        raw_offers = vast_data.get("offers", [])
        
        for o in raw_offers:
            total_vram_gb = (o.get('gpu_ram', 0) * o.get('num_gpus', 1)) / 1024
            if total_vram_gb >= vram and o.get('reliability', 0) >= 0.90:
                price = round(o.get("dph_total", o.get('dph', 0.0)), 3)
                gpu_n = o.get("gpu_name", "GPU").replace('RTX_', 'RTX ')
                live_nodes.append({
                    "id": str(o.get("id")), 
                    "host": f"Global Datacenter (1x {gpu_n})",
                    "price": price,
                    "network": "Tier 1 Fiber",
                    "tag": "VAST.AI NODE",
                    "score": "95%"
                })
        
        live_nodes = sorted(live_nodes, key=lambda x: x["price"])
        return {"status": "success", "nodes": live_nodes[:5]}
    except Exception as e:
        return {"status": "success", "nodes": [{"id": "error", "host": "Global Market Dry", "price": 0.00, "network": "0 MB/s", "tag": "WAITING", "score": "0%"}]}

@app.post("/api/v1/workspace/deploy")
async def trigger_real_deployment(request: DeployRequest, db: Session = Depends(get_db)):
    user = db.query(UserDB).filter(UserDB.user_id == request.user_id).first()
    deposit = request.dph + (0.03 if request.mode == "beginner" else 0)
    
    if not user or user.balance < deposit:
        raise HTTPException(status_code=402, detail=f"Need at least ${deposit}")
        
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

@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket, user_id: str = "user_001"):
    await websocket.accept()
    db = SessionLocal()
    instance = db.query(InstanceDB).filter(InstanceDB.user_id == user_id).first()
    
    if not instance or not instance.status.startswith("running"):
        await websocket.send_text("\r\n\033[5;31m[!] TERMINAL NOT ACTIVE - NO GPU DEPLOYED\033[0m\r\n> ")
        db.close()
        return

    instance_id = instance.vast_instance_id
    ssh_host = os.environ.get(f"SSH_HOST_{instance_id}")
    ssh_port = os.environ.get(f"SSH_PORT_{instance_id}")
    db.close()

    if not ssh_host or not ssh_port:
        await websocket.send_text("\r\n\033[33m[SYS] Waiting for Datacenter network ports to open...\033[0m\r\n")
        return

    try:
        clean_b64 = "".join(NEOX_B64_KEY.split())
        raw_pem_bytes = base64.b64decode(clean_b64)
        raw_pem_string = raw_pem_bytes.decode("utf-8")
        master_key = asyncssh.import_private_key(raw_pem_string)
    except Exception as key_err:
        await websocket.send_text(f"\r\n\033[31m[CRITICAL] Base64 Cryptographic Unpacking Failed: {str(key_err)}\033[0m\r\n")
        return

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
                            return "DESTROY"
                        process.stdin.write(user_input)

                read_task = asyncio.create_task(read_from_ssh())
                write_task = asyncio.create_task(write_to_ssh())
                done, pending = await asyncio.wait([read_task, write_task], return_when=asyncio.FIRST_COMPLETED)
                for task in pending: task.cancel()
                
    except Exception as e:
        error_msg = str(e).split('\n')[0][:40] 
        await websocket.send_text(f"\r\n\033[31m[ERROR] Datacenter Connection Interrupted: {error_msg}\033[0m\r\n")
