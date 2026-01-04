#!/usr/bin/env python3
"""
Test script to verify Arkite Processes API endpoints
Tests: GET processes, GET process steps, POST create process, DELETE process
"""
import requests
import json
import os

# Read .env file manually
def read_env_file():
    """Read .env file and return dict of key=value pairs"""
    env_vars = {}
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    return env_vars

env_vars = read_env_file()

# Get credentials from .env file or environment or use defaults
API_BASE = env_vars.get('ARKITE_API_BASE') or os.getenv('ARKITE_API_BASE', 'https://192.168.178.93/api/v1')
API_KEY = env_vars.get('ARKITE_API_KEY') or os.getenv('ARKITE_API_KEY', 'Xpz2f7dRi')
PROJECT_ID = '1792619404459920363'  # From logs - update this to your project ID

print(f"Testing Arkite Processes API")
print(f"API Base: {API_BASE}")
print(f"Project ID: {PROJECT_ID}")
print("=" * 80)

headers = {"Content-Type": "application/json"}
params = {"apiKey": API_KEY}

# 1. GET all processes
print("\n1. GET /projects/{projectId}/processes/")
url = f"{API_BASE}/projects/{PROJECT_ID}/processes/"
print(f"URL: {url}")
try:
    response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
    print(f"Status: {response.status_code}")
    if response.ok:
        processes = response.json()
        print(f"Response: {json.dumps(processes, indent=2)}")
        print(f"Number of processes: {len(processes) if isinstance(processes, list) else 0}")
    else:
        print(f"Error: {response.text[:500]}")
except Exception as e:
    print(f"Exception: {e}")

# 2. GET all steps
print("\n2. GET /projects/{projectId}/steps/")
url = f"{API_BASE}/projects/{PROJECT_ID}/steps/"
print(f"URL: {url}")
try:
    response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
    print(f"Status: {response.status_code}")
    if response.ok:
        steps = response.json()
        print(f"Number of steps: {len(steps) if isinstance(steps, list) else 0}")
        if isinstance(steps, list) and len(steps) > 0:
            print(f"First step: {json.dumps(steps[0], indent=2)}")
            # Check for unique ProcessIds
            process_ids = set()
            for step in steps:
                pid = step.get("ProcessId")
                if pid and str(pid) != "0":
                    process_ids.add(str(pid))
            print(f"Unique ProcessIds found (non-zero): {process_ids}")
    else:
        print(f"Error: {response.text[:500]}")
except Exception as e:
    print(f"Exception: {e}")

# 3. CREATE a test process
print("\n3. POST /projects/{projectId}/processes/ (Create test process)")
url = f"{API_BASE}/projects/{PROJECT_ID}/processes/"
test_process = [{
    "Name": "Test Process from Odoo",
    "Comment": "Test process created by Odoo sync test"
}]
print(f"URL: {url}")
print(f"Payload: {json.dumps(test_process, indent=2)}")
try:
    response = requests.post(url, params=params, headers=headers, json=test_process, verify=False, timeout=10)
    print(f"Status: {response.status_code}")
    if response.ok:
        created = response.json()
        print(f"Created process: {json.dumps(created, indent=2)}")
        created_process_id = created.get("Id") if isinstance(created, dict) else (created[0].get("Id") if isinstance(created, list) and len(created) > 0 else None)
        print(f"Created Process ID: {created_process_id}")
        
        # 4. GET processes again to verify
        print("\n4. GET /projects/{projectId}/processes/ (After creation)")
        response2 = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
        if response2.ok:
            processes = response2.json()
            print(f"Number of processes now: {len(processes) if isinstance(processes, list) else 0}")
            print(f"Processes: {json.dumps(processes, indent=2)}")
        
        # 5. GET process steps for the created process
        if created_process_id:
            print(f"\n5. GET /projects/{PROJECT_ID}/processes/{created_process_id}/steps/")
            steps_url = f"{API_BASE}/projects/{PROJECT_ID}/processes/{created_process_id}/steps/"
            print(f"URL: {steps_url}")
            response3 = requests.get(steps_url, params=params, headers=headers, verify=False, timeout=10)
            if response3.ok:
                process_steps = response3.json()
                print(f"Status: {response3.status_code}")
                print(f"Number of steps for process {created_process_id}: {len(process_steps) if isinstance(process_steps, list) else 0}")
                if isinstance(process_steps, list) and len(process_steps) > 0:
                    print(f"First step: {json.dumps(process_steps[0], indent=2)}")
            else:
                print(f"Error: {response3.status_code} - {response3.text[:500]}")
        
        # 6. DELETE the test process
        if created_process_id:
            print(f"\n6. DELETE /projects/{PROJECT_ID}/processes/{created_process_id}/")
            delete_url = f"{API_BASE}/projects/{PROJECT_ID}/processes/{created_process_id}/"
            print(f"URL: {delete_url}")
            response4 = requests.delete(delete_url, params=params, headers=headers, verify=False, timeout=10)
            print(f"Status: {response4.status_code}")
            if response4.ok:
                print("Process deleted successfully")
            else:
                print(f"Error: {response4.status_code} - {response4.text[:500]}")
    else:
        print(f"Error: {response.status_code} - {response.text[:500]}")
except Exception as e:
    print(f"Exception: {e}")

print("\n" + "=" * 80)
print("Test complete!")
