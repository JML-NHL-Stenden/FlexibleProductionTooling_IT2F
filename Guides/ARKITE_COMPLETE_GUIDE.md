# Complete Arkite Platform Guide

## Table of Contents
1. [What is Arkite?](#what-is-arkite)
2. [Architecture & Components](#architecture--components)
3. [License Types](#license-types)
4. [Core Concepts](#core-concepts)
5. [Workflow & Process Flow](#workflow--process-flow)
6. [API Integration](#api-integration)
7. [Integration with This Project](#integration-with-this-project)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

---

## What is Arkite?

**Arkite** is an operator guidance platform that transforms workstations into digital, interactive environments. It provides:

- **Real-time picking and assembly instructions** through Augmented Reality
- **Step-by-step guidance** for operators
- **Validation of operations** (with Validate/Vision licenses)
- **3D sensor-based detection** of objects and activities
- **Project-based workflow management**

### Key Features

- **No Programming Required**: Configure projects through GUI
- **Multi-Workstation Support**: Server-client architecture
- **Real-time Validation**: Automatic verification of steps (with sensors)
- **Flexible Workflows**: Jobs, Processes, Steps, Variants
- **REST API**: Full programmatic control
- **MQTT Integration**: Real-time event handling

---

## Architecture & Components

### Software Components

#### 1. **Server Component**
- Centralized data storage
- Manages all projects, workstations, users
- REST API endpoint
- Should run on dedicated Windows server
- Stores all project data and resources

#### 2. **Workstation Component**
- Client software running on production workstations
- Connects to server
- Displays instructions to operators
- Handles sensor data (if applicable)
- Can run in **Edit** or **Run** mode

### Hardware Components

#### 1. **3D Sensor (Validate/Vision License)**
- **Time-of-Flight (ToF) sensor**
- Captures depth and infrared streams
- Validates object presence and activities
- Creates 3D point cloud of workbench

#### 2. **Projector**
- Projects instructions onto workbench
- Shows visual guidance (arrows, highlights, text)
- Calibrated to match sensor coordinate system

#### 3. **Vision Sensor (Vision License Only)**
- High-definition infrared camera
- Enhanced object detection
- Product inspection capabilities
- Improved detection for small objects (>0.5cm)

### System Architecture

```
┌─────────────────────────────────────────┐
│         Arkite Server                    │
│  - Projects Database                     │
│  - User Management                       │
│  - REST API (port 443/80)               │
│  - License Management                    │
└─────────────────────────────────────────┘
              │
              │ HTTP/REST API
              │
┌─────────────┴─────────────┐
│                           │
│  Workstation 1            │  Workstation 2
│  - Client Software        │  - Client Software
│  - 3D Sensor              │  - 3D Sensor
│  - Projector              │  - Projector
│  - Touch Screen           │  - Touch Screen
└───────────────────────────┘
```

---

## License Types

### 1. **Arkite Guide License**
**Basic Features:**
- Real-time picking and assembly instructions
- Augmented Reality guidance
- Manual step confirmation (operator presses Next)
- No automatic validation
- Text, image, and video instructions

**Use Case:** Simple assembly where operator confirms each step manually.

### 2. **Arkite Validate License**
**Includes Guide +:**
- **3D Sensor** for automatic validation
- Automatic step progression when step is done correctly
- Error warnings when step is incorrect
- Object presence detection
- Activity validation

**Use Case:** Assembly requiring validation that steps are performed correctly.

### 3. **Arkite Vision License**
**Includes Validate +:**
- **Vision Sensor** (high-definition infrared)
- Product inspection during assembly
- Improved detection for small objects (>0.5cm)
- Object orientation detection
- Enhanced material/color distinction

**Use Case:** Complex assemblies requiring precise validation and inspection.

---

## Core Concepts

### Projects

**Definition:** A project contains all information required to support jobs on a workstation.

**Key Points:**
- One project can support multiple jobs
- Projects have statuses: Draft, Review, Production
- Projects can be versioned
- Projects can require approval workflow
- Projects contain: Jobs, Processes, Detections, Materials, Steps, etc.

**Project Workflows:**
1. **Simple:** Draft → Production
2. **With Review:** Draft → Review → Production
3. **With Approval:** Draft → Review → Approval → Production

### Jobs

**Definition:** A work task that an operator performs (e.g., assembly, kitting, inspection).

**Components:**
- **Job Steps**: Individual steps in the job
- **Job Options**: Properties that affect which steps are shown
- **Job Variants**: Combinations of options

**Example:**
- Job: "Assemble Car Model"
- Options: Color (Red, Blue), Engine (V6, V8)
- Variants: Red+V6, Red+V8, Blue+V6, Blue+V8

### Processes

**Definition:** Automated workflows that can be triggered by events or manually.

**Process Types:**
- **Job Selection Process**: Automatically selects which job to run
- **Custom Processes**: Triggered by events, variables, or API calls

**Process Steps:**
- **Instruction Step**: Show instruction to operator
- **Wait Step**: Wait for condition
- **Variable Step**: Set variable value
- **Communication Step**: Send/receive data
- **Trigger Step**: Start another process

### Steps

**Definition:** Individual actions within a job or process.

**Step Types:**
- **Instruction Step**: Display text/image/video
- **Detection Step**: Wait for object/activity detection
- **Variable Step**: Set or read variables
- **Condition Step**: Branch based on condition
- **Communication Step**: Send/receive external data
- **Composite Step**: Contains child steps

### Detections

**Definition:** Objects, activities, tools, or virtual buttons that can be detected.

**Detection Types:**
- **Object Detection**: Presence of physical object
- **Activity Detection**: Operator action (pick, place, etc.)
- **Tool Detection**: Presence of tool
- **Picking Bin Detection**: Material location
- **Virtual Button**: Touch screen button
- **Quality Check**: Pass/fail validation

### Materials

**Definition:** Physical items used in assembly.

**Properties:**
- Name, description
- Image
- Picking bins (storage locations)
- Variants

### Variables

**Definition:** Dynamic values that can be set/read during runtime.

**Types:**
- **Shared Variables**: Accessible across all projects
- **Project Variables**: Specific to one project
- **Process Variables**: Local to a process

**Use Cases:**
- Store product codes
- Track assembly progress
- Pass data between processes
- Control conditional logic

### Units (Workstations)

**Definition:** Physical workstations running Arkite client software.

**Properties:**
- Unique ID (Unit ID)
- Name
- Assigned license
- Calibration status
- Connection status

---

## Workflow & Process Flow

### Typical Assembly Workflow

```
1. Operator scans QR code
   ↓
2. System identifies product
   ↓
3. Job Selection Process triggered
   ↓
4. Appropriate job selected based on product code
   ↓
5. Job starts, first step displayed
   ↓
6. Operator performs step
   ↓
7. System validates step (if Validate/Vision license)
   ↓
8. Next step automatically shown (or operator confirms)
   ↓
9. Repeat until job complete
   ↓
10. Job completion logged
```

### Job Execution Flow

```
┌─────────────────┐
│  Job Selected   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Step 1         │
│  - Instruction  │
│  - Detection    │
└────────┬────────┘
         │
         ▼
    [Validation]
         │
    ┌────┴────┐
    │ Pass?  │
    └───┬────┘
        │
    Yes │ No
        │
        ▼
┌─────────────────┐
│  Step 2         │
│  ...            │
└────────┬────────┘
         │
         ▼
    [Continue]
         │
         ▼
┌─────────────────┐
│  Job Complete   │
└─────────────────┘
```

### Process Trigger Types

1. **Manual Trigger**: Started by operator or admin
2. **Variable Trigger**: Variable value changes
3. **Communication Trigger**: External system sends command
4. **API Trigger**: REST API call
5. **Job Completion Trigger**: Triggered when job finishes
6. **Detection Trigger**: Object/activity detected

---

## API Integration

### Authentication

All API calls require authentication via:
- **Header**: `apiKey: YOUR_API_KEY`
- **OR Query Parameter**: `?apiKey=YOUR_API_KEY`

### Base URL

```
https://your-server-ip/api/v1
```

### Key Endpoints

#### Projects

```python
# Get all projects
GET /projects/?apiKey=YOUR_KEY

# Get project by ID
GET /projects/{projectId}?apiKey=YOUR_KEY

# Create project
POST /projects/?apiKey=YOUR_KEY
Body: [{"Name": "Project Name", "UnitIds": [12345]}]

# Duplicate project
POST /projects/{projectId}/duplicate/?apiKey=YOUR_KEY

# Update project
PATCH /projects/{projectId}?apiKey=YOUR_KEY
Body: {"Name": "New Name"}

# Delete project
DELETE /projects/{projectId}?apiKey=YOUR_KEY
```

#### Units (Workstations)

```python
# Get all units
GET /units/?apiKey=YOUR_KEY

# Get unit by ID
GET /units/{unitId}?apiKey=YOUR_KEY

# Load project on unit
POST /units/{unitId}/projects/{projectId}/load/?apiKey=YOUR_KEY

# Get loaded project
GET /units/{unitId}/loadedProject/?apiKey=YOUR_KEY
```

#### Processes (Runtime)

```python
# Control process
POST /units/{unitId}/processes/control/?apiKey=YOUR_KEY
Body: {
    "ProcessId": 123,
    "Action": "Next"  # Next, Previous, Reset, Play, Pause, Restart, Goto
}

# Get active steps
GET /units/{unitId}/processes/{processId}/activeSteps/?apiKey=YOUR_KEY
```

#### Variables (Runtime)

```python
# Get variable value
GET /units/{unitId}/variables/{variableName}/?apiKey=YOUR_KEY

# Get all variables
GET /units/{unitId}/variables/?apiKey=YOUR_KEY

# Set variables
PUT /units/{unitId}/variables/?apiKey=YOUR_KEY
Body: {
    "VariableName": "ProductCode",
    "Value": "12345"
}
```

### API Response Codes

- **200-299**: Success
- **400**: Bad Request (invalid parameters)
- **401**: Unauthorized (invalid API key)
- **404**: Not Found
- **500**: Server Error

### Common API Patterns

#### 1. Duplicate Template Project

```python
# 1. Find template project
template_id = get_project_id_by_name("Template-Project")

# 2. Duplicate it
POST /projects/{template_id}/duplicate/

# 3. Rename duplicated project
PATCH /projects/{new_project_id}
Body: {"Name": "Product-12345"}

# 4. Load on unit
POST /units/{unit_id}/projects/{new_project_id}/load/
```

#### 2. Set Variable and Trigger Process

```python
# 1. Set product code variable
PUT /units/{unit_id}/variables/
Body: {"VariableName": "ProductCode", "Value": "12345"}

# 2. Trigger job selection process
POST /units/{unit_id}/processes/control/
Body: {"ProcessId": job_selection_process_id, "Action": "Play"}
```

#### 3. Wait for Unit to be Ready

```python
# Retry loading project until unit is online
for attempt in range(max_retries):
    response = POST /units/{unit_id}/projects/{project_id}/load/
    if response.status_code == 200:
        break
    if "unit not connected" in response.text:
        time.sleep(5)  # Wait and retry
        continue
```

---

## Integration with This Project

### Architecture Overview

```
┌─────────────┐
│ QR Scanner  │
└──────┬──────┘
       │
       │ MQTT Message
       │ (arkite/trigger/QR)
       ▼
┌─────────────────┐
│  MQTT Broker     │
│  (Mosquitto)     │
└──────┬───────────┘
       │
       ├─────────────────┐
       │                   │
       ▼                   ▼
┌──────────────┐   ┌──────────────┐
│ MQTT Bridge  │   │ Arkite Agent │
│ (Docker)     │   │ (Windows)    │
└──────┬───────┘   └──────┬───────┘
       │                   │
       │ REST API          │ UI Automation
       │                   │
       ▼                   ▼
┌──────────────┐   ┌──────────────┐
│ Arkite Server│   │ Arkite       │
│ API          │   │ Workstation  │
└──────────────┘   └──────────────┘
```

### Workflow in This Project

#### 1. **QR Code Scan**
- Operator scans QR code
- QR scanner publishes to MQTT topic: `arkite/trigger/QR`
- Payload format:
```json
{
  "timestamp": "2024-01-01T12:00:00",
  "count": 1,
  "items": [{
    "product_name": "Road Lamp",
    "product_code": "123456",
    "qr_text": "123456"
  }],
  "source": {...}
}
```

#### 2. **MQTT Bridge Processing** (Docker Container)
- Listens to `arkite/trigger/QR` topic
- Parses product information
- Calls Arkite API:
  1. Finds or creates project (duplicates template)
  2. Names project after product
  3. Loads project on unit
  4. Retries if unit not ready

#### 3. **Arkite Agent** (Windows Service)
- Listens to same MQTT topic
- If Arkite not running, starts it
- Automates login
- Ensures workstation is ready

#### 4. **Arkite Workstation**
- Receives project load command
- Loads project
- Displays instructions to operator
- Validates steps (if Validate/Vision license)

### Code Examples

#### MQTT Bridge (bridge.py)

```python
def on_message(_cli, _userdata, msg):
    # Parse QR message
    product_name, product_code, qr_text = parse_qr_message(payload)
    
    # Create/resolve project
    project_id = duplicate_template_project(
        TEMPLATE_PROJECT_NAME, 
        product_name or qr_text
    )
    
    # Load on unit
    if project_id:
        wait_and_load_project(UNIT_ID, project_id)
```

#### Arkite Agent (arkite_agent.py)

```python
def on_message(_cli, _userdata, msg):
    # Parse QR message
    product_name, product_code, qr_text = parse_qr_message(payload)
    
    # Ensure Arkite is running and logged in
    if not is_arkite_running():
        open_and_login_arkite()
```

### Configuration

#### Environment Variables

```bash
# Arkite API
ARKITE_API_BASE=https://192.168.1.100/api/v1
ARKITE_API_KEY=Xpz2f7dRi
ARKITE_UNIT_ID=97640866481035
ARKITE_TEMPLATE_NAME=FPT-Template

# MQTT
MQTT_HOST=mqtt
MQTT_PORT=1883
MQTT_TOPIC_QR=arkite/trigger/QR

# Arkite Agent (Windows)
ARKITE_USER=Admin
ARKITE_PASS=Arkite3600
```

---

## Best Practices

### 1. Project Organization

✅ **DO:**
- Use template projects for common workflows
- Name projects clearly (include product code/name)
- Version projects before major changes
- Use project status workflow (Draft → Review → Production)

❌ **DON'T:**
- Create projects directly in production
- Use generic names like "Project1"
- Modify production projects without versioning

### 2. Job Design

✅ **DO:**
- Break jobs into logical steps
- Use job options for variants
- Add clear instructions per step
- Test jobs thoroughly before production

❌ **DON'T:**
- Create overly complex jobs
- Skip validation steps
- Use unclear instructions

### 3. Process Design

✅ **DO:**
- Use job selection processes for dynamic job selection
- Handle errors gracefully
- Log important events
- Use variables for dynamic behavior

❌ **DON'T:**
- Create circular process dependencies
- Ignore error conditions
- Hardcode values that should be variables

### 4. API Usage

✅ **DO:**
- Cache project IDs when possible
- Handle retries for unit connectivity
- Use duplicate endpoint for templates
- Check unit status before loading projects

❌ **DON'T:**
- Create projects without checking if they exist
- Ignore API errors
- Load projects on offline units
- Make excessive API calls

### 5. Detection Setup

✅ **DO:**
- Calibrate sensors properly
- Test detections before production
- Use appropriate detection types
- Position detection boxes accurately

❌ **DON'T:**
- Skip calibration
- Use wrong detection types
- Place detections in wrong locations

### 6. Variable Management

✅ **DO:**
- Use descriptive variable names
- Document variable purposes
- Use shared variables for cross-project data
- Validate variable values

❌ **DON'T:**
- Use generic names like "var1"
- Store sensitive data in variables
- Create too many variables

---

## Troubleshooting

### Common Issues

#### 1. **Unit Not Connected**

**Symptoms:**
- API returns "unit not connected"
- Project won't load

**Solutions:**
- Check workstation is running
- Verify network connectivity
- Check unit ID is correct
- Wait for unit to come online (retry logic)

#### 2. **Project Not Found**

**Symptoms:**
- API returns 404
- Project doesn't exist

**Solutions:**
- Check project name spelling
- Verify project exists on server
- Check API key has access
- List all projects to verify

#### 3. **Calibration Issues**

**Symptoms:**
- Detections not working
- Projections misaligned

**Solutions:**
- Recalibrate sensor and projector
- Check sensor/projector haven't moved
- Verify calibration markers are correct
- Check Windows display scaling (should be 100%)

#### 4. **API Authentication Failed**

**Symptoms:**
- 401 Unauthorized errors
- API calls rejected

**Solutions:**
- Verify API key is correct
- Check API key format
- Ensure API key hasn't expired
- Check server URL is correct

#### 5. **MQTT Messages Not Received**

**Symptoms:**
- Bridge not processing messages
- No project creation

**Solutions:**
- Check MQTT broker is running
- Verify topic name matches
- Check MQTT client connection
- Verify message format is correct

#### 6. **Project Load Fails**

**Symptoms:**
- Project created but won't load
- Unit shows error

**Solutions:**
- Check unit is online
- Verify project is assigned to unit
- Check project status (must be Production)
- Verify project has valid steps

### Debugging Tips

#### 1. **Enable Logging**

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### 2. **Check API Responses**

```python
response = requests.post(url, ...)
print(f"Status: {response.status_code}")
print(f"Response: {response.text}")
```

#### 3. **Verify MQTT Messages**

```python
def on_message(client, userdata, msg):
    print(f"Topic: {msg.topic}")
    print(f"Payload: {msg.payload.decode()}")
```

#### 4. **Test API Endpoints**

```bash
# Test project list
curl "https://server/api/v1/projects/?apiKey=YOUR_KEY"

# Test unit status
curl "https://server/api/v1/units/?apiKey=YOUR_KEY"
```

#### 5. **Check Arkite Workstation**

- Open Arkite Workstation software
- Check connection status
- Verify unit is registered
- Check for error messages

---

## Summary

### Key Takeaways

1. **Arkite is a platform** for operator guidance with AR visualization
2. **Server-Client Architecture** with centralized project management
3. **Three License Types** with increasing capabilities
4. **Project-Based Workflow** with Jobs, Processes, and Steps
5. **REST API** for full programmatic control
6. **MQTT Integration** enables real-time event handling
7. **Template Projects** allow dynamic project creation
8. **Validation** (with sensors) ensures correct assembly

### Integration Pattern

```
QR Scan → MQTT → Bridge → Arkite API → Project Load → Operator Instructions
```

### Best Practices

- Use templates for common workflows
- Handle errors and retries gracefully
- Test thoroughly before production
- Use proper project versioning
- Document processes and variables
- Monitor API and MQTT connections

---

This guide covers the essential aspects of working with Arkite. Refer to the official Arkite documentation for detailed feature information and advanced configurations.
