import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()
VAST_API_KEY = os.getenv("VAST_API_KEY", "your_api_key_here")
HEADERS = {"Accept": "application/json", "Authorization": f"Bearer {VAST_API_KEY}"}

def get_live_market(gpu_name="RTX_3090", vram=24, storage=50):
    print(f"[HUNTER] Scanning global market for {gpu_name} (VRAM: {vram}GB, Storage: {storage}GB)...")
    formatted_gpu = gpu_name.replace(" ", "_")
    
    query = {"ask_contract_unverified": False, "rentable": True, "gpu_name": {"eq": formatted_gpu}}
    query_str = json.dumps(query)
    
    url = f"https://console.vast.ai/api/v0/bundles/?q={query_str}"
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        offers = response.json().get('offers', [])
        offers = sorted(offers, key=lambda x: x['dph_base'])
        
        results = []
        for o in offers[:5]: 
            loc = o.get('geolocation', 'Global Cloud Node')
            inet = o.get('inet_down', 0)
            
            if inet > 1000: net_str = f"{inet/1000:.1f} GB/s"
            else: net_str = f"{inet:.0f} MB/s"
                
            results.append({
                "id": str(o['id']), "location": loc, "inet_down": inet,
                "network_speed": net_str, "total_cost": o['dph_base'] + 0.03 
            })
        return results
    return []

def deploy_metal(offer_id, mode="expert"):
    payload = {
        "client_id": "me", "image": "pytorch/pytorch:2.1.0-cuda11.8-cudnn8-devel",
        "disk": 50, "onstart": "jupyter lab --allow-root --ip=0.0.0.0 --port=8080 --no-browser",
        "runtype": "jupyter"
    }
    url = f"https://console.vast.ai/api/v0/asks/{offer_id}/"
    response = requests.put(url, headers=HEADERS, json=payload)
    if response.status_code == 200: return response.json().get("new_contract")
    return None

def execute_kill_order(instance_id):
    url = f"https://console.vast.ai/api/v0/instances/{instance_id}/"
    return requests.delete(url, headers=HEADERS).status_code == 200
