import os
import sys
import json
import time
import asyncio
import random
import subprocess
import requests
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
# NEO LAB ENGINE v8.0
# STABLE SSH + IMMORTAL TUNNEL EDITION
# =========================================================

print("⚙️ Installing runtime tools...")
subprocess.run(
    [sys.executable, "-m", "pip", "install", "vastai", "asyncssh"],
    capture_output=True
)

load_dotenv()

app = FastAPI(
    title="NEO LAB ENGINE",
    version="8.0"
)

# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

VAST_API_KEY = os.getenv("VAST_API_KEY")
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY")
NEOX_PRIVATE_KEY = os.getenv("NEOX_PRIVATE_KEY")
NEOX_PUBLIC_KEY = os.getenv("NEOX_PUBLIC_KEY")

if not VAST_API_KEY:
    raise Exception("VAST_API_KEY missing")

if not NEOX_PRIVATE_KEY:
    raise Exception("NEOX_PRIVATE_KEY missing")

if not NEOX_PUBLIC_KEY:
    raise Exception("NEOX_PUBLIC_KEY missing")

# =========================================================
# VAST CLI
# =========================================================

VAST_BIN = os.path.join(
    os.path.dirname(sys.executable),
    "vastai"
)

subprocess.run(
    [VAST_BIN, "set", "api-key", VAST_API_KEY],
    capture_output=True
)

# =========================================================
# DATABASE MODELS
# =========================================================

video_jobs = {}

VIDEO_MODELS = {
    "kling_v1": {
        "name": "Kling",
        "total": 0.23
    },
    "luma_dream": {
        "name": "Luma",
        "total": 0.35
    },
    "hailuo_minimax": {
        "name": "Hailuo",
        "total": 0.20
    },
    "veo_3_fast": {
        "name": "Veo 3.1",
        "total": 0.25
    }
}

# =========================================================
# REQUEST SCHEMAS
# =========================================================

class VoucherClaim(BaseModel):
    user_id: str
    voucher_code: str

class DeployRequest(BaseModel):
    user_id: str
    dph: float
    mode: str
    offer_id: str
    storage: float

class VideoGenRequest(BaseModel):
    user_id: str
    prompt: str
    model_id: str
    mode: str

# =========================================================
# BILLING MONITOR
# =========================================================

async def cost_control_monitor():

    while True:

        await asyncio.sleep(60)

        db = SessionLocal()

        try:

            active = db.query(InstanceDB).filter(
                InstanceDB.status.startswith("running")
            ).all()

            for inst in active:

                user = db.query(UserDB).filter(
                    UserDB.user_id == inst.user_id
                ).first()

                if not user:
                    continue

                rate = inst.dph

                if inst.status == "running_beginner":
                    rate += 0.03

                minute_cost = rate / 60

                if user.balance >= minute_cost:

                    user.balance -= minute_cost
                    db.commit()

                else:

                    try:
                        subprocess.run(
                            [
                                VAST_BIN,
                                "destroy",
                                "instance",
                                str(inst.vast_instance_id)
                            ],
                            timeout=30
                        )
                    except:
                        pass

                    inst.status = "destroyed"
                    db.commit()

        finally:
            db.close()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cost_control_monitor())

# =========================================================
# UI
# =========================================================

@app.get("/", response_class=HTMLResponse)
async def serve_ui():

    try:

        with open(
            "templates/index.html",
            "r",
            encoding="utf-8"
        ) as f:

            return HTMLResponse(f.read())

    except Exception as e:

        return HTMLResponse(
            f"<h1>{str(e)}</h1>",
            status_code=500
        )

# =========================================================
# MARKET SCANNER
# =========================================================

@app.get("/api/v1/workspace/scan_market")
async def scan_market(
    vram: float,
    storage: float = 100.0
):

    try:

        query = {
            "rentable": {"eq": True},
            "disk_space": {"gte": storage},
            "num_gpus": {"eq": 1}
        }

        headers = {
            "Authorization": f"Bearer {VAST_API_KEY}"
        }

        res = requests.get(
            "https://console.vast.ai/api/v0/bundles/",
            params={"q": json.dumps(query)},
            headers=headers,
            timeout=15
        )

        data = res.json()

        offers = data.get("offers", [])

        nodes = []

        for offer in offers:

            gpu_ram = (
                offer.get("gpu_ram", 0)
                *
                offer.get("num_gpus", 1)
            ) / 1024

            if gpu_ram < vram:
                continue

            if offer.get("reliability", 0) < 0.98:
                continue

            nodes.append({
                "id": str(offer.get("id")),
                "gpu": offer.get("gpu_name"),
                "price": round(
                    offer.get("dph_total", 0),
                    3
                ),
                "location": offer.get(
                    "geolocation",
                    "Global"
                )
            })

        nodes = sorted(
            nodes,
            key=lambda x: x["price"]
        )

        return {
            "status": "success",
            "nodes": nodes[:25]
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }

# =========================================================
# DEPLOY GPU INSTANCE
# =========================================================

@app.post("/api/v1/workspace/deploy")
async def deploy_instance(
    request: DeployRequest,
    db: Session = Depends(get_db)
):

    user = db.query(UserDB).filter(
        UserDB.user_id == request.user_id
    ).first()

    deposit = request.dph

    if request.mode == "beginner":
        deposit += 0.03

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    if user.balance < deposit:
        raise HTTPException(
            status_code=402,
            detail=f"Need at least ${deposit}"
        )

    cmd = [
        VAST_BIN,
        "create",
        "instance",
        str(request.offer_id),

        "--image",
        "vastai/base-image:latest",

        "--disk",
        str(request.storage),

        "--ssh",

        "--env",
        "-p 22:22",

        "--onstart-cmd",
        "service ssh start",

        "--raw"
    ]

    try:

        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        if res.returncode != 0:

            raise HTTPException(
                status_code=500,
                detail=res.stderr or res.stdout
            )

        data = json.loads(res.stdout)

        instance_id = data.get("new_contract")

        if not instance_id:

            raise HTTPException(
                status_code=500,
                detail="No instance returned"
            )

        # subtract money
        user.balance -= deposit

        # remove old
        old = db.query(InstanceDB).filter(
            InstanceDB.user_id == user.user_id
        ).first()

        if old:
            db.delete(old)

        new_inst = InstanceDB(
            user_id=user.user_id,
            vast_instance_id=str(instance_id),
            status=f"running_{request.mode}",
            dph=request.dph,
            ssh_host="",
            ssh_port=""
        )

        db.add(new_inst)
        db.commit()

        # =====================================================
        # WAIT FOR SSH
        # =====================================================

        ssh_ready = False

        for _ in range(60):

            show_cmd = [
                VAST_BIN,
                "show",
                "instances",
                "--raw"
            ]

            out = subprocess.run(
                show_cmd,
                capture_output=True,
                text=True
            )

            if out.returncode == 0:

                instances = json.loads(out.stdout)

                for inst in instances:

                    if str(inst.get("id")) == str(instance_id):

                        ssh_host = inst.get("ssh_host")
                        ssh_port = inst.get("ssh_port")

                        if ssh_host and ssh_port:

                            new_inst.ssh_host = ssh_host
                            new_inst.ssh_port = str(ssh_port)

                            db.commit()

                            ssh_ready = True
                            break

            if ssh_ready:
                break

            await asyncio.sleep(5)

        return {
            "status": "booting",
            "instance_id": instance_id,
            "ssh_ready": ssh_ready,
            "new_balance": round(user.balance, 2)
        }

    except subprocess.TimeoutExpired:

        raise HTTPException(
            status_code=504,
            detail="Datacenter timeout"
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# =========================================================
# INSTANCE STATUS
# =========================================================

@app.get("/api/v1/workspace/status/{instance_id}")
async def get_instance_status(instance_id: str):

    try:

        res = subprocess.run(
            [
                VAST_BIN,
                "show",
                "instances",
                "--raw"
            ],
            capture_output=True,
            text=True
        )

        if res.returncode == 0:

            instances = json.loads(res.stdout)

            for inst in instances:

                if str(inst.get("id")) == str(instance_id):

                    return {
                        "status": inst.get(
                            "actual_status",
                            "loading"
                        ),
                        "ssh_host": inst.get(
                            "ssh_host"
                        ),
                        "ssh_port": inst.get(
                            "ssh_port"
                        )
                    }

        return {
            "status": "not_found"
        }

    except Exception as e:

        return {
            "status": "error",
            "message": str(e)
        }

# =========================================================
# IMMORTAL TERMINAL
# =========================================================

@app.websocket("/ws/terminal")
async def websocket_terminal(
    websocket: WebSocket,
    user_id: str = "user_001"
):

    await websocket.accept()

    db = SessionLocal()

    try:

        instance = db.query(InstanceDB).filter(
            InstanceDB.user_id == user_id
        ).first()

        if not instance:

            await websocket.send_text(
                "\r\n[ERROR] No active instance\r\n"
            )

            return

        mode = instance.status.split("_")[1]

        # =====================================================
        # BEGINNER MODE
        # =====================================================

        if mode == "beginner":

            await websocket.send_text(
                "\r\n[NEO ASSISTANT READY]\r\n"
            )

            while True:

                data = await websocket.receive_text()

                await websocket.send_text(
                    f"\r\nProcessing: {data}\r\n"
                )

        # =====================================================
        # EXPERT MODE
        # =====================================================

        while True:

            db.refresh(instance)

            ssh_host = instance.ssh_host
            ssh_port = instance.ssh_port

            if ssh_host and ssh_port:
                break

            await websocket.send_text(
                "\r\n[SYS] Waiting for SSH tunnel...\r\n"
            )

            await asyncio.sleep(5)

        key = asyncssh.import_private_key(
            NEOX_PRIVATE_KEY
        )

        while True:

            try:

                async with asyncssh.connect(
                    ssh_host,
                    port=int(ssh_port),
                    username="root",
                    client_keys=[key],
                    known_hosts=None
                ) as conn:

                    async with conn.create_process(
                        term_type="xterm-256color"
                    ) as process:

                        await websocket.send_text(
                            "\r\n[SUCCESS] Tunnel Established\r\n"
                        )

                        async def ssh_reader():

                            while True:

                                data = await process.stdout.read(1024)

                                if not data:
                                    break

                                await websocket.send_text(data)

                        async def ssh_writer():

                            while True:

                                cmd = await websocket.receive_text()

                                if (
                                    cmd.strip().lower()
                                    ==
                                    "neox destroy"
                                ):

                                    subprocess.run(
                                        [
                                            VAST_BIN,
                                            "destroy",
                                            "instance",
                                            str(
                                                instance.vast_instance_id
                                            )
                                        ]
                                    )

                                    instance.status = "destroyed"

                                    db.commit()

                                    await websocket.send_text(
                                        "\r\n[DESTROYED]\r\n"
                                    )

                                    return

                                process.stdin.write(cmd)

                        read_task = asyncio.create_task(
                            ssh_reader()
                        )

                        write_task = asyncio.create_task(
                            ssh_writer()
                        )

                        done, pending = await asyncio.wait(
                            [read_task, write_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )

                        for task in pending:
                            task.cancel()

            except Exception:

                await websocket.send_text(
                    "\r\n[SYS] Reconnecting to datacenter...\r\n"
                )

                await asyncio.sleep(5)

    except WebSocketDisconnect:
        pass

    finally:
        db.close()

# =========================================================
# CLAIM VOUCHER
# =========================================================

@app.post("/api/v1/billing/claim-voucher")
async def claim_voucher(
    request: VoucherClaim,
    db: Session = Depends(get_db)
):

    user = db.query(UserDB).filter(
        UserDB.user_id == request.user_id
    ).first()

    if not user:

        user = UserDB(
            user_id=request.user_id,
            balance=0.0
        )

        db.add(user)

    user.balance += 5.0

    db.commit()

    return {
        "status": "success",
        "new_balance": round(user.balance, 2)
}
