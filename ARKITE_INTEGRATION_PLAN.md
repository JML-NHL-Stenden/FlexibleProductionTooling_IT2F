# Arkite Integration Plan

## Overview
Integrate Arkite project management functionality from the "Test" menu into the main Odoo management interface, using the modern wireframe UI design.

## Phases

### Phase 1: Integrate Arkite Project Management into Projects ✅
**Goal:** Add Arkite project creation/duplication directly in the Project form view

**Tasks:**
- Add `arkite_project_id` field to `product_module.project` model
- Add "Arkite Management" section in Project form view
- Add buttons: "Create Arkite Project", "Duplicate from Template", "Link Existing Project"
- Integrate wizard functionality directly into Project form (no separate wizard)
- Display linked Arkite project info (ID, name, status)

**UI Location:** Project form view → New "Arkite Management" section

---

### Phase 2: Integrate Job Steps Management into Jobs (product_type)
**Goal:** Add Arkite step management directly in the Job form view

**Tasks:**
- Add `arkite_project_id` field to `product_module.type` (Job) model
- Add "Arkite Steps Management" section in Job form view
- Integrate step management (add, edit, reorder job steps)
- Integrate variant management
- Integrate process & step management
- Use native Odoo list views with drag-and-drop (like wireframe UI)

**UI Location:** Job form view → New "Arkite Steps" tab/section

---

### Phase 3: Integrate Detections Management
**Goal:** Add detections management to Project or Job level

**Tasks:**
- Add detections section to Project form view
- Display detections list with add/edit/delete
- Show job-specific vs project-wide detections
- Use native Odoo list views

**UI Location:** Project form view → "Detections" section

---

### Phase 4: Clean Up and Polish
**Goal:** Remove Test menu and finalize integration

**Tasks:**
- Remove Test menu items
- Remove or deprecate wizard models (or keep as backend utilities)
- Update documentation
- Test all functionality
- Ensure UI consistency with wireframe design

---

## Design Principles
1. **Native Odoo UI:** Use standard Odoo components (list views, buttons, fields)
2. **Wireframe Consistency:** Match the modern wireframe UI style
3. **User-Friendly:** Intuitive workflow, clear instructions
4. **No Clunky Interfaces:** Avoid custom HTML/JavaScript where native components work
5. **Progressive Enhancement:** Each phase builds on the previous
