# product_module/models/arkite_job_step_wizard.py
import os
import logging
import json
import time
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ArkiteJobStepWizard(models.Model):
    _name = 'product_module.arkite.job.step.wizard'
    _description = 'Add Steps to Arkite Job'
    _order = 'id desc'

    # Step 1: Project Selection (independent)
    project_id = fields.Char(
        string='Project ID',
        help='Enter Project ID and click "Load Project" to verify'
    )
    
    project_name = fields.Char(
        string='Project Name',
        readonly=True,
        help='Name of the project (loaded when you click "Load Project")'
    )
    
    project_loaded = fields.Boolean(
        string='Project Loaded',
        default=False,
        readonly=True,
        help='Indicates if project has been successfully loaded'
    )
    
    # Note: We add steps directly to the project (Job steps), not to processes
    # Job steps have ProcessId = 0 or null, Process steps have a non-zero ProcessId
    
    # Step 2: Step Configuration (independent, only after project loaded)
    step_name = fields.Char(
        string='Step Name',
        help='Name of the step to add'
    )
    
    step_type = fields.Selection([
        ('WORK_INSTRUCTION', 'Work Instruction'),
        ('TOOL_PLACING', 'Tool Placing'),
        ('TOOL_TAKING', 'Tool Taking'),
        ('OBJECT_PLACING', 'Object Placing'),
        ('OBJECT_TAKING', 'Object Taking'),
        ('PICKING_BIN_PLACING', 'Picking Bin Placing'),
        ('PICKING_BIN_TAKING', 'Picking Bin Taking'),
        ('ACTIVITY', 'Activity'),
        ('CHECK_NO_CHANGE_ZONE', 'Check No Change Zone'),
        ('VIRTUAL_BUTTON_PRESS', 'Virtual Button Press'),
        ('MATERIAL_GRAB', 'Material Grab'),
        ('COMPOSITE', 'Composite'),
    ], string='Step Type', default='WORK_INSTRUCTION',
       help='Type of step to create')
    
    step_instruction = fields.Text(
        string='Instruction Text',
        help='Text instruction for the step (for WORK_INSTRUCTION type)'
    )
    
    parent_step_id = fields.Char(
        string='Parent Step ID',
        help='ID of the parent step (leave empty to auto-detect root step)'
    )
    
    detection_id = fields.Char(
        string='Detection ID',
        help='Required for: TOOL_PLACING, TOOL_TAKING, OBJECT_PLACING, OBJECT_TAKING, PICKING_BIN_PLACING, PICKING_BIN_TAKING, ACTIVITY, CHECK_NO_CHANGE_ZONE, VIRTUAL_BUTTON_PRESS, MATERIAL_GRAB'
    )
    
    material_id = fields.Char(
        string='Material ID',
        help='Required for MATERIAL_GRAB step type'
    )
    
    button_id = fields.Char(
        string='Button ID',
        help='Required for VIRTUAL_BUTTON_PRESS step type'
    )
    
    index = fields.Integer(
        string='Index',
        default=0,
        help='Position index of the step (0 = append at end)'
    )
    
    # Display/Info fields (regular readonly HTML fields, like working wizard)
    available_projects_info = fields.Html(
        string='Available Projects',
        readonly=True,
        help='List of available projects in Arkite'
    )
    
    # Step 2: Job Steps - Using One2many for native Odoo interface
    job_step_ids = fields.One2many(
        'product_module.arkite.job.step.temp',
        'wizard_id',
        string='Job Steps',
        help='Job steps in the project (drag to reorder)'
    )
    
    # Step 3: Variant Management
    variant_name = fields.Char(
        string='Variant Name',
        help='Name of the variant to add (e.g., V1, Red, Model-A)'
    )
    
    variant_description = fields.Text(
        string='Variant Description',
        help='Optional description for the variant'
    )
    
    variant_names_batch = fields.Text(
        string='Multiple Variant Names',
        help='Enter multiple variant names separated by commas (e.g., V1, V2, V3 or Red, Blue, Green)'
    )
    
    # Step 3: Variants - Using One2many for native Odoo interface  
    variant_ids = fields.One2many(
        'product_module.arkite.variant.temp',
        'wizard_id',
        string='Variants',
        help='Variants in the project'
    )
    
    # Step 4: Process & Step Management - Using One2many for proper Odoo interface
    selected_process_id = fields.Char(
        string='Process ID',
        help='ID of the selected process (enter process name or ID, it will be auto-filled)'
    )
    
    # Temporarily removed selected_process_selection to fix upgrade issue
    # Will be re-added after successful upgrade
    # selected_process_selection = fields.Char(
    #     string='Select Process',
    #     help='Enter process name or ID (process ID will be auto-filled)'
    # )
    
    available_process_ids = fields.One2many(
        'product_module.arkite.process.temp',
        'wizard_id',
        string='Available Processes',
        help='All processes available in the project'
    )
    
    # Temporarily removed onchange - will be re-added after upgrade
    # @api.onchange('selected_process_selection')
    # def _onchange_selected_process_selection(self):
    #     """Update selected_process_id when selection changes"""
    #     if self.selected_process_selection and self.available_process_ids:
    #         # Try to find by name first
    #         matching_process = self.available_process_ids.filtered(
    #             lambda p: p.name == self.selected_process_selection
    #         )
    #         if matching_process:
    #             self.selected_process_id = matching_process[0].process_id
    #         elif self.selected_process_selection.isdigit() or (self.selected_process_selection.startswith('-') and self.selected_process_selection[1:].isdigit()):
    #             # If it's a numeric ID, use it directly
    #             self.selected_process_id = self.selected_process_selection
    #         else:
    #             # Try to find by partial name match
    #             matching_process = self.available_process_ids.filtered(
    #                 lambda p: self.selected_process_selection.lower() in p.name.lower()
    #             )
    #             if matching_process:
    #                 self.selected_process_id = matching_process[0].process_id
    
    process_step_ids = fields.One2many(
        'product_module.arkite.process.step',
        'wizard_id',
        string='Process Steps',
        help='Steps in the selected process (drag to reorder)'
    )
    
    available_variant_ids = fields.Many2many(
        'product_module.arkite.variant.temp',
        'wizard_variant_rel',
        'wizard_id', 'variant_id',
        string='Available Variants',
        help='All variants available in the project'
    )
    
    @api.model
    def create(self, vals):
        """Set default values when creating new record"""
        # Note: job_step_ids, variant_ids, and available_process_ids are One2many fields, no default needed
        return super().create(vals)
    
    def action_list_all_projects(self):
        """List all available projects to help user find project IDs - using exact same pattern as working code"""
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            self.available_projects_info = '<p style="color: #dc3545; font-size: 12px;">Arkite API configuration is missing. Please check environment variables.</p>'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Arkite API configuration is missing',
                    'type': 'danger',
                }
            }
        
        # Use exact same pattern as bridge.py and project wizard
        url = f"{api_base}/projects/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        _logger.info("[ARKITE] Fetching all projects from: %s", url)
        
        try:
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
        except Exception as e:
            _logger.error("[ARKITE] ERROR fetching projects: %s", e, exc_info=True)
            self.write({'available_projects_info': f'<p style="color: #dc3545; font-size: 12px;">Network error: {str(e)}</p>'})
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        
        _logger.info("[ARKITE] GET /projects/ STATUS: %s", response.status_code)
        
        if not response.ok:
            error_text = response.text[:500] if response.text else "Unknown error"
            _logger.error("[ARKITE] Server refused request: %s", error_text)
            self.write({'available_projects_info': f'<p style="color: #dc3545; font-size: 12px;">Failed to fetch projects: HTTP {response.status_code}<br/><pre style="font-size: 10px;">{error_text}</pre></p>'})
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        
        try:
            data = response.json()
        except Exception as e:
            _logger.error("[ARKITE] JSON parse error: %s, Response: %s", e, response.text[:500])
            self.write({'available_projects_info': f'<p style="color: #dc3545; font-size: 12px;">Invalid JSON response: {str(e)}<br/><pre style="font-size: 10px;">{response.text[:500]}</pre></p>'})
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        
        if not isinstance(data, list):
            _logger.error("[ARKITE] Bad format for projects response: %s", data)
            self.write({'available_projects_info': f'<p style="color: #dc3545; font-size: 12px;">Unexpected response format. Expected list, got: {type(data)}<br/><pre style="font-size: 10px;">{str(data)[:500]}</pre></p>'})
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        
        if not data:
            self.write({'available_projects_info': '<p style="color: #666; font-size: 12px;">No projects found in Arkite.</p>'})
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        
        # Build HTML table - using exact same field extraction as bridge.py
        html = '<div style="margin-top: 8px;">'
        html += f'<p style="font-size: 12px; margin-bottom: 8px;"><strong>Found {len(data)} project(s):</strong></p>'
        html += '<table style="width: 100%; border-collapse: collapse; font-size: 12px;">'
        html += '<thead><tr style="background-color: #f8f9fa;"><th style="padding: 8px; border: 1px solid #dee2e6;">Project ID</th><th style="padding: 8px; border: 1px solid #dee2e6;">Project Name</th><th style="padding: 8px; border: 1px solid #dee2e6;">Comment</th></tr></thead>'
        html += '<tbody>'
        
        for proj in data[:50]:  # Limit to 50
            # Use exact same field extraction as bridge.py
            proj_id = proj.get("Id") or proj.get("ProjectId", "N/A")
            proj_name = proj.get("Name") or proj.get("ProjectName", "Unnamed")
            proj_comment = (proj.get("Comment") or proj.get("Description") or "")[:50]
            
            html += f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;"><strong>{proj_id}</strong></td>'
            html += f'<td style="padding: 8px; border: 1px solid #dee2e6;">{proj_name}</td>'
            html += f'<td style="padding: 8px; border: 1px solid #dee2e6;">{proj_comment}</td></tr>'
        
        html += '</tbody></table>'
        if len(data) > 50:
            html += f'<p style="font-size: 11px; color: #666;">Showing first 50 of {len(data)} projects</p>'
        html += '<p style="font-size: 11px; color: #666; margin-top: 8px;"><em>Copy a Project ID from this list and paste it in the Project ID field above, then click "Load Project".</em></p>'
        html += '</div>'
        
        # Write the HTML field to ensure it's saved
        self.write({'available_projects_info': html})
        
        # Return reload to refresh the form and show the updated HTML field
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
    
    def action_load_project(self):
        """Step 1: Load project by ID - using exact same pattern as working code"""
        if not self.project_id:
            self.write({'available_projects_info': '<p style="color: #dc3545; font-size: 12px;">Please enter a Project ID.</p>'})
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            self.write({'available_projects_info': '<p style="color: #dc3545; font-size: 12px;">Arkite API configuration is missing. Please check environment variables.</p>'})
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        
        project_id = self.project_id
        
        # Use exact same pattern as bridge.py - no trailing slash for single project
        url = f"{api_base}/projects/{project_id}"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        _logger.info("[ARKITE] Fetching project ID %s from: %s", project_id, url)
        
        try:
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
        except Exception as e:
            _logger.error("[ARKITE] ERROR fetching project: %s", e, exc_info=True)
            self.write({
                'project_name': "",
                'project_loaded': False,
                'available_projects_info': f'<p style="color: #dc3545; font-size: 12px;">Network error: {str(e)}</p>'
            })
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        
        _logger.info("[ARKITE] GET /projects/{id} STATUS: %s", response.status_code)
        _logger.debug("[ARKITE] GET /projects/{id} RESPONSE: %s", response.text[:500])
        
        if not response.ok:
            error_text = response.text[:500] if response.text else "Unknown error"
            _logger.error("[ARKITE] Server refused request: %s", error_text)
            
            # Try to get all projects to help user (but don't raise UserError - it closes the form)
            try:
                all_url = f"{api_base}/projects/"
                all_response = requests.get(all_url, params=params, headers=headers, verify=False, timeout=10)
                if all_response.ok:
                    all_projects = all_response.json()
                    if isinstance(all_projects, list) and all_projects:
                        project_ids = [str(p.get("Id") or p.get("ProjectId", "N/A")) for p in all_projects[:10]]
                        error_text = f"Project ID {project_id} not found (HTTP {response.status_code}).\n\nAvailable project IDs (first 10): {', '.join(project_ids)}"
            except Exception:
                pass
            
            # Set error message in HTML field
            self.write({
                'project_name': "",
                'project_loaded': False,
                'available_projects_info': f'<p style="color: #dc3545; font-size: 12px;">Project ID {project_id} not found (HTTP {response.status_code}).<br/><pre style="font-size: 10px;">{error_text}</pre><br/>Click "List All Projects" to see available project IDs.</p>'
            })
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        
        try:
            project = response.json()
        except Exception as e:
            _logger.error("[ARKITE] JSON parse error: %s, Response: %s", e, response.text[:500])
            self.write({
                'project_name': "",
                'project_loaded': False,
                'available_projects_info': f'<p style="color: #dc3545; font-size: 12px;">Invalid JSON response: {str(e)}<br/><pre style="font-size: 10px;">{response.text[:500]}</pre></p>'
            })
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        
        # Use exact same field extraction as bridge.py
        project_name = project.get("Name") or project.get("ProjectName") or "Unknown"
        
        _logger.info("[ARKITE] Found project '%s' with ID %s", project_name, project_id)
        
        # Write all fields and reload form
        self.write({
            'project_name': project_name,
            'project_loaded': True,
        })
        
        return {'type': 'ir.actions.client', 'tag': 'reload'}
    
    def action_load_steps(self):
        """Step 2a: Load existing job steps for the project - independent action"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            # Fetch all project steps
            url = f"{api_base}/projects/{self.project_id}/steps/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("[ARKITE] Fetching steps for project %s", self.project_id)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            
            if response.ok:
                all_steps = response.json()
                if isinstance(all_steps, list):
                    # Filter job steps: Type="Job" OR ProcessId is 0/null/empty
                    job_steps = []
                    for s in all_steps:
                        step_type = s.get("Type", "")
                        process_id = s.get("ProcessId")
                        # Job steps have Type="Job" or ProcessId is 0/null/empty string
                        if step_type == "Job" or not process_id or process_id == "0" or process_id == 0:
                            job_steps.append(s)
                    
                    # Sort by Index for better display
                    job_steps.sort(key=lambda x: x.get("Index", 0))
                    
                    # Clear existing job steps
                    self.job_step_ids.unlink()
                    
                    if job_steps:
                        # Create job step records
                        step_records = []
                        for idx, step in enumerate(job_steps):
                            step_id = str(step.get("Id", ""))
                            step_name = step.get("Name", "Unnamed")
                            step_type = step.get("StepType", step.get("Type", "N/A"))
                            parent_id = str(step.get("ParentStepId", "0"))
                            step_index = step.get("Index", idx * 10)
                            
                            step_record = self.env['product_module.arkite.job.step.temp'].create({
                                'wizard_id': self.id,
                                'step_id': step_id,
                                'step_name': step_name,
                                'step_type': step_type,
                                'sequence': step_index,
                                'index': step_index,
                                'parent_step_id': parent_id
                            })
                        step_records.append(step_record.id)
                    
                        # Reload form to show the new records
                        return {'type': 'ir.actions.client', 'tag': 'reload'}
                    else:
                        # Reload form even if no steps found (to clear old data)
                        return {'type': 'ir.actions.client', 'tag': 'reload'}
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Error',
                            'message': 'Unexpected response format.',
                            'type': 'danger',
                        }
                    }
            else:
                error_text = response.text[:200] if response.text else "Unknown error"
                raise UserError(f"Failed to fetch steps: HTTP {response.status_code} - {error_text}")
        except Exception as e:
            _logger.error("Error loading steps: %s", e)
            raise UserError(f"Error loading steps: {str(e)}")
    
    def action_move_step_quick(self):
        """Move a step up or down quickly from the steps list"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        # Get step_id and direction from context
        step_id = self.env.context.get('step_id')
        direction = self.env.context.get('direction')
        
        if not step_id or not direction:
            raise UserError("Step ID and direction must be specified")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            # Get current steps
            url = f"{api_base}/projects/{self.project_id}/steps/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if not response.ok:
                raise UserError(f"Failed to fetch steps: HTTP {response.status_code}")
            
            all_steps = response.json()
            if not isinstance(all_steps, list):
                raise UserError("Unexpected response format")
            
            # Filter job steps and find the target step
            job_steps = []
            target_step = None
            for s in all_steps:
                step_type = s.get("Type", "")
                process_id = s.get("ProcessId")
                if step_type == "Job" or not process_id or process_id == "0" or process_id == 0:
                    job_steps.append(s)
                    if str(s.get("Id", "")) == str(step_id):
                        target_step = s
            
            if not target_step:
                raise UserError(f"Step with ID {step_id} not found")
            
            # Sort by Index
            job_steps.sort(key=lambda x: x.get("Index", 0))
            
            # Find current position
            current_index = None
            for idx, step in enumerate(job_steps):
                if str(step.get("Id", "")) == str(step_id):
                    current_index = idx
                    break
            
            if current_index is None:
                raise UserError(f"Step not found in job steps list")
            
            # Determine new position
            if direction == "up" and current_index > 0:
                new_index = current_index - 1
            elif direction == "down" and current_index < len(job_steps) - 1:
                new_index = current_index + 1
            else:
                raise UserError(f"Cannot move step {direction} - already at boundary")
            
            # Get the step we're swapping with
            swap_step = job_steps[new_index]
            target_index_value = target_step.get("Index", 0)
            swap_index_value = swap_step.get("Index", 0)
            
            # Update both steps: swap their indices
            # Update target step
            update_url = f"{api_base}/projects/{self.project_id}/steps/{step_id}"
            update_data = {"Index": swap_index_value}
            update_response = requests.patch(update_url, params=params, headers=headers, json=update_data, verify=False, timeout=10)
            
            if not update_response.ok:
                error_text = update_response.text[:200] if update_response.text else "Unknown error"
                raise UserError(f"Failed to update step index: HTTP {update_response.status_code} - {error_text}")
            
            # Update swap step
            swap_step_id = str(swap_step.get("Id", ""))
            swap_update_url = f"{api_base}/projects/{self.project_id}/steps/{swap_step_id}"
            swap_update_data = {"Index": target_index_value}
            swap_update_response = requests.patch(swap_update_url, params=params, headers=headers, json=swap_update_data, verify=False, timeout=10)
            
            if not swap_update_response.ok:
                error_text = swap_update_response.text[:200] if swap_update_response.text else "Unknown error"
                # Try to revert the first change
                requests.patch(update_url, params=params, headers=headers, json={"Index": target_index_value}, verify=False, timeout=10)
                raise UserError(f"Failed to update swap step index: HTTP {swap_update_response.status_code} - {error_text}")
            
            # Reload steps to show updated order
            time.sleep(0.5)
            self.action_load_steps()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': f'Step moved {direction} successfully. Steps list updated.',
                    'type': 'success',
                    'sticky': False,
                }
            }
        except Exception as e:
            _logger.error("Error moving step: %s", e, exc_info=True)
            raise UserError(f"Error moving step: {str(e)}")
    
    
    def action_add_step(self):
        """Step 2b: Add a job step to the project - independent action"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        if not self.step_name:
            raise UserError("Please enter a step name")
        
        if not self.project_id:
            raise UserError("Project information is missing")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        # Build step payload for JOB step
        # Based on manual testing: API returns 500 error BUT steps ARE created successfully
        # Use string IDs (matching API response format) - ProcessId and ParentStepId as strings
        step_data = {
            "Type": "Job",  # Must be "Job" for job steps
            "Name": self.step_name,
            "StepType": self.step_type,
            "ProcessId": "0",  # String "0" (matching API response format)
            "Index": self.index if self.index > 0 else 0,
            "ForAllVariants": True,
            "VariantIds": [],
            "TextInstruction": {},
            "ImageInstructionId": "0",  # String "0" (matching API response format)
            "ChildStepOrder": "None" if self.step_type != "COMPOSITE" else "Sequential",
            "StepControlflow": "None",
            "StepConditions": [],
            "Comment": None
        }
        
        # Handle ParentStepId - must be a valid step ID (string, matching API format)
        if self.parent_step_id and self.parent_step_id.strip():
            # Keep as string (matching API response format)
            step_data["ParentStepId"] = self.parent_step_id.strip()
        else:
            # Auto-detect parent step: find the root composite step
            try:
                url = f"{api_base}/projects/{self.project_id}/steps/"
                params = {"apiKey": api_key}
                headers = {"Content-Type": "application/json"}
                response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if response.ok:
                    existing_steps = response.json()
                    if isinstance(existing_steps, list) and existing_steps:
                        # Filter job steps: Type="Job" OR ProcessId is 0/null/empty
                        job_steps = []
                        for s in existing_steps:
                            step_type = s.get("Type", "")
                            process_id = s.get("ProcessId")
                            if step_type == "Job" or not process_id or process_id == "0" or process_id == 0:
                                job_steps.append(s)
                        
                        if job_steps:
                            # Find the root composite step (Type="Job", StepType="COMPOSITE", ParentStepId="0")
                            root_composite = None
                            for step in job_steps:
                                step_type = step.get("Type", "")
                                step_step_type = step.get("StepType", "")
                                parent_id = step.get("ParentStepId", "0")
                                # Root composite: Type="Job", StepType="COMPOSITE", ParentStepId="0"
                                if (step_type == "Job" and 
                                    step_step_type == "COMPOSITE" and 
                                    (not parent_id or parent_id == "0" or parent_id == 0)):
                                    root_composite = step.get("Id")
                                    break
                            
                            if root_composite:
                                # Use root composite step as parent
                                # Keep as string (matching API response format)
                                step_data["ParentStepId"] = str(root_composite) if not isinstance(root_composite, str) else root_composite
                                _logger.info("[ARKITE] Using root composite step %s as parent", step_data["ParentStepId"])
                            else:
                                # Fallback: find any root step (ParentStepId="0")
                                for step in job_steps:
                                    parent_id = step.get("ParentStepId", "0")
                                    if not parent_id or parent_id == "0" or parent_id == 0:
                                        step_id = step.get("Id")
                                        step_data["ParentStepId"] = str(step_id) if not isinstance(step_id, str) else step_id
                                        break
                                else:
                                    # Last resort: use first job step as parent
                                    step_id = job_steps[0].get("Id")
                                    step_data["ParentStepId"] = str(step_id) if not isinstance(step_id, str) else step_id
                        else:
                            # No existing job steps - cannot add step without a parent
                            raise UserError("No existing job steps found. Please create a root composite step in Arkite UI first, or specify a Parent Step ID.")
                    else:
                        raise UserError("No steps found in project. Please create a root composite step in Arkite UI first, or specify a Parent Step ID.")
                else:
                    error_text = response.text[:200] if response.text else "Unknown error"
                    raise UserError(f"Failed to fetch existing steps: HTTP {response.status_code}\n{error_text}")
            except UserError:
                raise
            except Exception as e:
                _logger.error("Could not determine parent step: %s", e, exc_info=True)
                raise UserError(f"Could not determine parent step. Please specify a Parent Step ID manually. Error: {str(e)}")
        
        # Add optional fields based on step type
        if self.step_instruction and self.step_type == 'WORK_INSTRUCTION':
            # TextInstruction should be an object with language codes
            step_data["TextInstruction"] = {
                "en-US": self.step_instruction
            }
        # Note: Even if empty, TextInstruction should be {} (empty object), not omitted
        
        if self.detection_id and self.step_type in ['TOOL_PLACING', 'TOOL_TAKING', 'OBJECT_PLACING', 'OBJECT_TAKING', 
                                                     'PICKING_BIN_PLACING', 'PICKING_BIN_TAKING', 'ACTIVITY', 
                                                     'CHECK_NO_CHANGE_ZONE', 'VIRTUAL_BUTTON_PRESS', 'MATERIAL_GRAB']:
            # Keep as string (matching API format)
            step_data["DetectionId"] = str(self.detection_id).strip() if self.detection_id else None
        
        if self.material_id and self.step_type == 'MATERIAL_GRAB':
            # Keep as string (matching API format)
            step_data["MaterialId"] = str(self.material_id).strip() if self.material_id else None
        
        if self.button_id and self.step_type == 'VIRTUAL_BUTTON_PRESS':
            # Keep as string (matching API format)
            step_data["ButtonId"] = str(self.button_id).strip() if self.button_id else None
        
        if self.index > 0:
            step_data["Index"] = self.index
        
        # Add step via API
        try:
            url = f"{api_base}/projects/{self.project_id}/steps/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("[ARKITE] Adding job step to project %s", self.project_id)
            _logger.debug("[ARKITE] Step payload: %s", json.dumps(step_data, indent=2))
            # API expects an array of steps
            response = requests.post(url, params=params, json=[step_data], headers=headers, verify=False, timeout=10)
            
            # IMPORTANT: Arkite API has a bug - it creates the step successfully but returns 500 error
            # So we need to verify if the step was actually created even if we get an error
            step_created = False
            created_step_id = None
            
            if response.ok:
                # Success response
                created_steps = response.json()
                if isinstance(created_steps, list) and created_steps:
                    created_step_id = created_steps[0].get("Id", "Unknown")
                    step_created = True
                elif isinstance(created_steps, dict):
                    created_step_id = created_steps.get("Id", "Unknown")
                    step_created = True
            else:
                # Even if we get an error, check if step was created (API bug)
                _logger.warning("[ARKITE] API returned error, but checking if step was created anyway...")
                error_text = response.text[:500] if response.text else "Unknown error"
                
                # Wait a moment for step to be created
                import time
                time.sleep(1)
                
                # Verify by fetching steps and checking if our step name exists
                verify_url = f"{api_base}/projects/{self.project_id}/steps/"
                verify_response = requests.get(verify_url, params=params, headers=headers, verify=False, timeout=10)
                if verify_response.ok:
                    all_steps = verify_response.json()
                    # Find step with our name and parent
                    parent_id = step_data.get("ParentStepId")
                    matching_steps = [s for s in all_steps 
                                     if s.get("Name") == self.step_name 
                                     and str(s.get("ParentStepId")) == str(parent_id)]
                    if matching_steps:
                        # Step was created despite the error!
                        created_step_id = matching_steps[0].get("Id", "Unknown")
                        step_created = True
                        _logger.info("[ARKITE] Step was created successfully despite API error (ID: %s)", created_step_id)
            
            if step_created:
                # Save step name for notification
                step_name_saved = self.step_name
                
                # Clear only step input fields (keep project loaded, keep steps list)
                self.write({
                    'step_name': "",
                    'step_instruction': "",
                    'parent_step_id': "",
                    'detection_id': "",
                    'material_id': "",
                    'button_id': "",
                    'index': 0
                })
                
                # Automatically reload steps to show the new one
                # Wait a moment for API to process
                time.sleep(0.5)
                self.action_load_steps()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': f'Step "{step_name_saved}" added successfully (ID: {created_step_id}). Steps list updated. You can add another step.',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                error_text = response.text[:500] if response.text else "Unknown error"
                _logger.error("[ARKITE] Failed to add step: HTTP %s - %s", response.status_code, error_text)
                raise UserError(f"Failed to add step: HTTP {response.status_code}\n{error_text}\n\nNote: The Arkite API may have a bug where it returns an error even when steps are created. Please verify if the step was actually created.")
        except requests.exceptions.RequestException as e:
            _logger.error("Network error adding step: %s", e)
            raise UserError(f"Network error: {str(e)}")
        except Exception as e:
            _logger.error("Error adding step: %s", e, exc_info=True)
            raise UserError(f"Error adding step: {str(e)}")
    
    def action_load_variants(self):
        """Step 3a: Load existing variants for the project"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            url = f"{api_base}/projects/{self.project_id}/variants/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("[ARKITE] Fetching variants for project %s", self.project_id)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            
            if response.ok:
                variants = response.json()
                if isinstance(variants, list):
                    # Clear existing variants
                    self.variant_ids.unlink()
                    
                    # Create variant records
                    variant_records = []
                    for v in variants:
                        variant_id = str(v.get("Id", ""))
                        variant_name = v.get("Name", "Unnamed")
                        variant_desc = v.get("Description", "")
                        
                        variant_temp = self.env['product_module.arkite.variant.temp'].create({
                            'wizard_id': self.id,
                            'variant_id': variant_id,
                            'name': variant_name,
                            'description': variant_desc
                        })
                        variant_records.append(variant_temp.id)
                    
                    # Also update available_variant_ids for Step 4
                    self.available_variant_ids = [(6, 0, variant_records)]
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Success',
                            'message': f'Loaded {len(variant_records)} variant(s)',
                            'type': 'success',
                        }
                    }
                else:
                    self.variant_ids.unlink()
                    # Reload form even if no variants found (to clear old data)
                    return {'type': 'ir.actions.client', 'tag': 'reload'}
            else:
                error_text = response.text[:200] if response.text else "Unknown error"
                raise UserError(f"Failed to fetch variants: HTTP {response.status_code} - {error_text}")
        except Exception as e:
            _logger.error("Error loading variants: %s", e)
            raise UserError(f"Error loading variants: {str(e)}")
    
    def action_add_variant(self):
        """Step 3b: Add a single variant to the project"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        if not self.variant_name:
            raise UserError("Please enter a variant name")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            # Check if variant already exists
            url = f"{api_base}/projects/{self.project_id}/variants/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if response.ok:
                existing_variants = response.json()
                if isinstance(existing_variants, list):
                    for var in existing_variants:
                        if var.get("Name", "").upper() == self.variant_name.upper():
                            raise UserError(f"Variant '{self.variant_name}' already exists in this project")
            
            # Create variant
            variant_data = {
                "Type": "Variant",
                "Name": self.variant_name,
                "Description": self.variant_description or f"Variant {self.variant_name}"
            }
            
            response = requests.post(url, params=params, headers=headers, json=[variant_data], verify=False, timeout=10)
            
            variant_name_saved = self.variant_name  # Save before clearing
            
            # IMPORTANT: Arkite API may have a bug - it might create the variant successfully but return 500 error
            # So we need to verify if the variant was actually created even if we get an error
            if response.ok:
                created = response.json()
                variant_id = "N/A"
                
                if isinstance(created, list) and len(created) > 0:
                    variant_id = created[0].get("Id", "N/A")
                elif isinstance(created, dict):
                    variant_id = created.get("Id", "N/A")
                
                # Clear fields
                self.write({
                    'variant_name': '',
                    'variant_description': ''
                })
                
                # Reload variants
                time.sleep(0.5)
                self.action_load_variants()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': f'Variant "{variant_name_saved}" added successfully (ID: {variant_id}). Variants list updated.',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                # API returned an error - verify if variant was actually created
                error_text = response.text[:500] if response.text else "Unknown error"
                _logger.warning("[ARKITE] Variant creation returned HTTP %s, but verifying if variant was actually created: %s", response.status_code, error_text)
                
                # Wait a moment for API to process
                time.sleep(1)
                
                # Verify by fetching variants
                verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if verify_response.ok:
                    existing_variants = verify_response.json()
                    if isinstance(existing_variants, list):
                        for var in existing_variants:
                            if var.get("Name", "").upper() == variant_name_saved.upper():
                                variant_id = var.get("Id", "N/A")
                                _logger.info("[ARKITE] Variant was created despite API error (ID: %s)", variant_id)
                                
                                # Clear fields
                                self.write({
                                    'variant_name': '',
                                    'variant_description': ''
                                })
                                
                                # Reload variants
                                self.action_load_variants()
                                
                                return {
                                    'type': 'ir.actions.client',
                                    'tag': 'display_notification',
                                    'params': {
                                        'title': 'Success',
                                        'message': f'Variant "{variant_name_saved}" added successfully (ID: {variant_id}) despite API error. Variants list updated.',
                                        'type': 'success',
                                        'sticky': False,
                                    }
                                }
                
                # Variant was not created - this is a real error
                _logger.error("[ARKITE] Failed to add variant: HTTP %s - %s", response.status_code, error_text)
                
                # The error message suggests there's an issue with steps in the project
                if "should link to job" in error_text:
                    raise UserError(f"Failed to add variant: The project has invalid step configuration.\n\nError: {error_text}\n\nPlease fix the step configuration in Arkite UI first. The error suggests a step (Id: 4098507055823504094) needs to be properly linked to a job.")
                else:
                    raise UserError(f"Failed to add variant: HTTP {response.status_code}\n{error_text}")
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error adding variant: %s", e, exc_info=True)
            raise UserError(f"Error adding variant: {str(e)}")
    
    def action_add_variants_batch(self):
        """Step 3c: Add multiple variants at once"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        if not self.variant_names_batch:
            raise UserError("Please enter variant names (separated by commas)")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            # Parse variant names
            variant_names = [name.strip() for name in self.variant_names_batch.split(',') if name.strip()]
            if not variant_names:
                raise UserError("No valid variant names found. Please enter names separated by commas.")
            
            # Check existing variants
            url = f"{api_base}/projects/{self.project_id}/variants/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            existing_variant_names = set()
            if response.ok:
                existing_variants = response.json()
                if isinstance(existing_variants, list):
                    for var in existing_variants:
                        existing_variant_names.add(var.get("Name", "").upper())
            
            # Filter out existing variants
            variants_to_add = []
            skipped = []
            for name in variant_names:
                if name.upper() in existing_variant_names:
                    skipped.append(name)
                else:
                    variants_to_add.append({
                        "Type": "Variant",
                        "Name": name,
                        "Description": f"Variant {name}"
                    })
            
            if skipped:
                _logger.info("Skipping %d existing variants: %s", len(skipped), skipped)
            
            if not variants_to_add:
                raise UserError(f"All variants already exist: {', '.join(variant_names)}")
            
            # Create variants
            response = requests.post(url, params=params, headers=headers, json=variants_to_add, verify=False, timeout=10)
            
            if response.ok:
                created = response.json()
                created_count = len(created) if isinstance(created, list) else 1
                
                # Clear field
                self.write({'variant_names_batch': ''})
                
                # Reload variants
                time.sleep(0.5)
                self.action_load_variants()
                
                message = f'Successfully added {created_count} variant(s): {", ".join([v.get("Name", "Unknown") for v in (created if isinstance(created, list) else [created])])}'
                if skipped:
                    message += f'\nSkipped {len(skipped)} existing variant(s): {", ".join(skipped)}'
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': message,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                error_text = response.text[:500] if response.text else "Unknown error"
                _logger.error("[ARKITE] Failed to add variants: HTTP %s - %s", response.status_code, error_text)
                raise UserError(f"Failed to add variants: HTTP {response.status_code}\n{error_text}")
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error adding variants: %s", e, exc_info=True)
            raise UserError(f"Error adding variants: {str(e)}")
    
    def action_load_processes(self):
        """Load processes and populate One2many field with steps for selected process"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        if not self.selected_process_id:
            raise UserError("Please select a process first. Click 'Load Process List' to see available processes.")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            # Get all steps for the selected process
            url_steps = f"{api_base}/projects/{self.project_id}/steps/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response_steps = requests.get(url_steps, params=params, headers=headers, verify=False, timeout=10)
            if not response_steps.ok:
                raise UserError(f"Failed to fetch steps: HTTP {response_steps.status_code}")
            
            all_steps = response_steps.json()
            if not isinstance(all_steps, list):
                raise UserError("Unexpected response format for steps")
            
            # Filter steps for selected process
            selected_process_id_str = str(self.selected_process_id) if self.selected_process_id else ""
            process_steps = [s for s in all_steps if str(s.get("ProcessId", "")) == selected_process_id_str]
            process_steps.sort(key=lambda x: x.get("Index", 0))
            
            # Get all variants
            url_variants = f"{api_base}/projects/{self.project_id}/variants/"
            response_variants = requests.get(url_variants, params=params, headers=headers, verify=False, timeout=10)
            
            # Create/update variant temp records
            variant_records = []
            if response_variants.ok:
                variants = response_variants.json()
                if isinstance(variants, list):
                    for v in variants:
                        variant_id = str(v.get("Id", ""))
                        # Find or create variant temp record
                        variant_temp = self.env['product_module.arkite.variant.temp'].search([
                            ('variant_id', '=', variant_id),
                            ('wizard_id', '=', self.id)
                        ], limit=1)
                        if not variant_temp:
                            variant_temp = self.env['product_module.arkite.variant.temp'].create({
                                'wizard_id': self.id,
                                'variant_id': variant_id,
                                'name': v.get("Name", "Unknown"),
                                'description': v.get("Description", "")
                            })
                        variant_records.append(variant_temp.id)
            
            # Clear existing process steps
            self.process_step_ids.unlink()
            
            # Create process step records
            step_records = []
            for idx, step in enumerate(process_steps):
                step_id = str(step.get("Id", ""))
                step_name = step.get("Name", "Unnamed Step")
                step_type = step.get("StepType", "UNKNOWN")
                variant_ids = step.get("VariantIds", [])
                for_all_variants = step.get("ForAllVariants", False)
                step_index = step.get("Index", idx * 10)
                
                # Get variant records for this step
                step_variant_records = []
                for vid in variant_ids:
                    variant_temp = self.env['product_module.arkite.variant.temp'].search([
                        ('variant_id', '=', str(vid)),
                        ('wizard_id', '=', self.id)
                    ], limit=1)
                    if variant_temp:
                        step_variant_records.append(variant_temp.id)
                
                step_record = self.env['product_module.arkite.process.step'].create({
                    'wizard_id': self.id,
                    'process_id': str(self.selected_process_id),
                    'step_id': step_id,
                    'step_name': step_name,
                    'step_type': step_type,
                    'sequence': step_index,
                    'index': step_index,
                    'variant_ids': [(6, 0, step_variant_records)],
                    'for_all_variants': for_all_variants
                })
                step_records.append(step_record.id)
            
            # Update available variants
            self.available_variant_ids = [(6, 0, variant_records)]
            
            # Reload form to show the new records
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error loading processes: %s", e, exc_info=True)
            raise UserError(f"Error loading processes: {str(e)}")
    
    def action_load_process_list(self):
        """Load list of available processes"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            url = f"{api_base}/projects/{self.project_id}/processes/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if not response.ok:
                raise UserError(f"Failed to fetch processes: HTTP {response.status_code}")
            
            processes = response.json()
            if not isinstance(processes, list):
                raise UserError("Unexpected response format for processes")
            
            if not processes:
                raise UserError("No processes found in this project")
            
            # Clear existing process records
            self.available_process_ids.unlink()
            
            # Create process temp records
            process_records = []
            for p in processes:
                process_id = str(p.get("Id", ""))
                process_name = p.get("Name", "Unnamed Process")
                process_comment = p.get("Comment", "")
                
                process_temp = self.env['product_module.arkite.process.temp'].create({
                    'wizard_id': self.id,
                    'process_id': process_id,
                    'name': process_name,
                    'comment': process_comment
                })
                process_records.append(process_temp.id)
            
            # Auto-select if only one process
            if len(process_records) == 1:
                process_temp = self.env['product_module.arkite.process.temp'].browse(process_records[0])
                self.selected_process_id = process_temp.process_id
                # selected_process_selection temporarily removed
                return self.action_load_processes()
            
            # Reload form to show process selection
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error loading process list: %s", e, exc_info=True)
            raise UserError(f"Error loading process list: {str(e)}")
    
    def write(self, vals):
        """Override write to handle sequence changes from drag-and-drop"""
        result = super().write(vals)
        
        # If job_step_ids sequence changed, update Arkite
        if 'job_step_ids' in vals and self.job_step_ids:
            api_base = os.getenv('ARKITE_API_BASE')
            api_key = os.getenv('ARKITE_API_KEY')
            
            if api_base and api_key:
                try:
                    # Sort by sequence and update Arkite API
                    sorted_steps = self.job_step_ids.sorted('sequence')
                    
                    # Update indices in Arkite based on new sequence
                    for idx, step_record in enumerate(sorted_steps):
                        new_index = idx * 10  # Use increments of 10 for flexibility
                        if step_record.index != new_index:
                            url = f"{api_base}/projects/{self.project_id}/steps/{step_record.step_id}"
                            params = {"apiKey": api_key}
                            headers = {"Content-Type": "application/json"}
                            
                            # Get current step data
                            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                            if response.ok:
                                step_data = response.json()
                                step_data["Index"] = new_index
                                patch_response = requests.patch(url, params=params, headers=headers, json=step_data, verify=False, timeout=10)
                                if patch_response.ok:
                                    step_record.index = new_index
                except Exception as e:
                    _logger.error("Error updating job step sequence: %s", e)
        
        # If process_step_ids sequence changed, update Arkite
        if 'process_step_ids' in vals and self.process_step_ids and self.selected_process_id:
            api_base = os.getenv('ARKITE_API_BASE')
            api_key = os.getenv('ARKITE_API_KEY')
            
            if api_base and api_key:
                try:
                    # Sort by sequence and update Arkite API
                    sorted_steps = self.process_step_ids.sorted('sequence')
                    
                    # Update indices in Arkite based on new sequence
                    for idx, step_record in enumerate(sorted_steps):
                        new_index = idx * 10  # Use increments of 10 for flexibility
                        if step_record.index != new_index:
                            url = f"{api_base}/projects/{self.project_id}/steps/{step_record.step_id}"
                            params = {"apiKey": api_key}
                            headers = {"Content-Type": "application/json"}
                            
                            # Get current step data
                            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                            if response.ok:
                                step_data = response.json()
                                step_data["Index"] = new_index
                                patch_response = requests.patch(url, params=params, headers=headers, json=step_data, verify=False, timeout=10)
                                if patch_response.ok:
                                    step_record.index = new_index
                except Exception as e:
                    _logger.error("Error updating step sequence: %s", e)
        
        return result
    
    def action_move_process_step_sequence(self, step_record_id, direction):
        """Move step up or down (called from buttons)"""
        step_record = self.env['product_module.arkite.process.step'].browse(step_record_id)
        if not step_record.exists():
            raise UserError("Step record not found")
        
        # Get all steps for this process, sorted
        all_steps = self.process_step_ids.filtered(lambda s: s.process_id == step_record.process_id).sorted('sequence')
        current_idx = None
        for idx, s in enumerate(all_steps):
            if s.id == step_record.id:
                current_idx = idx
                break
        
        if current_idx is None:
            raise UserError("Step not found in list")
        
        if direction == 'up' and current_idx > 0:
            # Swap with previous
            prev_step = all_steps[current_idx - 1]
            step_record.sequence, prev_step.sequence = prev_step.sequence, step_record.sequence
        elif direction == 'down' and current_idx < len(all_steps) - 1:
            # Swap with next
            next_step = all_steps[current_idx + 1]
            step_record.sequence, next_step.sequence = next_step.sequence, step_record.sequence
        
        # Trigger onchange to update Arkite
        self._onchange_step_sequence()
        
        return {'type': 'ir.actions.client', 'tag': 'reload'}
    
    def action_show_variant_selection_for_step(self, step_id, step_name):
        """Show variant selection for a step - opens a wizard or updates the step's variant_ids"""
        # This will be handled by the tree view's many2many_tags widget
        return {'type': 'ir.actions.client', 'tag': 'reload'}
    
    def action_show_variant_selection(self):
        """Show interactive variant selection interface for a step"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        # Get step_id from context
        step_id = self.env.context.get('step_id')
        step_name = self.env.context.get('step_name', 'Unknown Step')
        
        if not step_id:
            raise UserError("Step ID not provided")
        
        # Load variants data - now using available_variant_ids Many2many field
        variants_data = []
        # Note: This method is deprecated - variant selection now uses native many2many_tags widget
        
        # Get current step to see which variants are already assigned
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            url = f"{api_base}/projects/{self.project_id}/steps/{step_id}"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            current_variant_ids = set()
            for_all_variants = False
            
            if response.ok:
                step_data = response.json()
                current_variant_ids = set(str(vid) for vid in step_data.get("VariantIds", []))
                for_all_variants = step_data.get("ForAllVariants", False)
            
            # Build selection interface
            html = f'<div style="padding: 16px; background-color: #f8f9fa; border-radius: 8px;">'
            html += f'<h4 style="margin-top: 0;">Assign Variants to Step: <strong>{step_name}</strong></h4>'
            html += f'<p style="font-size: 12px; color: #666; margin-bottom: 16px;">Step ID: <code>{step_id}</code></p>'
            
            if for_all_variants:
                html += '<div class="alert alert-info" style="margin-bottom: 16px; padding: 8px; font-size: 12px;">'
                html += 'This step is currently set to "For All Variants". Assigning specific variants will override this setting.'
                html += '</div>'
            
            if not variants_data:
                html += '<p style="color: #dc3545;">No variants available. Please create variants in Step 3 first.</p>'
            else:
                html += '<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 10px; margin-bottom: 16px;">'
                for variant in variants_data:
                    variant_id = variant.get('id', '')
                    variant_name = variant.get('name', 'Unknown')
                    variant_desc = variant.get('description', '')
                    is_selected = variant_id in current_variant_ids
                    
                    html += f'<div style="padding: 12px; border: 2px solid {"#28a745" if is_selected else "#dee2e6"}; border-radius: 6px; background-color: {"#d4edda" if is_selected else "white"};">'
                    html += f'<div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 8px;">'
                    html += f'<div style="flex: 1;">'
                    html += f'<strong style="font-size: 14px; color: {"#155724" if is_selected else "#333"};">{variant_name}</strong>'
                    if variant_desc:
                        html += f'<br/><small style="color: #666; font-size: 11px;">{variant_desc}</small>'
                    html += f'<br/><small style="color: #999; font-family: monospace; font-size: 9px;">ID: {variant_id}</small>'
                    html += '</div>'
                    
                    # Toggle button
                    if is_selected:
                        html += f'<button name="action_toggle_variant" type="object" '
                        html += f'context="{{&quot;step_id&quot;: &quot;{step_id}&quot;, &quot;variant_id&quot;: &quot;{variant_id}&quot;, &quot;action&quot;: &quot;remove&quot;}}" '
                        html += f'class="btn btn-sm btn-danger" style="padding: 4px 8px; font-size: 11px; margin-left: 8px;" title="Remove Variant">✕</button>'
                    else:
                        html += f'<button name="action_toggle_variant" type="object" '
                        html += f'context="{{&quot;step_id&quot;: &quot;{step_id}&quot;, &quot;variant_id&quot;: &quot;{variant_id}&quot;, &quot;action&quot;: &quot;add&quot;}}" '
                        html += f'class="btn btn-sm btn-success" style="padding: 4px 8px; font-size: 11px; margin-left: 8px;" title="Add Variant">+</button>'
                    html += '</div>'
                    html += '</div>'
                html += '</div>'
                
                html += '<div style="text-align: center; margin-top: 16px; padding-top: 16px; border-top: 1px solid #dee2e6;">'
                html += f'<button name="action_clear_variant_selection" type="object" '
                html += f'context="{{&quot;step_id&quot;: &quot;{step_id}&quot;}}" '
                html += f'class="btn btn-secondary" style="padding: 10px 20px; font-size: 14px; margin: 0 5px;">'
                html += 'Clear All Variants</button>'
                html += f' <button name="action_set_all_variants" type="object" '
                html += f'context="{{&quot;step_id&quot;: &quot;{step_id}&quot;}}" '
                html += f'class="btn btn-info" style="padding: 10px 20px; font-size: 14px; margin: 0 5px;">'
                html += 'Set "For All Variants"</button>'
                html += '</div>'
            
            html += '</div>'
            
            # Note: step_variant_selection_info field removed - using native widgets now
            self.write({
                'selected_step_id': step_id
            })
            
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error showing variant selection: %s", e, exc_info=True)
            raise UserError(f"Error showing variant selection: {str(e)}")
    
    def action_toggle_variant(self):
        """Add or remove a single variant from a step"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        step_id = self.env.context.get('step_id')
        variant_id = self.env.context.get('variant_id')
        action = self.env.context.get('action')  # 'add' or 'remove'
        
        if not step_id or not variant_id or not action:
            raise UserError("Missing parameters")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            # Get current step
            url = f"{api_base}/projects/{self.project_id}/steps/{step_id}"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if not response.ok:
                raise UserError(f"Failed to fetch step: HTTP {response.status_code}")
            
            step_data = response.json()
            current_variant_ids = [str(vid) for vid in step_data.get("VariantIds", [])]
            
            # Add or remove variant
            if action == "add":
                if variant_id not in current_variant_ids:
                    current_variant_ids.append(variant_id)
                    step_data["ForAllVariants"] = False  # Disable ForAllVariants when adding specific variants
            elif action == "remove":
                if variant_id in current_variant_ids:
                    current_variant_ids.remove(variant_id)
            
            # Update step
            step_data["VariantIds"] = current_variant_ids
            
            response = requests.patch(url, params=params, headers=headers, json=step_data, verify=False, timeout=10)
            
            if response.ok:
                # Verify update
                time.sleep(0.3)
                verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if verify_response.ok:
                    # Get step name for re-display
                    step_name = self.env.context.get('step_name', 'Unknown Step')
                    # Reload selection interface and processes
                    time.sleep(0.3)
                    # Re-show selection interface
                    self.env.context = dict(self.env.context, step_id=step_id, step_name=step_name)
                    self.action_show_variant_selection()
                    time.sleep(0.3)
                    self.action_load_processes()
                    
                    action_text = "added to" if action == "add" else "removed from"
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Success',
                            'message': f'Variant {action_text} step',
                            'type': 'success',
                            'sticky': False,
                        }
                    }
            else:
                error_text = response.text[:500] if response.text else "Unknown error"
                raise UserError(f"Failed to update variant: HTTP {response.status_code}\n{error_text}")
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error toggling variant: %s", e, exc_info=True)
            raise UserError(f"Error toggling variant: {str(e)}")
    
    def action_assign_variants_to_step(self):
        """Assign variants to a specific process step"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        if not self.selected_step_id:
            raise UserError("Please enter a Step ID")
        
        if not self.step_variant_ids:
            raise UserError("Please enter Variant IDs (comma-separated)")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            # Parse variant IDs
            variant_id_list = [vid.strip() for vid in self.step_variant_ids.split(',') if vid.strip()]
            if not variant_id_list:
                raise UserError("No valid variant IDs found")
            
            # Get current step
            url = f"{api_base}/projects/{self.project_id}/steps/{step_id}"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if not response.ok:
                raise UserError(f"Failed to fetch step: HTTP {response.status_code}")
            
            step_data = response.json()
            
            # Update step with new variant IDs
            step_data["VariantIds"] = variant_id_list
            step_data["ForAllVariants"] = False  # Set to False when specific variants are assigned
            
            # Update step
            response = requests.patch(
                url,
                params=params,
                headers=headers,
                json=step_data,
                verify=False,
                timeout=10
            )
            
            if response.ok:
                # Verify update (API bug workaround)
                time.sleep(0.5)
                verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if verify_response.ok:
                    updated_step = verify_response.json()
                    updated_variant_ids = updated_step.get("VariantIds", [])
                    if set(str(vid) for vid in updated_variant_ids) == set(variant_id_list):
                        # Reload processes
                        time.sleep(0.5)
                        self.action_load_processes()
                        
                        return {
                            'type': 'ir.actions.client',
                            'tag': 'display_notification',
                            'params': {
                                'title': 'Success',
                                'message': f'Successfully assigned {len(variant_id_list)} variant(s) to step',
                                'type': 'success',
                            }
                        }
                    else:
                        _logger.warning("Variant assignment may have failed - verification mismatch")
                
                # Clear selection interface
                self.write({'step_variant_selection_info': ''})
                # Reload processes anyway
                time.sleep(0.5)
                self.action_load_processes()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': f'Variant assignment completed (please verify)',
                        'type': 'success',
                    }
                }
            else:
                error_text = response.text[:500] if response.text else "Unknown error"
                _logger.error("[ARKITE] Failed to assign variants: HTTP %s - %s", response.status_code, error_text)
                raise UserError(f"Failed to assign variants: HTTP {response.status_code}\n{error_text}")
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error assigning variants: %s", e, exc_info=True)
            raise UserError(f"Error assigning variants: {str(e)}")
    
    def action_move_process_step(self):
        """Move a process step up or down"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        step_id = self.env.context.get('step_id')
        process_id = self.env.context.get('process_id')
        direction = self.env.context.get('direction')
        
        if not step_id or not direction:
            raise UserError("Step ID and direction must be specified")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            # Get all steps for this process
            url = f"{api_base}/projects/{self.project_id}/steps/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if not response.ok:
                raise UserError(f"Failed to fetch steps: HTTP {response.status_code}")
            
            all_steps = response.json()
            if not isinstance(all_steps, list):
                raise UserError("Unexpected response format")
            
            # Filter steps for this process
            process_steps = [s for s in all_steps if str(s.get("ProcessId", "")) == str(process_id)]
            process_steps.sort(key=lambda x: x.get("Index", 0))
            
            # Find target step
            target_step = None
            for s in process_steps:
                if str(s.get("Id", "")) == str(step_id):
                    target_step = s
                    break
            
            if not target_step:
                raise UserError(f"Step with ID {step_id} not found in process")
            
            # Find current position
            current_index = None
            for idx, step in enumerate(process_steps):
                if str(step.get("Id", "")) == str(step_id):
                    current_index = idx
                    break
            
            if current_index is None:
                raise UserError("Step not found in process steps list")
            
            # Determine new position
            if direction == "up" and current_index > 0:
                new_index = current_index - 1
            elif direction == "down" and current_index < len(process_steps) - 1:
                new_index = current_index + 1
            else:
                raise UserError(f"Cannot move step {direction} - already at boundary")
            
            # Get the step we're swapping with
            swap_step = process_steps[new_index]
            target_index_value = target_step.get("Index", 0)
            swap_index_value = swap_step.get("Index", 0)
            
            # Swap indices
            target_step_id = str(target_step.get("Id", ""))
            swap_step_id = str(swap_step.get("Id", ""))
            
            # Update target step
            url_target = f"{api_base}/projects/{self.project_id}/steps/{target_step_id}"
            target_step_data = target_step.copy()
            target_step_data["Index"] = swap_index_value
            response = requests.patch(url_target, params=params, headers=headers, json=target_step_data, verify=False, timeout=10)
            
            if not response.ok:
                raise UserError(f"Failed to update step: HTTP {response.status_code}")
            
            # Update swap step
            url_swap = f"{api_base}/projects/{self.project_id}/steps/{swap_step_id}"
            swap_step_data = swap_step.copy()
            swap_step_data["Index"] = target_index_value
            response = requests.patch(url_swap, params=params, headers=headers, json=swap_step_data, verify=False, timeout=10)
            
            if not response.ok:
                raise UserError(f"Failed to update step: HTTP {response.status_code}")
            
            # Reload processes
            time.sleep(0.5)
            self.action_load_processes()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': f'Step moved {direction} successfully',
                    'type': 'success',
                }
            }
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error moving process step: %s", e, exc_info=True)
            raise UserError(f"Error moving process step: {str(e)}")
    
    def action_clear_variant_selection(self):
        """Clear all variants from a step"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        step_id = self.env.context.get('step_id') or self.selected_step_id
        if not step_id:
            raise UserError("Step ID not provided")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            # Get current step
            url = f"{api_base}/projects/{self.project_id}/steps/{step_id}"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if not response.ok:
                raise UserError(f"Failed to fetch step: HTTP {response.status_code}")
            
            step_data = response.json()
            step_name = step_data.get("Name", "Unknown Step")
            
            # Clear variants
            step_data["VariantIds"] = []
            step_data["ForAllVariants"] = False
            
            # Update step
            response = requests.patch(url, params=params, headers=headers, json=step_data, verify=False, timeout=10)
            
            if response.ok:
                # Verify update
                time.sleep(0.5)
                verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if verify_response.ok:
                    # Clear selection interface and reload
                    time.sleep(0.5)
                    self.action_load_processes()
                    # Note: Variant selection now handled by native many2many_tags widget
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Success',
                            'message': 'All variants cleared from step',
                            'type': 'success',
                        }
                    }
            else:
                error_text = response.text[:500] if response.text else "Unknown error"
                raise UserError(f"Failed to clear variants: HTTP {response.status_code}\n{error_text}")
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error clearing variants: %s", e, exc_info=True)
            raise UserError(f"Error clearing variants: {str(e)}")
    
    def action_set_all_variants(self):
        """Set step to "For All Variants" mode"""
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        step_id = self.env.context.get('step_id') or self.selected_step_id
        if not step_id:
            raise UserError("Step ID not provided")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        try:
            # Get current step
            url = f"{api_base}/projects/{self.project_id}/steps/{step_id}"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if not response.ok:
                raise UserError(f"Failed to fetch step: HTTP {response.status_code}")
            
            step_data = response.json()
            step_name = step_data.get("Name", "Unknown Step")
            
            # Set ForAllVariants
            step_data["ForAllVariants"] = True
            step_data["VariantIds"] = []  # Clear specific variants when using ForAllVariants
            
            # Update step
            response = requests.patch(url, params=params, headers=headers, json=step_data, verify=False, timeout=10)
            
            if response.ok:
                # Verify update
                time.sleep(0.5)
                verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if verify_response.ok:
                    # Clear selection interface and reload
                    time.sleep(0.5)
                    self.action_load_processes()
                    # Note: Variant selection now handled by native many2many_tags widget
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': 'Success',
                            'message': 'Step set to "For All Variants"',
                            'type': 'success',
                        }
                    }
            else:
                error_text = response.text[:500] if response.text else "Unknown error"
                raise UserError(f"Failed to set For All Variants: HTTP {response.status_code}\n{error_text}")
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error setting For All Variants: %s", e, exc_info=True)
            raise UserError(f"Error setting For All Variants: {str(e)}")
