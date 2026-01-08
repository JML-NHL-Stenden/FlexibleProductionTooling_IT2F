# product_module/models/instruction_step.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import os
import logging
import time

_logger = logging.getLogger(__name__)


class ProductModuleInstructionStep(models.Model):
    _name = 'product_module.instruction.step'
    _description = 'Process Step for Instruction'
    _order = 'index, id'
    _rec_name = 'name'
    
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Display order (for drag-and-drop reordering)'
    )

    instruction_id = fields.Many2one(
        'product_module.instruction',
        string='Process',
        # required=True,
        ondelete='cascade',
        help='Process this step belongs to'
    )
    # Temporary field to allow One2many from project to steps
    # This is computed from instruction_id.project_id for display purposes
    project_id = fields.Many2one(
        'product_module.project',
        string='Project',
        related='instruction_id.project_id',
        store=True,
        readonly=True,
        help='Project this step belongs to (via instruction)'
    )
    arkite_step_id = fields.Char(
        string='Arkite Step ID',
        readonly=True,
        help='Step ID from Arkite platform (auto-filled when synced)',
        index=True,
        unique=True,
    )
    name = fields.Char(
        string='Step Name',
        required=True,
        help='Name of the step'
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
        ('COMPONENT', 'Component'),
    ], string='Step Type', required=True, default='WORK_INSTRUCTION', help='Type of step')
    index = fields.Integer(
        string='Index',
        default=0,
        help='Position index of the step in Arkite'
    )
    parent_step_id = fields.Char(
        string='Parent Step ID',
        readonly=True,
        help='ID of the parent step (for composite steps)'
    )
    for_all_variants = fields.Boolean(
        string='For All Variants',
        default=True,
        help='If true, this step is executed for all variants'
    )
    # Variants - link to project variants
    variant_ids = fields.Many2many(
        'product_module.variant',
        'instruction_step_variant_rel',
        'step_id', 'variant_id',
        string='Variants',
        help='Specific variants this step applies to (if For All Variants is False)'
    )
    comment = fields.Text(
        string='Comment',
        help='Comment/notes for this step'
    )
    detection_status = fields.Boolean(
        default=False
    )
    is_completed = fields.Boolean(
        default=False
    )
    is_project_loaded = fields.Boolean(
        default=False
    )
    detection_id = fields.Char(
        string='Detection ID',
        help='Detection ID (required for detection-based steps like TOOL_PLACING, OBJECT_PLACING, etc.)'
    )
    material_id = fields.Char(
        string='Material ID',
        help='Material ID (required for MATERIAL_GRAB step type)'
    )
    button_id = fields.Char(
        string='Button ID',
        help='Button ID (required for VIRTUAL_BUTTON_PRESS step type)'
    )
    # Additional step fields
    text_instruction = fields.Text(
        string='Text Instruction',
        help='Text instruction content (for WORK_INSTRUCTION type)'
    )
    image_instruction_id = fields.Char(
        string='Image Instruction ID',
        help='Arkite Image ID for instruction image'
    )
    child_step_order = fields.Selection([
        ('Sequential', 'Sequential'),
        ('Parallel', 'Parallel'),
        ('None', 'None'),
    ], string='Child Step Order', default='Sequential',
       help='How child steps are executed (for COMPOSITE steps)')
    step_controlflow = fields.Selection([
        ('None', 'None'),
        ('Loop', 'Loop'),
        ('Conditional', 'Conditional'),
    ], string='Step Control Flow', default='None',
       help='Control flow type for this step')

    _sql_constraints = [
        ('arkite_step_id_unique',
        'unique(arkite_step_id)',
        'Arkite Step ID must be unique'),
    ]
    
    @api.model
    def create(self, vals):
        """Override create to create step in Arkite if arkite_step_id is empty (new step)"""
        # Set project_id from instruction_id if not already set
        if 'instruction_id' in vals and not vals.get('project_id'):
            instruction = self.env['product_module.instruction'].browse(vals.get('instruction_id'))
            if instruction and instruction.project_id:
                vals['project_id'] = instruction.project_id.id
        elif self.env.context.get('default_instruction_id') and not vals.get('project_id'):
            instruction = self.env['product_module.instruction'].browse(self.env.context.get('default_instruction_id'))
            if instruction and instruction.project_id:
                vals['project_id'] = instruction.project_id.id
        
        # If arkite_step_id is provided, it's a synced step - just create the record
        if vals.get('arkite_step_id'):
            return super().create(vals)
        
        # Otherwise, create a new step in Arkite for the process
        instruction = None
        if vals.get('instruction_id'):
            instruction = self.env['product_module.instruction'].browse(vals.get('instruction_id'))
        elif self.env.context.get('default_instruction_id'):
            instruction = self.env['product_module.instruction'].browse(self.env.context.get('default_instruction_id'))
        
        if not instruction or not instruction.project_id:
            raise UserError(_('Process step must be linked to a process with a project.'))
        
        if not instruction.arkite_process_id:
            raise UserError(_('The process must have an Arkite Process ID to create steps. Please sync the process from Arkite first.'))
        
        if not instruction.project_id.arkite_project_id:
            raise UserError(_('The project must have an Arkite Project ID to create steps.'))
        
        # Get credentials
        try:
            creds = instruction.project_id._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception as e:
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration. Error: %s') % str(e))
        
        project_id = instruction.project_id.arkite_project_id
        process_id = instruction.arkite_process_id
        
        # Find parent composite step if needed
        parent_composite_id = None
        try:
            url_check = f"{api_base}/projects/{project_id}/steps/"
            params_check = {"apiKey": api_key}
            headers_check = {"Content-Type": "application/json"}
            check_response = requests.get(url_check, params=params_check, headers=headers_check, verify=False, timeout=10)
            if check_response.ok:
                all_steps = check_response.json()
                if isinstance(all_steps, list):
                    existing_process_steps = [s for s in all_steps if str(s.get("ProcessId", "")) == str(process_id)]
                    if existing_process_steps:
                        composite_in_process = next((s for s in existing_process_steps if s.get("StepType") == "COMPOSITE"), None)
                        if composite_in_process:
                            parent_composite_id = str(composite_in_process.get("Id", ""))
        except Exception as e:
            _logger.warning("[ARKITE] Error checking existing process steps: %s", e)
        
        # Build step payload
        # Fix: Convert sequence to Index by dividing by 10
        sequence_val = vals.get('sequence', 0)
        index_val = sequence_val // 10 if sequence_val > 0 else 0
        
        # Get variant IDs from Many2many field if provided
        variant_ids_arkite = []
        if 'variant_ids' in vals and vals['variant_ids']:
            # Extract variant IDs from the Many2many command list
            # Format: [(6, 0, [id1, id2, ...])] or [(4, id), ...]
            variant_commands = vals['variant_ids']
            odoo_variant_ids = []
            for cmd in variant_commands:
                if cmd[0] == 6:  # Replace all
                    odoo_variant_ids.extend(cmd[2] if len(cmd) > 2 else [])
                elif cmd[0] == 4:  # Add one
                    odoo_variant_ids.append(cmd[1])
            
            # Map Odoo variant IDs to Arkite variant IDs
            if odoo_variant_ids and instruction.project_id:
                odoo_variants = self.env['product_module.variant'].browse(odoo_variant_ids)
                for odoo_variant in odoo_variants:
                    # Try to find matching Arkite variant by name
                    arkite_variant_temp = instruction.project_id.arkite_variant_ids.filtered(
                        lambda v: v.name == odoo_variant.name
                    )
                    if arkite_variant_temp and arkite_variant_temp.variant_id:
                        try:
                            variant_ids_arkite.append(int(arkite_variant_temp.variant_id))
                        except (ValueError, TypeError):
                            pass
        
        step_data = {
            "Type": "Process",
            "Name": vals.get('name', 'Unnamed Step'),
            "StepType": vals.get('step_type', 'WORK_INSTRUCTION'),
            "ProcessId": str(process_id),
            "Index": index_val,  # Fixed: Use converted index value
            "ForAllVariants": vals.get('for_all_variants', True),
            "VariantIds": variant_ids_arkite,  # Fixed: Include variant IDs
            "TextInstruction": {},
            "ImageInstructionId": vals.get('image_instruction_id', "0") if vals.get('image_instruction_id') else "0",
            "ChildStepOrder": "Sequential" if vals.get('step_type') == "COMPOSITE" else "None",
            "StepControlflow": vals.get('step_controlflow', "None"),
            "StepConditions": [],
            "Comment": vals.get('comment', "") or None
        }
        
        # Add optional fields based on step type
        if vals.get('text_instruction') and vals.get('step_type') == 'WORK_INSTRUCTION':
            step_data["TextInstruction"] = {"en-US": vals['text_instruction']}
        
        if vals.get('detection_id'):
            step_data["DetectionId"] = vals['detection_id']
        if vals.get('material_id'):
            step_data["MaterialId"] = vals['material_id']
        if vals.get('button_id'):
            step_data["ButtonId"] = vals['button_id']
        
        if parent_composite_id and str(parent_composite_id) != "0":
            step_data["ParentStepId"] = str(parent_composite_id)
        
        # Create step in Arkite
        url = f"{api_base}/projects/{project_id}/steps/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.post(url, params=params, json=[step_data], headers=headers, verify=False, timeout=10)
            
            if response.ok:
                created_steps = response.json()
                if isinstance(created_steps, list) and created_steps:
                    created_step_id = created_steps[0].get("Id", "")
                    vals['arkite_step_id'] = str(created_step_id)
                    # Get actual index from created step
                    if created_steps[0].get("Index") is not None:
                        vals['index'] = created_steps[0].get("Index", 0)
                elif isinstance(created_steps, dict):
                    created_step_id = created_steps.get("Id", "")
                    vals['arkite_step_id'] = str(created_step_id)
            else:
                # Check if step was created despite error (API bug)
                time.sleep(1)
                verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if verify_response.ok:
                    all_steps = verify_response.json()
                    matching_steps = [s for s in all_steps 
                                     if s.get("Name") == step_data["Name"] 
                                     and str(s.get("ProcessId", "")) == str(process_id)]
                    if matching_steps:
                        created_step_id = matching_steps[0].get("Id", "")
                        vals['arkite_step_id'] = str(created_step_id)
                        vals['index'] = matching_steps[0].get("Index", 0)
        except Exception as e:
            _logger.error("[ARKITE] Error creating step in Arkite: %s", e, exc_info=True)
            raise UserError(_('Failed to create step in Arkite: %s') % str(e))
        
        return super().create(vals)
    
    def write(self, vals):
        """Override write to save changes to Arkite API"""
        # Note: project_id is a related field, so it updates automatically when instruction_id changes
        result = super().write(vals)
        
        for record in self:
            if not record.arkite_step_id or not record.instruction_id or not record.instruction_id.project_id:
                continue
            
            if not record.instruction_id.arkite_process_id or not record.instruction_id.project_id.arkite_project_id:
                continue
            
            # Get credentials
            try:
                creds = record.instruction_id.project_id._get_arkite_credentials()
                api_base = creds['api_base']
                api_key = creds['api_key']
            except Exception:
                continue
            
            project_id = record.instruction_id.project_id.arkite_project_id
            
            try:
                url = f"{api_base}/projects/{project_id}/steps/{record.arkite_step_id}"
                params = {"apiKey": api_key}
                headers = {"Content-Type": "application/json"}
                
                # Get current step from Arkite
                response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if not response.ok:
                    continue
                
                step_data = response.json()
                updated = False
                
                # Update fields that changed
                if 'name' in vals and step_data.get("Name") != record.name:
                    step_data["Name"] = record.name
                    updated = True
                
                if 'step_type' in vals and step_data.get("StepType") != record.step_type:
                    step_data["StepType"] = record.step_type
                    step_data["ChildStepOrder"] = "Sequential" if record.step_type == "COMPOSITE" else "None"
                    updated = True
                
                if 'sequence' in vals:
                    # Fix: Convert sequence to Index by dividing by 10
                    new_index = record.sequence // 10 if record.sequence > 0 else 0
                    step_data["Index"] = new_index
                    updated = True
                    # Also update the index field in Odoo
                    record.index = new_index
                
                if 'for_all_variants' in vals:
                    step_data["ForAllVariants"] = record.for_all_variants
                    if record.for_all_variants:
                        step_data["VariantIds"] = []
                    updated = True
                
                # Update variant IDs if changed
                if 'variant_ids' in vals:
                    variant_ids_arkite = []
                    if record.variant_ids and record.instruction_id.project_id:
                        # Map Odoo variant IDs to Arkite variant IDs
                        for odoo_variant in record.variant_ids:
                            arkite_variant_temp = record.instruction_id.project_id.arkite_variant_ids.filtered(
                                lambda v: v.name == odoo_variant.name
                            )
                            if arkite_variant_temp and arkite_variant_temp.variant_id:
                                try:
                                    variant_ids_arkite.append(int(arkite_variant_temp.variant_id))
                                except (ValueError, TypeError):
                                    pass
                    step_data["VariantIds"] = variant_ids_arkite
                    updated = True
                
                if 'text_instruction' in vals and record.step_type == 'WORK_INSTRUCTION':
                    step_data["TextInstruction"] = {"en-US": record.text_instruction} if record.text_instruction else {}
                    updated = True
                
                if 'image_instruction_id' in vals:
                    step_data["ImageInstructionId"] = record.image_instruction_id if record.image_instruction_id else "0"
                    updated = True
                
                if 'detection_id' in vals:
                    step_data["DetectionId"] = record.detection_id if record.detection_id else None
                    updated = True
                
                if 'material_id' in vals:
                    step_data["MaterialId"] = record.material_id if record.material_id else None
                    updated = True
                
                if 'button_id' in vals:
                    step_data["ButtonId"] = record.button_id if record.button_id else None
                    updated = True
                
                if 'comment' in vals:
                    step_data["Comment"] = record.comment if record.comment else None
                    updated = True
                
                if 'child_step_order' in vals:
                    step_data["ChildStepOrder"] = record.child_step_order
                    updated = True
                
                if 'step_controlflow' in vals:
                    step_data["StepControlflow"] = record.step_controlflow
                    updated = True
                
                # Update step in Arkite if anything changed
                if updated:
                    patch_response = requests.patch(url, params=params, headers=headers, json=step_data, verify=False, timeout=10)
                    if patch_response.ok and 'sequence' in vals:
                        # Update index from Arkite
                        verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                        if verify_response.ok:
                            updated_data = verify_response.json()
                            # Fix: Convert Index back to sequence format for consistency
                            arkite_index = updated_data.get("Index", 0)
                            record.index = arkite_index
                            # Update sequence to match (multiply by 10)
                            record.sequence = arkite_index * 10
            except Exception as e:
                _logger.error("[ARKITE] Error updating step in Arkite: %s", e, exc_info=True)
        
        return result
    
    def unlink(self):
        """Override unlink to delete step from Arkite when removed"""
        for record in self:
            if record.arkite_step_id and record.instruction_id and record.instruction_id.project_id:
                if record.instruction_id.arkite_process_id and record.instruction_id.project_id.arkite_project_id:
                    try:
                        creds = record.instruction_id.project_id._get_arkite_credentials()
                        api_base = creds['api_base']
                        api_key = creds['api_key']
                        
                        url = f"{api_base}/projects/{record.instruction_id.project_id.arkite_project_id}/steps/{record.arkite_step_id}"
                        params = {"apiKey": api_key}
                        headers = {"Content-Type": "application/json"}
                        
                        response = requests.delete(url, params=params, headers=headers, verify=False, timeout=10)
                        if not response.ok and response.status_code != 404:
                            _logger.warning("[ARKITE] Failed to delete step from Arkite: HTTP %s", response.status_code)
                    except Exception as e:
                        _logger.error("[ARKITE] Error deleting step from Arkite: %s", e, exc_info=True)
        
        return super().unlink()
