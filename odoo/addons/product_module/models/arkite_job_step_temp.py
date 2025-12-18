# product_module/models/arkite_job_step_temp.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import os
import logging
import time

_logger = logging.getLogger(__name__)


class ArkiteJobStepTemp(models.TransientModel):
    """Temporary model for displaying job steps in tree view"""
    _name = 'product_module.arkite.job.step.temp'
    _description = 'Arkite Job Step (Temporary)'
    _order = 'sequence, id'
    _rec_name = 'step_name'
    
    wizard_id = fields.Many2one('product_module.arkite.job.step.wizard', string='Wizard', required=True, ondelete='cascade')
    
    # Step data
    step_id = fields.Char(string='Step ID', readonly=True, help='Arkite Step ID (auto-filled when loaded from Arkite)')
    step_name = fields.Char(string='Step Name', required=True)
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
        ('COMPONENT', 'Component'),
    ], string='Step Type', required=True, default='WORK_INSTRUCTION', help='Type of step to create')
    step_instruction = fields.Text(string='Instruction Text', help='Text instruction (for WORK_INSTRUCTION type)')
    sequence = fields.Integer(string='Sequence', default=10)
    index = fields.Integer(string='Index', readonly=True)
    parent_step_id = fields.Char(string='Parent Step ID', help='Leave empty to auto-detect root step')
    detection_id = fields.Char(string='Detection ID', help='Required for some step types')
    material_id = fields.Char(string='Material ID', help='Required for MATERIAL_GRAB')
    button_id = fields.Char(string='Button ID', help='Required for VIRTUAL_BUTTON_PRESS')
    
    @api.model
    def create(self, vals):
        """Override create to create step in Arkite if step_id is empty (new step)"""
        # If step_id is provided, it's a loaded step - just create the record
        if vals.get('step_id'):
            return super().create(vals)
        
        # Otherwise, create a new step in Arkite
        wizard = self.env['product_module.arkite.job.step.wizard'].browse(vals.get('wizard_id'))
        if not wizard or not wizard.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        # Use the wizard's action_add_step logic to create the step
        # We'll create the step via API and then update vals with the returned step_id
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        # Build step payload
        step_data = {
            "Type": "Job",
            "Name": vals.get('step_name', 'Unnamed Step'),
            "StepType": vals.get('step_type', 'WORK_INSTRUCTION'),
            "ProcessId": "0",
            "Index": vals.get('sequence', 0) if vals.get('sequence', 0) > 0 else 0,
            "ForAllVariants": True,
            "VariantIds": [],
            "TextInstruction": {},
            "ImageInstructionId": "0",
            "ChildStepOrder": "None" if vals.get('step_type') != "COMPOSITE" else "Sequential",
            "StepControlflow": "None",
            "StepConditions": [],
            "Comment": None
        }
        
        # Handle parent step - only set if we have a valid parent ID
        parent_step_id = None
        if vals.get('parent_step_id'):
            parent_val = vals['parent_step_id']
            if isinstance(parent_val, str) and parent_val.strip() and parent_val.strip() != "0":
                parent_step_id = parent_val.strip()
        
        # Auto-detect parent if not provided
        if not parent_step_id:
            try:
                url = f"{api_base}/projects/{wizard.project_id}/steps/"
                params = {"apiKey": api_key}
                headers = {"Content-Type": "application/json"}
                response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if response.ok:
                    existing_steps = response.json()
                    if isinstance(existing_steps, list) and existing_steps:
                        job_steps = [s for s in existing_steps if s.get("Type") == "Job" or not s.get("ProcessId") or s.get("ProcessId") == "0"]
                        if job_steps:
                            # Find root composite or first job step
                            root_composite = next((s.get("Id") for s in job_steps if s.get("StepType") == "COMPOSITE" and (not s.get("ParentStepId") or s.get("ParentStepId") == "0" or str(s.get("ParentStepId")) == "0")), None)
                            if root_composite:
                                parent_step_id = str(root_composite)
                                _logger.info("[ARKITE] Auto-detected root composite as parent: %s", parent_step_id)
                            else:
                                # Use first job step as parent
                                first_step_id = job_steps[0].get("Id", "")
                                if first_step_id and str(first_step_id) != "0":
                                    parent_step_id = str(first_step_id)
                                    _logger.info("[ARKITE] Auto-detected first job step as parent: %s", parent_step_id)
            except Exception as e:
                _logger.error("Error auto-detecting parent step: %s", e)
        
        # Only add ParentStepId to payload if we have a valid parent ID (not "0" or empty)
        if parent_step_id and str(parent_step_id) != "0" and str(parent_step_id).strip():
            step_data["ParentStepId"] = str(parent_step_id).strip()
            _logger.info("[ARKITE] Setting ParentStepId to: %s", step_data["ParentStepId"])
        else:
            _logger.info("[ARKITE] No valid parent step found, omitting ParentStepId (creating as root step)")
            # Explicitly ensure ParentStepId is not in the payload
            if "ParentStepId" in step_data:
                del step_data["ParentStepId"]
        
        # Add optional fields
        if vals.get('step_instruction') and vals.get('step_type') == 'WORK_INSTRUCTION':
            step_data["TextInstruction"] = {"en-US": vals['step_instruction']}
        
        if vals.get('detection_id'):
            step_data["DetectionId"] = vals['detection_id']
        if vals.get('material_id'):
            step_data["MaterialId"] = vals['material_id']
        if vals.get('button_id'):
            step_data["ButtonId"] = vals['button_id']
        
        # Create step in Arkite (API expects an array)
        url = f"{api_base}/projects/{wizard.project_id}/steps/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        # Log the payload before sending
        _logger.info("[ARKITE] Creating job step with payload: %s", step_data)
        
        try:
            # API expects an array of steps
            response = requests.post(url, params=params, json=[step_data], headers=headers, verify=False, timeout=10)
            
            # IMPORTANT: Arkite API has a bug - it creates the step successfully but returns 500 error
            step_created = False
            created_step_id = None
            
            if response.ok:
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
                time.sleep(1)
                
                # Verify by fetching steps
                verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if verify_response.ok:
                    all_steps = verify_response.json()
                    parent_id = step_data.get("ParentStepId", "")
                    matching_steps = [s for s in all_steps 
                                     if s.get("Name") == step_data["Name"] 
                                     and str(s.get("ParentStepId", "")) == str(parent_id)]
                    if matching_steps:
                        created_step_id = matching_steps[0].get("Id", "Unknown")
                        step_created = True
                        _logger.info("[ARKITE] Step was created successfully despite API error (ID: %s)", created_step_id)
            
            if step_created:
                vals['step_id'] = str(created_step_id)
                # Get the actual index from the created step
                verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if verify_response.ok:
                    steps = verify_response.json()
                    new_step = next((s for s in steps if str(s.get("Id", "")) == str(created_step_id)), None)
                    if new_step:
                        vals['index'] = new_step.get("Index", vals.get('sequence', 0))
            else:
                error_text = response.text[:500] if response.text else "Unknown error"
                raise UserError(f"Failed to create step: HTTP {response.status_code}\n{error_text}")
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error creating step in Arkite: %s", e)
            raise UserError(f"Error creating step: {str(e)}")
        
        return super().create(vals)
    
    def write(self, vals):
        """Override write to save sequence changes to Arkite API"""
        result = super().write(vals)
        
        for record in self:
            if not record.wizard_id or not record.wizard_id.project_id:
                continue
            
            # Update sequence/index if changed
            if 'sequence' in vals and record.step_id:
                api_base = os.getenv('ARKITE_API_BASE')
                api_key = os.getenv('ARKITE_API_KEY')
                
                if not api_base or not api_key:
                    continue
                
                try:
                    url = f"{api_base}/projects/{record.wizard_id.project_id}/steps/{record.step_id}"
                    params = {"apiKey": api_key}
                    headers = {"Content-Type": "application/json"}
                    
                    # Get current step
                    response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                    if not response.ok:
                        continue
                    
                    step_data = response.json()
                    new_index = record.sequence
                    if step_data.get("Index") != new_index:
                        step_data["Index"] = new_index
                        patch_response = requests.patch(url, params=params, headers=headers, json=step_data, verify=False, timeout=10)
                        if patch_response.ok:
                            # Verify update
                            time.sleep(0.3)
                            verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                            if verify_response.ok:
                                updated_data = verify_response.json()
                                record.index = updated_data.get("Index", record.sequence)
                except Exception as e:
                    _logger.error("Error updating job step sequence: %s", e)
        
        return result
    
    def unlink(self):
        """Override unlink to delete step from Arkite when removed from list"""
        for record in self:
            if record.step_id and record.wizard_id and record.wizard_id.project_id:
                api_base = os.getenv('ARKITE_API_BASE')
                api_key = os.getenv('ARKITE_API_KEY')
                
                if api_base and api_key:
                    try:
                        url = f"{api_base}/projects/{record.wizard_id.project_id}/steps/{record.step_id}"
                        params = {"apiKey": api_key}
                        headers = {"Content-Type": "application/json"}
                        
                        # Delete step from Arkite
                        response = requests.delete(url, params=params, headers=headers, verify=False, timeout=10)
                        if not response.ok and response.status_code != 404:  # 404 is OK (already deleted)
                            _logger.warning("Failed to delete step from Arkite: HTTP %s", response.status_code)
                    except Exception as e:
                        _logger.error("Error deleting step from Arkite: %s", e)
                        # Continue with deletion even if API call fails
        
        return super().unlink()
