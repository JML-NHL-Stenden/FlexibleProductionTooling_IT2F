# product_module/models/arkite_process_step.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import os
import logging
import time

_logger = logging.getLogger(__name__)


class ArkiteProcessStep(models.TransientModel):
    """Temporary model for displaying process steps in tree view"""
    _name = 'product_module.arkite.process.step'
    _description = 'Arkite Process Step (Temporary)'
    _order = 'sequence, id'
    _rec_name = 'step_name'
    
    wizard_id = fields.Many2one('product_module.arkite.job.step.wizard', string='Wizard', required=True, ondelete='cascade')
    process_id = fields.Char(string='Process ID', required=True)
    
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
    sequence = fields.Integer(string='Sequence', default=10)
    index = fields.Integer(string='Index', readonly=True)
    
    # Variants
    variant_ids = fields.Many2many(
        'product_module.arkite.variant.temp',
        'process_step_variant_rel',
        'step_id', 'variant_id',
        string='Variants'
    )
    for_all_variants = fields.Boolean(string='For All Variants', default=False)
    
    @api.model
    def create(self, vals):
        """Override create to create step in Arkite if step_id is empty (new step)"""
        # If step_id is provided, it's a loaded step - just create the record
        if vals.get('step_id'):
            return super().create(vals)
        
        # Otherwise, create a new step in Arkite for the process
        wizard = self.env['product_module.arkite.job.step.wizard'].browse(vals.get('wizard_id'))
        if not wizard or not wizard.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        process_id = vals.get('process_id')
        if not process_id:
            # Try to get from wizard's selected_process_id (Char field)
            if wizard.selected_process_id:
                process_id = wizard.selected_process_id
                vals['process_id'] = process_id
            else:
                raise UserError("Process ID is required. Please select a process first (click 'Load Process List' then select a process).")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        # First, check existing process steps to understand the structure
        # Process steps might need a ParentStepId pointing to a composite step within the process
        parent_composite_id = None
        try:
            url_check = f"{api_base}/projects/{wizard.project_id}/steps/"
            params_check = {"apiKey": api_key}
            headers_check = {"Content-Type": "application/json"}
            check_response = requests.get(url_check, params=params_check, headers=headers_check, verify=False, timeout=10)
            if check_response.ok:
                all_steps = check_response.json()
                if isinstance(all_steps, list):
                    # Find existing process steps for this process
                    existing_process_steps = [s for s in all_steps if str(s.get("ProcessId", "")) == str(process_id)]
                    if existing_process_steps:
                        # Check if any existing process step has a ParentStepId
                        for step in existing_process_steps:
                            parent_id = step.get("ParentStepId")
                            if parent_id and str(parent_id) != "0":
                                # Found a parent - check if it's a composite step
                                parent_step = next((s for s in all_steps if str(s.get("Id", "")) == str(parent_id)), None)
                                if parent_step and parent_step.get("StepType") == "COMPOSITE":
                                    parent_composite_id = str(parent_id)
                                    _logger.info("[ARKITE] Found existing composite parent for process steps: %s", parent_composite_id)
                                    break
                        # If no parent found, look for a composite step within this process
                        if not parent_composite_id:
                            composite_in_process = next((s for s in existing_process_steps if s.get("StepType") == "COMPOSITE"), None)
                            if composite_in_process:
                                parent_composite_id = str(composite_in_process.get("Id", ""))
                                _logger.info("[ARKITE] Found composite step in process to use as parent: %s", parent_composite_id)
        except Exception as e:
            _logger.warning("[ARKITE] Error checking existing process steps: %s", e)
        
        # Build step payload for process step
        step_data = {
            "Type": "Process",  # Process steps have Type="Process"
            "Name": vals.get('step_name', 'Unnamed Step'),
            "StepType": vals.get('step_type', 'WORK_INSTRUCTION'),
            "ProcessId": str(process_id),  # Process ID (not "0" like job steps)
            "Index": vals.get('sequence', 0) if vals.get('sequence', 0) > 0 else 0,
            "ForAllVariants": vals.get('for_all_variants', False),
            "VariantIds": [],
            "TextInstruction": {},
            "ImageInstructionId": "0",
            "ChildStepOrder": "None" if vals.get('step_type') != "COMPOSITE" else "Sequential",
            "StepControlflow": "None",
            "StepConditions": [],
            "Comment": None
        }
        
        # Only add ParentStepId if we found a valid composite parent
        # If no parent found, omit ParentStepId entirely (let Arkite handle it)
        if parent_composite_id and str(parent_composite_id) != "0":
            step_data["ParentStepId"] = str(parent_composite_id)
            _logger.info("[ARKITE] Setting ParentStepId to composite: %s", parent_composite_id)
        else:
            _logger.info("[ARKITE] No composite parent found, omitting ParentStepId")
            # Explicitly ensure ParentStepId is not in the payload
            if "ParentStepId" in step_data:
                del step_data["ParentStepId"]
        
        _logger.info("[ARKITE] Creating process step - Name: %s, ProcessId: %s, Payload keys: %s", 
                     step_data.get("Name"), step_data.get("ProcessId"), list(step_data.keys()))
        
        # Create step in Arkite (API expects an array)
        url = f"{api_base}/projects/{wizard.project_id}/steps/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        # Final verification: ensure ParentStepId is never "0"
        if "ParentStepId" in step_data and (step_data["ParentStepId"] == "0" or step_data["ParentStepId"] == 0):
            _logger.error("[ARKITE] ERROR: ParentStepId is '0'! Removing it...")
            del step_data["ParentStepId"]
        
        try:
            payload = [step_data]
            _logger.info("[ARKITE] Sending POST request to: %s", url)
            _logger.info("[ARKITE] Final payload: %s", payload)
            
            response = requests.post(url, params=params, json=payload, headers=headers, verify=False, timeout=10)
            
            _logger.info("[ARKITE] Response status: %s", response.status_code)
            _logger.info("[ARKITE] Response text: %s", response.text[:500] if response.text else "No response text")
            
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
                    matching_steps = [s for s in all_steps 
                                     if s.get("Name") == step_data["Name"] 
                                     and str(s.get("ProcessId", "")) == str(process_id)]
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
            _logger.error("Error creating process step in Arkite: %s", e)
            raise UserError(f"Error creating step: {str(e)}")
        
        return super().create(vals)
    
    def action_move_up(self):
        """Move step up"""
        self.ensure_one()
        return self.wizard_id.action_move_process_step_sequence(self.id, 'up')
    
    def action_move_down(self):
        """Move step down"""
        self.ensure_one()
        return self.wizard_id.action_move_process_step_sequence(self.id, 'down')
    
    def action_assign_variants(self):
        """Open variant assignment interface"""
        self.ensure_one()
        return self.wizard_id.action_show_variant_selection_for_step(self.step_id, self.step_name)
    
    def write(self, vals):
        """Override write to save changes to Arkite API"""
        result = super().write(vals)
        
        for record in self:
            if not record.wizard_id or not record.wizard_id.project_id:
                continue
            
            # Skip if step_id is not set (new step being created)
            if not record.step_id:
                continue
            
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
                updated = False
                
                # Update step name if changed
                if 'step_name' in vals and step_data.get("Name") != record.step_name:
                    step_data["Name"] = record.step_name
                    updated = True
                
                # Update step type if changed
                if 'step_type' in vals and step_data.get("StepType") != record.step_type:
                    step_data["StepType"] = record.step_type
                    # Update ChildStepOrder for composite steps
                    if record.step_type == "COMPOSITE":
                        step_data["ChildStepOrder"] = "Sequential"
                    else:
                        step_data["ChildStepOrder"] = "None"
                    updated = True
                
                # Update sequence/index if changed
                if 'sequence' in vals:
                    new_index = record.sequence
                    if step_data.get("Index") != new_index:
                        step_data["Index"] = new_index
                        updated = True
                
                # Update variants if changed
                if 'variant_ids' in vals or 'for_all_variants' in vals:
                    if record.for_all_variants:
                        step_data["ForAllVariants"] = True
                        step_data["VariantIds"] = []
                    else:
                        step_data["ForAllVariants"] = False
                        step_data["VariantIds"] = [v.variant_id for v in record.variant_ids]
                    updated = True
                
                # Update step if anything changed
                if updated:
                    patch_response = requests.patch(url, params=params, headers=headers, json=step_data, verify=False, timeout=10)
                    if patch_response.ok:
                        # Verify update
                        time.sleep(0.3)
                        verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                        if verify_response.ok:
                            updated_data = verify_response.json()
                            if 'sequence' in vals:
                                record.index = updated_data.get("Index", record.sequence)
            except Exception as e:
                _logger.error("Error updating step in Arkite: %s", e)
        
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


class ArkiteVariantTemp(models.TransientModel):
    """Temporary model for variants"""
    _name = 'product_module.arkite.variant.temp'
    _description = 'Arkite Variant (Temporary)'
    _rec_name = 'name'
    
    wizard_id = fields.Many2one('product_module.arkite.job.step.wizard', string='Wizard', ondelete='cascade')
    variant_id = fields.Char(string='Variant ID', required=True)
    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
