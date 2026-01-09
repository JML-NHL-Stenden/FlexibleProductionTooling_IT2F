# product_module/models/instruction.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)


class ProductModuleInstruction(models.Model):
    _name = 'product_module.instruction'
    _description = 'Process for Product'
    _order = 'sequence, id'

    product_id = fields.Many2one(
        'product_module.product', 
        string='Product', 
        ondelete='cascade'
    )
    
    step_id = fields.Char(
        string='Arkite Step ID',
        readonly=True,
        help='Step ID from Arkite platform (auto-filled when synced)',
        index=True,
        unique=True,
    )
    variant_id = fields.Many2one(
        'product_module.variant',
        string='Variant',
        ondelete='cascade'
    )
    project_id = fields.Many2one(
        'product_module.project',
        string='Project',
        ondelete='cascade',
        help='Project this process belongs to'
    )
    is_completed = fields.Boolean(
        default=False
    )
    sequence = fields.Integer(string='Step #', default=0, help='Order of process steps')
    title = fields.Char(string='Process Title', required=True, size=250)
    arkite_process_id = fields.Char(
        string='Arkite Process ID',
        readonly=True,
        help='Process ID from Arkite platform (auto-filled when synced)'
    )
    # Additional Arkite process information
    arkite_process_type = fields.Char(
        string='Arkite Process Type',
        readonly=True,
        help='Process type from Arkite (e.g., "Process")'
    )
    arkite_comment = fields.Text(
        string='Arkite Comment',
        readonly=True,
        help='Comment/description from Arkite process'
    )
    # Process steps (One2many relationship)
    process_step_ids = fields.One2many(
        'product_module.instruction.step',
        'instruction_id',
        string='Process Steps',
        help='Steps that belong to this process'
    )
    process_step_count = fields.Integer(
        string='Process Steps Count',
        compute='_compute_process_step_count',
        help='Number of steps in this process'
    )
    # Computed field to check if this process is selected
    is_selected = fields.Boolean(
        string='Is Selected',
        compute='_compute_is_selected',
        store=False,
        help='Whether this process is currently selected in the parent project'
    )
    # Process Start Trigger (when the process should start)
    process_trigger = fields.Selection([
        ('project_loaded', 'Project Loaded'),
        ('alarm_clock', 'Alarm Clock'),
        ('receive_communication', 'Receive Communication'),
        ('timer', 'Timer'),
        ('variable_changed', 'Variable Changed'),
        ('watchdog', 'Watchdog'),
    ], string='Process Start Trigger', 
       help='When this process should start automatically. "Project Loaded" starts when project is loaded on unit.')
    image = fields.Binary(string='Illustration', attachment=True)

    _sql_constraints = [
        ('step_id_unique',
        'unique(step_id)',
        'Step ID must be unique'),
    ]
    
    @api.depends('process_step_ids')
    def _compute_process_step_count(self):
        """Compute the number of process steps"""
        for record in self:
            record.process_step_count = len(record.process_step_ids)
    
    @api.depends('project_id', 'project_id.selected_instruction_id')
    def _compute_is_selected(self):
        """Compute if this process is selected in the parent project"""
        for record in self:
            if record.project_id:
                # Access selected_instruction_id through project_id
                selected_id = record.project_id.selected_instruction_id
                record.is_selected = (selected_id and selected_id.id == record.id)
            else:
                record.is_selected = False
    
    def _refresh_selection_state(self):
        """Force recomputation of is_selected field"""
        self.invalidate_recordset(['is_selected'])
        self._compute_is_selected()
    
    def action_sync_process_steps_from_arkite(self):
        """Fetch and sync process steps from Arkite for this process"""
        self.ensure_one()
        if not self.arkite_process_id or not self.project_id:
            raise UserError(_('This process must have an Arkite Process ID and be linked to a project to sync steps.'))
        
        if not self.project_id.arkite_project_id:
            raise UserError(_('The project must have an Arkite Project ID to sync steps.'))
        
        # If called from project, update selected_instruction_id
        if self.env.context.get('from_project'):
            self.project_id.selected_instruction_id = self.id
        
        # Get credentials
        try:
            creds = self.project_id._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception as e:
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration. Error: %s') % str(e))
        
        try:
            # Try process-specific endpoint first
            url = f"{api_base}/projects/{self.project_id.arkite_project_id}/processes/{self.arkite_process_id}/steps/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("[ARKITE] Fetching process steps from: %s (process ID: %s)", url, self.arkite_process_id)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            
            steps = []
            if response.ok:
                steps = response.json()
                if isinstance(steps, list):
                    _logger.info("[ARKITE] Fetched %s steps from process-specific endpoint", len(steps))
                else:
                    _logger.warning("[ARKITE] Process-specific endpoint returned non-list: %s", type(steps))
            else:
                _logger.warning("[ARKITE] Process-specific endpoint failed (HTTP %s), trying general steps endpoint", response.status_code)
            
            # If process-specific endpoint returned nothing or failed, try general steps endpoint
            if not steps or len(steps) == 0:
                url_all = f"{api_base}/projects/{self.project_id.arkite_project_id}/steps/"
                _logger.info("[ARKITE] Trying general steps endpoint: %s", url_all)
                response_all = requests.get(url_all, params=params, headers=headers, verify=False, timeout=10)
                if response_all.ok:
                    all_steps = response_all.json()
                    if isinstance(all_steps, list):
                        # Filter steps for this process
                        process_id_str = str(self.arkite_process_id)
                        steps = [s for s in all_steps if str(s.get("ProcessId", "")) == process_id_str]
                        _logger.info("[ARKITE] Found %s steps for process %s from general endpoint (total: %s)", 
                                   len(steps), self.arkite_process_id, len(all_steps))
                    else:
                        _logger.warning("[ARKITE] General steps endpoint returned non-list: %s", type(all_steps))
                else:
                    _logger.error("[ARKITE] General steps endpoint also failed: HTTP %s", response_all.status_code)
            
            if isinstance(steps, list) and len(steps) > 0:
                _logger.info("[ARKITE] Processing %s steps for process %s", len(steps), self.arkite_process_id)
                
                # Clear existing steps
                self.process_step_ids.unlink()
                
                # Create step records
                for step_data in steps:
                    _logger.debug("[ARKITE] Creating step: Name='%s', Id='%s', ProcessId='%s', Type='%s'", 
                                step_data.get("Name"), step_data.get("Id"), step_data.get("ProcessId"), step_data.get("Type"))
                    
                    # Extract TextInstruction content
                    text_instruction = ""
                    text_inst_data = step_data.get("TextInstruction", {})
                    if isinstance(text_inst_data, dict):
                        # TextInstruction might have keys like "en-US", "Text", "Content", etc.
                        text_instruction = text_inst_data.get("en-US", "") or text_inst_data.get("Text", "") or text_inst_data.get("Content", "") or ""
                    elif isinstance(text_inst_data, str):
                        text_instruction = text_inst_data
                    
                    # Get ImageInstructionId
                    image_instruction_id = str(step_data.get("ImageInstructionId", "")) if step_data.get("ImageInstructionId") and str(step_data.get("ImageInstructionId")) != "0" else ""
                    
                    # Get VariantIds and map to Odoo variants (if project has variants)
                    variant_ids_list = []
                    variant_ids_from_arkite = step_data.get("VariantIds", [])
                    if variant_ids_from_arkite and self.project_id:
                        # Map Arkite variant IDs to Odoo variants
                        # First, try to find matching variants via arkite_variant_ids (temporary model)
                        for arkite_variant_id in variant_ids_from_arkite:
                            arkite_variant_id_str = str(arkite_variant_id)
                            # Find the temporary variant record in the project
                            arkite_variant_temp = self.project_id.arkite_variant_ids.filtered(
                                lambda v: v.variant_id == arkite_variant_id_str
                            )
                            if arkite_variant_temp:
                                # Try to find matching Odoo variant by name
                                # Note: This assumes variant names match between Arkite and Odoo
                                odoo_variant = self.env['product_module.variant'].search([
                                    ('name', '=', arkite_variant_temp.name)
                                ], limit=1)
                                if odoo_variant:
                                    variant_ids_list.append(odoo_variant.id)
                                else:
                                    _logger.debug("[ARKITE] No Odoo variant found for Arkite variant '%s' (ID: %s)", 
                                                arkite_variant_temp.name, arkite_variant_id_str)
                    
                    # Get ChildStepOrder and StepControlflow
                    child_step_order = step_data.get("ChildStepOrder", "Sequential")
                    step_controlflow = step_data.get("StepControlflow", "None")
                    
                    # Fix: Use empty string instead of False for Char fields
                    parent_step_id = str(step_data.get("ParentStepId", "")) if step_data.get("ParentStepId") and str(step_data.get("ParentStepId")) != "0" else ""
                    detection_id = str(step_data.get("DetectionId", "")) if step_data.get("DetectionId") else ""
                    material_id = str(step_data.get("MaterialId", "")) if step_data.get("MaterialId") else ""
                    button_id = str(step_data.get("ButtonId", "")) if step_data.get("ButtonId") else ""
                    
                    step_index = step_data.get("Index", 0)
                    
                    self.env['product_module.instruction.step'].create({
                        'instruction_id': self.id,
                        'arkite_step_id': str(step_data.get("Id", "")),
                        'name': step_data.get("Name", "Unnamed Step"),
                        'step_type': step_data.get("StepType", "WORK_INSTRUCTION"),
                        'index': step_index,
                        'sequence': step_index * 10,  # Convert Index to sequence (multiply by 10)
                        'parent_step_id': parent_step_id,
                        'for_all_variants': step_data.get("ForAllVariants", True),
                        'comment': step_data.get("Comment", ""),
                        'detection_id': detection_id,
                        'material_id': material_id,
                        'button_id': button_id,
                        'text_instruction': text_instruction,
                        'image_instruction_id': image_instruction_id,
                        'child_step_order': child_step_order if child_step_order in ['Sequential', 'Parallel', 'None'] else 'Sequential',
                        'step_controlflow': step_controlflow if step_controlflow in ['None', 'Loop', 'Conditional'] else 'None',
                        'variant_ids': [(6, 0, variant_ids_list)] if variant_ids_list else [],
                    })
                
                # Invalidate cache to refresh the UI
                self.invalidate_recordset(['process_step_ids', 'process_step_count'])
                self._compute_process_step_count()
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Synced %s process steps from Arkite.') % len(steps),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            elif isinstance(steps, list) and len(steps) == 0:
                _logger.warning("[ARKITE] No steps found for process %s", self.arkite_process_id)
                # Clear existing steps if none found
                self.process_step_ids.unlink()
                self.invalidate_recordset(['process_step_ids', 'process_step_count'])
                self._compute_process_step_count()
                raise UserError(_('No steps found for this process in Arkite. The process may not have any steps yet, or they may be root steps (ProcessId=0).'))
            else:
                raise UserError(_('Unexpected response format from Arkite API'))
        except requests.exceptions.RequestException as e:
            _logger.error("[ARKITE] Network error syncing process steps: %s", e, exc_info=True)
            raise UserError(_('Network error: %s') % str(e))
        except Exception as e:
            _logger.error("[ARKITE] Error syncing process steps: %s", e, exc_info=True)
            raise UserError(_('Error: %s') % str(e))

    # Input constrains
    @api.constrains('product_id', 'variant_id', 'project_id')
    def _check_parent(self):
        for record in self:
            parent_count = sum([bool(record.product_id), bool(record.variant_id), bool(record.project_id)])
            if parent_count == 0:
                raise UserError(_('Process must be linked to either a Product, Variant, or Project.'))
            if parent_count > 1:
                raise UserError(_('Process can only be linked to one parent (Product, Variant, or Project).'))
    
    @api.constrains('title')
    def _check_title_length(self):
        for record in self:
            if record.title and len(record.title) > 250:
                raise UserError(_('Process Title cannot exceed 250 characters.'))
    
    def action_select_instruction(self):
        """Action to select this process on the parent project"""
        self.ensure_one()
        if not self.project_id:
            raise UserError(_('This process must be linked to a project to be selected.'))
        
        # Update selected instruction - write() automatically commits in Odoo
        self.project_id.write({'selected_instruction_id': self.id})
        
        # Flush to ensure the write is committed to database
        self.env.cr.flush()
        
        # Force recomputation of all related fields
        self.project_id._compute_selected_instruction_steps()
        self.project_id._compute_selected_instruction_info()
        
        # Invalidate and recompute is_selected on all instructions
        if self.project_id.instruction_ids:
            for instruction in self.project_id.instruction_ids:
                instruction.invalidate_recordset(['is_selected'])
                instruction._compute_is_selected()
        
        # Return action to reopen the form - this forces a fresh read from database
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product_module.project',
            'res_id': self.project_id.id,
            'view_mode': 'form',
            'target': 'current',
            'views': [(False, 'form')],
        }


