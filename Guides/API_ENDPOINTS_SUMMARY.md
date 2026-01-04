# Arkite Server API - Endpoint Organization

## API Overview
**Title:** Server Communication  
**Version:** 2025.1  
**Description:** REST API for retrieving and modifying project data, and running operations on workstations (units)

---

## Endpoint Categories

The API is organized into **2 main categories** using tags:

### 1. **"data"** Tag - Data Management Endpoints
Calls for sending and requesting data (configuration, CRUD operations)

### 2. **"operation"** Tag - Runtime Operation Endpoints  
Calls during operations (controlling running units, fetching runtime state)

---

## Detailed Endpoint Breakdown

### 📁 **UNITS** (Workstations)
**Tag:** `data`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/units/` | Fetch all units |
| GET | `/units/{unitId}/` | Fetch unit by ID |
| DELETE | `/units/{unitId}/` | Delete unit by ID |

---

### 📁 **PROJECTS**
**Tag:** `data`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/` | Fetch all projects |
| POST | `/projects/` | Add one or more projects |
| GET | `/projects/{projectId}` | Fetch project by ID |
| PATCH | `/projects/{projectId}` | Update project properties |
| DELETE | `/projects/{projectId}` | Delete project |
| POST | `/projects/{projectId}/duplicate/` | Duplicate project |

---

### 📁 **PROCESSES** (under Projects)
**Tag:** `data`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/{projectId}/processes/` | Fetch all processes for project |
| POST | `/projects/{projectId}/processes/` | Add processes to project |
| GET | `/projects/{projectId}/processes/{processId}/` | Fetch process by ID |
| DELETE | `/projects/{projectId}/processes/{processId}/` | Delete process |
| POST | `/projects/{projectId}/processes/{processId}/duplicate/` | Duplicate process |
| GET | `/projects/{projectId}/processes/{processId}/steps/` | Fetch steps for process |

---

### 📁 **TASKS** (under Projects)
**Tag:** `data`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/{projectId}/tasks/` | Fetch all tasks for project |
| GET | `/projects/{projectId}/tasks/{taskId}/` | Fetch task by ID |

---

### 📁 **DETECTIONS** (under Projects)
**Tag:** `data`  
Detections include: objects, tools, activities, picking bins, virtual buttons, quality checks

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/{projectId}/detections/` | Fetch all detections |
| POST | `/projects/{projectId}/detections/` | Add detections |
| GET | `/projects/{projectId}/detections/{detectionId}/` | Fetch detection by ID |
| PATCH | `/projects/{projectId}/detections/{detectionId}/` | Update detection |
| DELETE | `/projects/{projectId}/detections/{detectionId}/` | Delete detection |
| POST | `/projects/{projectId}/detections/{detectionId}/duplicate/` | Duplicate detection |
| POST | `/projects/{projectId}/detections/createFromCAD/` | Create CAD/CAM detection |

---

### 📁 **MATERIALS** (under Projects)
**Tag:** `data`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/{projectId}/materials/` | Fetch all materials |
| POST | `/projects/{projectId}/materials/` | Add materials |
| GET | `/projects/{projectId}/materials/{materialId}/` | Fetch material by ID |
| PATCH | `/projects/{projectId}/materials/{materialId}/` | Update material |
| DELETE | `/projects/{projectId}/materials/{materialId}/` | Delete material |

---

### 📁 **IMAGES/RESOURCES** (under Projects)
**Tag:** `data`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/{projectId}/images/` | Fetch all images |
| POST | `/projects/{projectId}/images/` | Upload images (multipart/form-data) |
| GET | `/projects/{projectId}/images/{imageId}/` | Fetch image by ID |
| DELETE | `/projects/{projectId}/images/{imageId}/` | Delete image |
| POST | `/projects/{projectId}/images/{imageId}/replace/` | Replace image |
| GET | `/projects/{projectId}/images/{imageId}/show/` | Show image |

---

### 📁 **STEPS** (under Projects)
**Tag:** `data`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/{projectId}/steps/` | Fetch all steps |
| POST | `/projects/{projectId}/steps/` | Add steps |
| PATCH | `/projects/{projectId}/steps/{stepId}` | Update step |
| DELETE | `/projects/{projectId}/steps/{stepId}` | Delete step |
| POST | `/projects/{projectId}/steps/{stepId}/duplicate/` | Duplicate step |
| GET | `/projects/{projectId}/steps/{compositeStepId}/childSteps/` | Fetch child steps |

---

### 📁 **CONDITIONS** (under Projects)
**Tag:** `data`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/{projectId}/conditions/` | Fetch all conditions |
| POST | `/projects/{projectId}/conditions/` | Add conditions |
| PATCH | `/projects/{projectId}/conditions/{conditionId}` | Update condition |
| DELETE | `/projects/{projectId}/conditions/{conditionId}` | Delete condition |
| POST | `/projects/{projectId}/conditions/{conditionId}/duplicate/` | Duplicate condition |

---

### 📁 **VARIANTS** (under Projects)
**Tag:** `data`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/{projectId}/variants/` | Fetch all variants |
| POST | `/projects/{projectId}/variants/` | Add variants |
| PATCH | `/projects/{projectId}/variants/{variantId}` | Update variant |
| DELETE | `/projects/{projectId}/variants/{variantId}` | Delete variant |
| POST | `/projects/{projectId}/variants/{variantId}/duplicate/` | Duplicate variant |

---

### 📁 **VARIABLES** (under Projects)
**Tag:** `data`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/projects/{projectId}/variables/` | Fetch all variables |
| POST | `/projects/{projectId}/variables/` | Add variables |
| PATCH | `/projects/{projectId}/variables/{variableId}` | Update variable |
| DELETE | `/projects/{projectId}/variables/{variableId}` | Delete variable |

---

## 🚀 **RUNTIME OPERATIONS** (on Running Units)
**Tag:** `operation`  
*These endpoints require a running unit (workstation software active)*

### Project Loading
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/units/{unitId}/projects/{projectId}/load/` | Load project on unit |
| GET | `/units/{unitId}/loadedProject/` | Get currently loaded project |

### Variable Operations (Runtime)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/units/{unitId}/variables/{variableName}/` | Get variable value by name |
| GET | `/units/{unitId}/variables/` | Get all variables |
| PUT | `/units/{unitId}/variables/` | Set variable states |

### Process Control
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/units/{unitId}/processes/control/` | Control processes (Next, Previous, Reset, Play, Pause, Restart, Goto) |
| GET | `/units/{unitId}/processes/{processId}/activeSteps/` | Get active steps for process |

### Material/Picking Bin Operations
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/units/{unitId}/material/{materialId}/pickingBins/` | Get picking bins for material |
| GET | `/units/{unitId}/pickingBin/{pickingBinId}/material/` | Get material for picking bin |

---

## Summary Statistics

- **Total Endpoints:** ~65 endpoints
- **Data Endpoints:** ~55 endpoints (configuration/CRUD)
- **Operation Endpoints:** ~10 endpoints (runtime control)
- **Main Resource Groups:** Units, Projects, Processes, Tasks, Detections, Materials, Images, Steps, Conditions, Variants, Variables

---

## Authentication

All endpoints require API key authentication via:
- Header: `apiKey` 
- OR Query parameter: `apiKey`

---

## Base URLs

- Production: `https://myServerUrl/api/v1`
- Local: `https://localhost/api/v1`

