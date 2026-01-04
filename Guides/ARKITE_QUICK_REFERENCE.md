# Arkite Quick Reference

## API Endpoints Quick Reference

### Base URL
```
https://your-server-ip/api/v1
```

### Authentication
```python
# Header
headers = {"apiKey": "YOUR_API_KEY"}

# OR Query Parameter
params = {"apiKey": "YOUR_API_KEY"}
```

---

## Projects

### Get All Projects
```python
GET /projects/?apiKey=YOUR_KEY
Response: [{"Id": 123, "Name": "Project1", ...}, ...]
```

### Get Project by ID
```python
GET /projects/{projectId}?apiKey=YOUR_KEY
```

### Create Project
```python
POST /projects/?apiKey=YOUR_KEY
Body: [{
    "Name": "New Project",
    "Comment": "Description",
    "UnitIds": [12345]
}]
```

### Duplicate Project
```python
POST /projects/{projectId}/duplicate/?apiKey=YOUR_KEY
Response: {"Id": 456, "Name": "Project1 - Copy", ...}
```

### Update Project
```python
PATCH /projects/{projectId}?apiKey=YOUR_KEY
Body: {"Name": "Updated Name"}
```

### Delete Project
```python
DELETE /projects/{projectId}?apiKey=YOUR_KEY
```

---

## Units (Workstations)

### Get All Units
```python
GET /units/?apiKey=YOUR_KEY
Response: [{"Id": 12345, "Name": "Workstation1", ...}, ...]
```

### Get Unit by ID
```python
GET /units/{unitId}?apiKey=YOUR_KEY
```

### Load Project on Unit
```python
POST /units/{unitId}/projects/{projectId}/load/?apiKey=YOUR_KEY
```

### Get Loaded Project
```python
GET /units/{unitId}/loadedProject/?apiKey=YOUR_KEY
Response: {"Id": 123, "Name": "Project Name", ...}
```

---

## Processes (Runtime)

### Control Process
```python
POST /units/{unitId}/processes/control/?apiKey=YOUR_KEY
Body: {
    "ProcessId": 123,
    "Action": "Next"  # Next, Previous, Reset, Play, Pause, Restart, Goto
}
```

### Get Active Steps
```python
GET /units/{unitId}/processes/{processId}/activeSteps/?apiKey=YOUR_KEY
```

---

## Variables (Runtime)

### Get Variable Value
```python
GET /units/{unitId}/variables/{variableName}/?apiKey=YOUR_KEY
Response: {"VariableName": "ProductCode", "Value": "12345"}
```

### Get All Variables
```python
GET /units/{unitId}/variables/?apiKey=YOUR_KEY
Response: [{"VariableName": "Var1", "Value": "val1"}, ...]
```

### Set Variables
```python
PUT /units/{unitId}/variables/?apiKey=YOUR_KEY
Body: {
    "VariableName": "ProductCode",
    "Value": "12345"
}
```

---

## Common Python Patterns

### Find Project by Name
```python
def get_project_id_by_name(project_name: str, api_base: str, api_key: str):
    url = f"{api_base}/projects/"
    params = {"apiKey": api_key}
    response = requests.get(url, params=params, verify=False)
    projects = response.json()
    for proj in projects:
        if proj.get("Name") == project_name:
            return proj.get("Id")
    return None
```

### Duplicate Template Project
```python
def duplicate_template(template_name: str, new_name: str, api_base: str, api_key: str):
    # 1. Find template
    template_id = get_project_id_by_name(template_name, api_base, api_key)
    if not template_id:
        return None
    
    # 2. Duplicate
    url = f"{api_base}/projects/{template_id}/duplicate/"
    params = {"apiKey": api_key}
    response = requests.post(url, params=params, verify=False)
    new_project = response.json()
    new_id = new_project.get("Id")
    
    # 3. Rename
    url = f"{api_base}/projects/{new_id}"
    params = {"apiKey": api_key}
    requests.patch(url, params=params, json={"Name": new_name}, verify=False)
    
    return new_id
```

### Load Project with Retry
```python
def load_project_with_retry(unit_id: int, project_id: int, api_base: str, api_key: str, max_retries=20):
    url = f"{api_base}/units/{unit_id}/projects/{project_id}/load/"
    params = {"apiKey": api_key}
    
    for attempt in range(max_retries):
        response = requests.post(url, params=params, verify=False)
        if response.status_code == 200:
            return True
        if "unit not connected" in response.text.lower():
            time.sleep(5)
            continue
        return False
    return False
```

### Set Variable and Trigger Process
```python
def trigger_job_selection(unit_id: int, product_code: str, process_id: int, api_base: str, api_key: str):
    # 1. Set product code variable
    url = f"{api_base}/units/{unit_id}/variables/"
    params = {"apiKey": api_key}
    requests.put(url, params=params, json={
        "VariableName": "ProductCode",
        "Value": product_code
    }, verify=False)
    
    # 2. Trigger process
    url = f"{api_base}/units/{unit_id}/processes/control/"
    params = {"apiKey": api_key}
    requests.post(url, params=params, json={
        "ProcessId": process_id,
        "Action": "Play"
    }, verify=False)
```

---

## MQTT Integration

### Topic Structure
```
arkite/trigger/QR          # QR code trigger
arkite/status/{unit_id}     # Unit status updates
arkite/events/{unit_id}     # Runtime events
```

### QR Trigger Payload Format
```json
{
  "timestamp": "2024-01-01T12:00:00Z",
  "count": 1,
  "items": [{
    "product_name": "Road Lamp",
    "product_code": "123456",
    "qr_text": "123456"
  }],
  "source": {
    "device": "QR-Scanner-01",
    "location": "Station-1"
  }
}
```

### MQTT Bridge Pattern
```python
import paho.mqtt.client as mqtt

def on_connect(client, userdata, flags, rc):
    client.subscribe("arkite/trigger/QR")

def on_message(client, userdata, msg):
    payload = json.loads(msg.payload.decode())
    product_code = payload["items"][0]["qr_text"]
    
    # Create/load project
    project_id = duplicate_template("Template", product_code)
    load_project(UNIT_ID, project_id)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect("mqtt-broker", 1883)
client.loop_forever()
```

---

## Process Control Actions

| Action | Description |
|--------|-------------|
| `Next` | Move to next step |
| `Previous` | Move to previous step |
| `Reset` | Reset process to beginning |
| `Play` | Start/resume process |
| `Pause` | Pause process |
| `Restart` | Restart from beginning |
| `Goto` | Jump to specific step |

---

## Variable Types

### Shared Variables
- Accessible across all projects
- Use for global settings
- Example: `SystemMode`, `OperatorName`

### Project Variables
- Specific to one project
- Use for project-specific data
- Example: `ProductCode`, `AssemblyStep`

### Process Variables
- Local to a process
- Use for temporary data
- Example: `CurrentStep`, `ValidationResult`

---

## Detection Types

| Type | Description | Use Case |
|------|-------------|----------|
| **Object** | Physical object presence | Parts, components |
| **Activity** | Operator action | Pick, place, assemble |
| **Tool** | Tool presence | Screwdriver, wrench |
| **Picking Bin** | Material location | Component storage |
| **Virtual Button** | Touch screen button | Operator confirmation |
| **Quality Check** | Pass/fail validation | Inspection step |

---

## Step Types

| Type | Description |
|------|-------------|
| **Instruction** | Display text/image/video |
| **Detection** | Wait for object/activity |
| **Variable** | Set or read variable |
| **Condition** | Branch based on condition |
| **Communication** | Send/receive external data |
| **Composite** | Contains child steps |

---

## Project Statuses

| Status | Description | Can Edit? |
|--------|-------------|-----------|
| **Draft** | Being configured | Yes |
| **Review** | Under review | No (except Admin) |
| **Approval** | Awaiting approval | No |
| **Production** | Active in production | No (except Admin) |

---

## License Comparison

| Feature | Guide | Validate | Vision |
|---------|-------|----------|--------|
| AR Instructions | ✅ | ✅ | ✅ |
| Manual Confirmation | ✅ | ✅ | ✅ |
| 3D Sensor | ❌ | ✅ | ✅ |
| Auto Validation | ❌ | ✅ | ✅ |
| Vision Sensor | ❌ | ❌ | ✅ |
| Product Inspection | ❌ | ❌ | ✅ |
| Small Object Detection | ❌ | ❌ | ✅ |

---

## Error Codes

| Code | Meaning | Solution |
|------|---------|----------|
| **200** | Success | - |
| **400** | Bad Request | Check parameters |
| **401** | Unauthorized | Check API key |
| **404** | Not Found | Check ID/name |
| **500** | Server Error | Check server logs |

---

## Common Error Messages

| Message | Cause | Solution |
|---------|-------|----------|
| `unit not connected` | Workstation offline | Wait for unit to come online |
| `project not found` | Invalid project ID | Check project exists |
| `invalid api key` | Wrong API key | Verify API key |
| `workstation not ready` | Unit initializing | Retry after delay |
| `calibration required` | Sensor not calibrated | Run calibration wizard |

---

## Configuration Checklist

### Server Setup
- [ ] Server component installed
- [ ] License key configured
- [ ] API enabled
- [ ] Network accessible

### Workstation Setup
- [ ] Client software installed
- [ ] Connected to server
- [ ] Assigned to license
- [ ] Calibrated (if using sensors)
- [ ] Unit ID noted

### Project Setup
- [ ] Template project created
- [ ] Jobs configured
- [ ] Processes set up
- [ ] Detections configured
- [ ] Variables defined
- [ ] Status set to Production

### Integration Setup
- [ ] API key obtained
- [ ] MQTT broker running
- [ ] Bridge service configured
- [ ] Topics defined
- [ ] Error handling implemented

---

## Quick Troubleshooting

### Project Won't Load
1. Check unit is online: `GET /units/{unitId}`
2. Verify project exists: `GET /projects/{projectId}`
3. Check project status (must be Production)
4. Verify project assigned to unit

### API Returns 401
1. Check API key is correct
2. Verify key format
3. Check key hasn't expired
4. Ensure key is in header or query param

### Detections Not Working
1. Verify sensor is calibrated
2. Check detection boxes are positioned correctly
3. Ensure correct detection type is used
4. Check sensor is connected and working

### MQTT Messages Not Processed
1. Verify broker is running
2. Check topic name matches
3. Verify message format is correct
4. Check bridge service is running
5. Review bridge logs

---

## Environment Variables

```bash
# Arkite API
ARKITE_API_BASE=https://192.168.1.100/api/v1
ARKITE_API_KEY=your_api_key_here
ARKITE_UNIT_ID=12345
ARKITE_TEMPLATE_NAME=Template-Project

# MQTT
MQTT_HOST=mqtt-broker
MQTT_PORT=1883
MQTT_TOPIC_QR=arkite/trigger/QR

# Arkite Agent (Windows)
ARKITE_USER=Admin
ARKITE_PASS=Arkite3600
```

---

## Python Example: Complete Workflow

```python
import requests
import time
import urllib3

urllib3.disable_warnings()

API_BASE = "https://server/api/v1"
API_KEY = "your_key"
UNIT_ID = 12345
TEMPLATE_NAME = "Template-Project"

def create_project_from_qr(qr_code: str, product_name: str):
    """Complete workflow: QR → Project → Load"""
    
    # 1. Find or duplicate template
    template_id = get_project_id_by_name(TEMPLATE_NAME)
    if not template_id:
        print(f"Template '{TEMPLATE_NAME}' not found")
        return False
    
    # 2. Duplicate template
    new_name = product_name or qr_code
    new_id = duplicate_project(template_id, new_name)
    if not new_id:
        print("Failed to duplicate project")
        return False
    
    # 3. Load on unit (with retry)
    success = load_project_with_retry(UNIT_ID, new_id)
    if success:
        print(f"Project '{new_name}' loaded successfully")
    else:
        print(f"Failed to load project after retries")
    
    return success

def get_project_id_by_name(name: str):
    url = f"{API_BASE}/projects/"
    params = {"apiKey": API_KEY}
    response = requests.get(url, params=params, verify=False)
    projects = response.json()
    for proj in projects:
        if proj.get("Name") == name:
            return proj.get("Id")
    return None

def duplicate_project(template_id: int, new_name: str):
    url = f"{API_BASE}/projects/{template_id}/duplicate/"
    params = {"apiKey": API_KEY}
    response = requests.post(url, params=params, verify=False)
    if response.status_code == 200:
        new_proj = response.json()
        new_id = new_proj.get("Id")
        # Rename
        url = f"{API_BASE}/projects/{new_id}"
        requests.patch(url, params=params, json={"Name": new_name}, verify=False)
        return new_id
    return None

def load_project_with_retry(unit_id: int, project_id: int, max_retries=20):
    url = f"{API_BASE}/units/{unit_id}/projects/{project_id}/load/"
    params = {"apiKey": API_KEY}
    
    for attempt in range(max_retries):
        response = requests.post(url, params=params, verify=False)
        if response.status_code == 200:
            return True
        if "unit not connected" in response.text.lower():
            time.sleep(5)
            continue
        return False
    return False

# Usage
create_project_from_qr("123456", "Road Lamp")
```

---

This quick reference covers the most common Arkite operations. Keep it handy for daily development!
