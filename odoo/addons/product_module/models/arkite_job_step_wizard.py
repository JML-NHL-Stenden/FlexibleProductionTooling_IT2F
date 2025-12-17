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
    
    available_processes_info = fields.Html(
        string='Available Processes',
        readonly=True,
        help='List of available processes (jobs) in the project'
    )
    
    existing_steps_info = fields.Html(
        string='Existing Steps',
        readonly=True,
        help='List of existing steps in the process/job'
    )
    
    # For step reordering
    step_order_data = fields.Text(
        string='Step Order Data',
        readonly=True,
        help='JSON data for step reordering (internal use)'
    )
    
    # For move step action
    move_step_id = fields.Char(
        string='Step ID to Move',
        help='Internal field for step reordering'
    )
    
    move_direction = fields.Selection([
        ('up', 'Move Up'),
        ('down', 'Move Down'),
    ], string='Move Direction', help='Internal field for step reordering')
    
    @api.model
    def create(self, vals):
        """Set default values when creating new record"""
        if 'available_projects_info' not in vals:
            vals['available_projects_info'] = '<p style="color: #666; font-size: 12px;">Click "List All Projects" to see available project IDs.</p>'
        if 'available_processes_info' not in vals:
            vals['available_processes_info'] = '<p style="color: #666; font-size: 12px;">Project loaded. You can now view and add steps.</p>'
        if 'existing_steps_info' not in vals:
            vals['existing_steps_info'] = '<p style="color: #666; font-size: 12px;">Click "Refresh Steps List" to see job steps in this project. The list will auto-update after adding steps.</p>'
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
            'available_processes_info': '<p style="color: #666; font-size: 12px;">Project loaded. You can now view and add steps.</p>',
            'existing_steps_info': '<p style="color: #666; font-size: 12px;">Click "Load Existing Steps" to see job steps in this project.</p>'
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
                    
                    if job_steps:
                        # Store step data for reordering
                        step_data_list = []
                        for step in job_steps:
                            step_data_list.append({
                                'Id': str(step.get("Id", "")),
                                'Name': step.get("Name", "Unnamed"),
                                'Index': step.get("Index", 0),
                                'StepType': step.get("StepType", step.get("Type", "N/A")),
                                'ParentStepId': str(step.get("ParentStepId", "0"))
                            })
                        self.write({'step_order_data': json.dumps(step_data_list)})
                        
                        html = '<div style="margin-top: 8px;">'
                        html += f'<p style="font-size: 12px; margin-bottom: 8px;"><strong>Found {len(job_steps)} job step(s) (out of {len(all_steps)} total steps):</strong></p>'
                        html += '<div style="max-height: 400px; overflow-y: auto; border: 1px solid #dee2e6; border-radius: 4px;">'
                        html += '<table style="width: 100%; border-collapse: collapse; font-size: 12px;">'
                        html += '<thead><tr style="background-color: #f8f9fa; position: sticky; top: 0;"><th style="padding: 8px; border: 1px solid #dee2e6;">Index</th><th style="padding: 8px; border: 1px solid #dee2e6;">ID</th><th style="padding: 8px; border: 1px solid #dee2e6;">Name</th><th style="padding: 8px; border: 1px solid #dee2e6;">Step Type</th><th style="padding: 8px; border: 1px solid #dee2e6;">Parent Step ID</th><th style="padding: 8px; border: 1px solid #dee2e6;">Actions</th></tr></thead>'
                        html += '<tbody>'
                        
                        for idx, step in enumerate(job_steps):
                            step_id = step.get("Id", "N/A")
                            step_name = step.get("Name", "Unnamed")
                            step_type = step.get("StepType", step.get("Type", "N/A"))
                            parent_id = step.get("ParentStepId", "0")
                            step_index = step.get("Index", 0)
                            
                            html += f'<tr><td style="padding: 8px; border: 1px solid #dee2e6; text-align: center;"><strong>{step_index}</strong></td>'
                            html += f'<td style="padding: 8px; border: 1px solid #dee2e6; font-family: monospace; font-size: 11px;">{step_id}</td>'
                            html += f'<td style="padding: 8px; border: 1px solid #dee2e6;"><strong>{step_name}</strong></td>'
                            html += f'<td style="padding: 8px; border: 1px solid #dee2e6;">{step_type}</td>'
                            html += f'<td style="padding: 8px; border: 1px solid #dee2e6; font-family: monospace; font-size: 11px;">{parent_id}</td>'
                            html += f'<td style="padding: 8px; border: 1px solid #dee2e6; text-align: center;">'
                            if idx > 0:
                                html += f'<button type="button" class="btn btn-sm btn-secondary" onclick="odoo.define(\'step_reorder\', function(require) {{ var rpc = require(\'web.rpc\'); rpc.query({{model: \'product_module.arkite.job.step.wizard\', method: \'action_move_step\', args: [[{self.id}], \'{step_id}\', \'up\']}}).then(function() {{ location.reload(); }}); }});" style="margin: 2px; padding: 4px 8px; font-size: 11px;">↑</button>'
                            if idx < len(job_steps) - 1:
                                html += f'<button type="button" class="btn btn-sm btn-secondary" onclick="odoo.define(\'step_reorder\', function(require) {{ var rpc = require(\'web.rpc\'); rpc.query({{model: \'product_module.arkite.job.step.wizard\', method: \'action_move_step\', args: [[{self.id}], \'{step_id}\', \'down\']}}).then(function() {{ location.reload(); }}); }});" style="margin: 2px; padding: 4px 8px; font-size: 11px;">↓</button>'
                            html += '</td></tr>'
                        
                        html += '</tbody></table>'
                        html += '</div>'
                        html += '<p style="font-size: 11px; color: #666; margin-top: 8px;"><em>Steps are sorted by Index. Use the "Reorder Steps" section below to change step order.</em></p>'
                        html += '</div>'
                        self.write({'existing_steps_info': html})
                    else:
                        self.write({'existing_steps_info': f'<p style="color: #666; font-size: 12px;">No job steps found. You can add the first step. (Found {len(all_steps)} total steps, all are process steps.)</p>'})
                else:
                    self.write({'existing_steps_info': '<p style="color: #dc3545; font-size: 12px;">Unexpected response format.</p>'})
            else:
                error_text = response.text[:200] if response.text else "Unknown error"
                self.write({'existing_steps_info': f'<p style="color: #dc3545; font-size: 12px;">Failed to fetch steps: HTTP {response.status_code} - {error_text}</p>'})
            
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        except Exception as e:
            _logger.error("Error loading steps: %s", e)
            raise UserError(f"Error loading steps: {str(e)}")
    
    def action_move_step(self):
        """Move a step up or down in the order by updating its Index"""
        if not self.move_step_id or not self.move_direction:
            raise UserError("Step ID and direction must be specified")
        
        step_id = self.move_step_id
        direction = self.move_direction
        
        if not self.project_loaded or not self.project_id:
            raise UserError("Please load a project first (Step 1)")
        
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
            
            # Clear move fields
            self.write({
                'move_step_id': '',
                'move_direction': False
            })
            
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
