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
# IMMORTAL NEOX TUNNEL 
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

            try:
                # 🚨 IMPORTED FROM CONFIG.PY 🚨
                clean_b64 = "".join(NEOX_B64_KEY.split())
                raw_pem_bytes = base64.b64decode(clean_b64)
                raw_pem_string = raw_pem_bytes.decode("utf-8")
                master_key = asyncssh.import_private_key(raw_pem_string)
            except Exception as key_err:
                await websocket.send_text(f"\r\n\033[31m[CRITICAL] Base64 Cryptographic Unpacking Failed: {str(key_err)}\033[0m\r\n")
                return

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
