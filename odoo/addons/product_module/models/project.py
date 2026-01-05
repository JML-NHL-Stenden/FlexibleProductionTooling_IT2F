# product_module/models/project.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import os
import logging
import time

_logger = logging.getLogger(__name__)


class ProductModuleProject(models.Model):
    _name = 'product_module.project'
    _description = 'Product Project'
    _order = 'name, id'

    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    name = fields.Char(string='Project Name', required=True, size=50)
    description = fields.Text(string='Description', size=250)
    
    # Related jobs (Many2many relationship)
    job_ids = fields.Many2many('product_module.type', string='Jobs')
    job_count = fields.Integer(string='Total Jobs', compute='_compute_job_count')
    
    # Arkite Integration
    arkite_unit_id = fields.Many2one(
        'product_module.arkite.unit',
        string='Arkite Unit',
        help='Arkite unit/workstation assigned to this project. API calls will use this unit\'s credentials.'
    )
    arkite_project_id = fields.Char(
        string='Arkite Project ID',
        help='ID of the linked Arkite project'
    )
    arkite_project_name = fields.Char(
        string='Arkite Project Name',
        readonly=True,
        help='Name of the linked Arkite project (auto-filled when linked)'
    )
    arkite_linked = fields.Boolean(
        string='Linked to Arkite',
        compute='_compute_arkite_linked',
        help='Whether this project is linked to an Arkite project'
    )
    arkite_project_loaded = fields.Boolean(
        string='Project Loaded',
        default=False,
        readonly=True,
        help='Indicates if the Arkite project has been successfully loaded'
    )
    
    # Fields moved from Product: Processes, Materials, QR Code
    instruction_ids = fields.One2many(
        'product_module.instruction',
        'project_id',
        string='Processes',
        help='Assembly processes for this project'
    )
    instruction_count = fields.Integer(
        string='Process Count',
        compute='_compute_instruction_count',
        store=False,
        help='Number of processes in this project'
    )
    selected_instruction_id = fields.Many2one(
        'product_module.instruction',
        string='Selected Process',
        help='Currently selected process to view/edit its steps'
    )
    
    @api.onchange('selected_instruction_id')
    def _onchange_selected_instruction_id(self):
        """Trigger refresh when selected instruction changes"""
        # Force recomputation of steps and info when selection changes
        if self.selected_instruction_id:
            self._compute_selected_instruction_steps()
            self._compute_selected_instruction_info()
            # Force recomputation of is_selected on all instructions
            if self.instruction_ids:
                for instruction in self.instruction_ids:
                    instruction.invalidate_recordset(['is_selected'])
                    instruction._compute_is_selected()
    # Computed field to get steps from selected instruction
    # This ensures only steps from the selected process are shown
    selected_instruction_step_ids = fields.Many2many(
        'product_module.instruction.step',
        string='Steps for Selected Process',
        compute='_compute_selected_instruction_steps',
        inverse='_inverse_selected_instruction_steps',
        store=False,
        help='Steps for the currently selected process. Select a process first to view/edit its steps.'
    )
    
    @api.depends('selected_instruction_id', 'selected_instruction_id.process_step_ids')
    def _compute_selected_instruction_steps(self):
        """Compute steps from selected instruction"""
        for record in self:
            if record.selected_instruction_id:
                record.selected_instruction_step_ids = record.selected_instruction_id.process_step_ids
            else:
                record.selected_instruction_step_ids = False
    
    def _inverse_selected_instruction_steps(self):
        """Handle inverse - ensure steps belong to selected instruction"""
        for record in self:
            if record.selected_instruction_id and record.selected_instruction_step_ids:
                # Ensure all steps belong to the selected instruction
                for step in record.selected_instruction_step_ids:
                    if step.instruction_id != record.selected_instruction_id:
                        step.instruction_id = record.selected_instruction_id
    selected_instruction_title = fields.Char(
        string='Selected Process Title',
        compute='_compute_selected_instruction_info',
        store=False,
        help='Title of the selected process'
    )
    selected_instruction_step_count = fields.Integer(
        string='Selected Process Step Count',
        compute='_compute_selected_instruction_info',
        store=False,
        help='Number of steps in the selected process'
    )
    selected_instruction_has_arkite_id = fields.Boolean(
        string='Selected Process Has Arkite ID',
        compute='_compute_selected_instruction_info',
        store=False,
        help='Whether the selected process has an Arkite Process ID'
    )
    material_ids = fields.One2many(
        'product_module.material',
        'project_id',
        string='Materials',
        help='Materials used in this project'
    )
    
    # QR Code fields (computed from project name or first variant)
    qr_text = fields.Char(
        string='QR Text',
        compute='_compute_qr',
        store=False,
        help='QR code text (typically project name or variant code)'
    )
    qr_image = fields.Binary(
        string='QR Code',
        compute='_compute_qr',
        attachment=True,
        store=False,
        help='QR code image'
    )
    qr_image_name = fields.Char(
        string='QR Filename',
        compute='_compute_qr_filename',
        store=False
    )
    
    # Arkite Steps, Variants, Processes, and Detections (One2many to transient models)
    arkite_job_step_ids = fields.One2many(
        'product_module.arkite.job.step.temp',
        'project_id',
        string='Job Steps',
        help='Arkite job steps for this project'
    )
    arkite_variant_ids = fields.One2many(
        'product_module.arkite.variant.temp',
        'project_id',
        string='Variants',
        help='Arkite variants for this project'
    )
    arkite_process_ids = fields.One2many(
        'product_module.arkite.process.temp',
        'project_id',
        string='Processes',
        help='Arkite processes available in the project'
    )
    selected_arkite_process_id = fields.Char(
        string='Selected Process ID',
        help='Currently selected Arkite process ID to view/edit its steps'
    )
    selected_process_id_char = fields.Char(
        string='Selected Process ID (Text)',
        help='Enter process name or ID to select a process'
    )
    selected_arkite_process_name = fields.Char(
        string='Selected Process Name',
        compute='_compute_selected_process_name',
        store=False,
        help='Name of the selected process (computed)'
    )
    arkite_process_step_ids = fields.One2many(
        'product_module.arkite.process.step',
        'project_id',
        string='Process Steps',
        help='Steps for the selected Arkite process'
    )
    arkite_detection_ids = fields.One2many(
        'product_module.arkite.detection.temp',
        'project_id',
        string='Detections',
        help='Arkite detections in the project'
    )
    arkite_material_ids = fields.One2many(
        'product_module.arkite.material.temp',
        'project_id',
        string='Arkite Materials',
        help='Materials from Arkite project'
    )

    @api.depends('job_ids')
    def _compute_job_count(self):
        """Count number of jobs for this project"""
        for record in self:
            record.job_count = len(record.job_ids)
    
    @api.depends('instruction_ids')
    def _compute_instruction_count(self):
        """Count number of processes for this project"""
        for record in self:
            record.instruction_count = len(record.instruction_ids)
    
    
    @api.depends('selected_instruction_id', 'selected_instruction_id.title', 'selected_instruction_id.process_step_count', 'selected_instruction_id.arkite_process_id')
    def _compute_selected_instruction_info(self):
        """Compute title, step count, and Arkite ID status for selected process"""
        for record in self:
            if record.selected_instruction_id:
                record.selected_instruction_title = record.selected_instruction_id.title
                record.selected_instruction_step_count = record.selected_instruction_id.process_step_count
                record.selected_instruction_has_arkite_id = bool(record.selected_instruction_id.arkite_process_id)
            else:
                record.selected_instruction_title = False
                record.selected_instruction_step_count = 0
                record.selected_instruction_has_arkite_id = False
    
    def action_select_instruction(self):
        """Action to select a process - called from button with context"""
        self.ensure_one()
        instruction_id = self.env.context.get('instruction_id')
        if instruction_id:
            # Select the instruction
            instruction = self.env['product_module.instruction'].browse(instruction_id)
            if instruction.exists() and instruction.project_id.id == self.id:
                # Update selected instruction
                self.write({'selected_instruction_id': instruction_id})
                # Flush to ensure write is committed
                self.env.cr.flush()
                # Force recomputation
                self._compute_selected_instruction_steps()
                self._compute_selected_instruction_info()
                # Force recomputation of is_selected on all instructions
                if self.instruction_ids:
                    for inst in self.instruction_ids:
                        inst.invalidate_recordset(['is_selected'])
                        inst._compute_is_selected()
        # Return action to reopen the form - forces fresh read from database
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product_module.project',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
            'views': [(False, 'form')],
        }
    
    @api.model
    def default_get(self, fields_list):
        """Set default values when creating a new project"""
        res = super().default_get(fields_list)
        return res
    
    def _ensure_first_process_selected(self):
        """Ensure the first process is selected if no process is currently selected"""
        if not self.selected_instruction_id and self.instruction_ids:
            # Select the first process by sequence, then by id
            first_process = self.instruction_ids.sorted(lambda p: (p.sequence, p.id))[0]
            self.write({'selected_instruction_id': first_process.id})
            # No need to update is_selected - the view uses attrs with parent.selected_instruction_id
    
    @api.model
    def create(self, vals):
        """Override create to select first process after creation"""
        record = super().create(vals)
        # After creation, if there are processes, select the first one
        if record.instruction_ids:
            record._ensure_first_process_selected()
        return record
    
    def write(self, vals):
        """Override write to ensure first process is selected if needed"""
        result = super().write(vals)
        # If instruction_ids changed and no process is selected, select the first one
        if 'instruction_ids' in vals or not self.selected_instruction_id:
            self._ensure_first_process_selected()
        return result
    
    @api.onchange('instruction_ids')
    def _onchange_instruction_ids(self):
        """When processes change, select the first one if none selected"""
        if not self.selected_instruction_id and self.instruction_ids:
            self._ensure_first_process_selected()
    
    def action_sync_process_steps_from_arkite(self):
        """Sync process steps from Arkite for the selected process"""
        self.ensure_one()
        if not self.selected_instruction_id:
            raise UserError(_('Please select a process first to sync its steps.'))
        return self.selected_instruction_id.action_sync_process_steps_from_arkite()
    
    @api.depends('selected_arkite_process_id', 'selected_process_id_char', 'arkite_process_ids', 'arkite_process_ids.name')
    def _compute_selected_process_name(self):
        """Compute the name of the selected process"""
        for record in self:
            # Use selected_process_id_char if available, otherwise use selected_arkite_process_id
            process_id = record.selected_process_id_char or record.selected_arkite_process_id
            if process_id:
                process = record.arkite_process_ids.filtered(
                    lambda p: p.process_id == process_id
                )
                record.selected_arkite_process_name = process.name if process else process_id
            else:
                record.selected_arkite_process_name = ""
    
    @api.onchange('arkite_process_ids')
    def _onchange_arkite_process_ids(self):
        """Update selection options when processes change"""
        # Force recomputation of selection field
        # The selection will be dynamically generated in the view
        pass
    
    @api.depends('arkite_project_id')
    def _compute_arkite_linked(self):
        """Check if project is linked to Arkite"""
        for record in self:
            record.arkite_linked = bool(record.arkite_project_id)
    
    @api.depends('name', 'arkite_project_id')
    def _compute_qr(self):
        """Generate QR code from project name or Arkite project ID"""
        import base64
        import io
        for record in self:
            # Use Arkite project ID if available, otherwise use project name
            code = (record.arkite_project_id or record.name or '').strip()
            record.qr_text = code or False

            if not code:
                record.qr_image = False
                continue

            try:
                import qrcode
            except ImportError:
                record.qr_image = False
                continue

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=2,
            )
            qr.add_data(code)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            buf = io.BytesIO()
            img.save(buf, format='PNG')
            record.qr_image = base64.b64encode(buf.getvalue())

    @api.depends('name', 'arkite_project_id')
    def _compute_qr_filename(self):
        """Generate filename for QR code download"""
        for record in self:
            code = record.arkite_project_id or record.name
            if code:
                record.qr_image_name = f'qr_{code}.png'
            else:
                record.qr_image_name = 'qr_code.png'

    # Input constrains
    @api.constrains('name')
    def _check_name_length(self):
        for record in self:
            if record.name and len(record.name) > 50:
                raise UserError(_('Project Name cannot exceed 50 characters.'))
    
    @api.constrains('description')
    def _check_description_length(self):
        for record in self:
            if record.description and len(record.description) > 250:
                raise UserError(_('Description cannot exceed 250 characters.'))
    
    # ====================
    # Arkite Integration Methods
    # ====================
    
    def _get_arkite_credentials(self):
        """Get Arkite API credentials from unit or fallback to environment variables"""
        # Try to get from assigned Arkite Unit model first
        if self.arkite_unit_id:
            if not self.arkite_unit_id.api_base or not self.arkite_unit_id.api_key:
                raise UserError(_('Arkite unit "%s" is missing API configuration. Please configure the unit first.') % self.arkite_unit_id.name)
            return {
                'api_base': self.arkite_unit_id.api_base,
                'api_key': self.arkite_unit_id.api_key,
                'unit_id': self.arkite_unit_id.unit_id,
            }
        
        # Try to get from Unit Tracking (progress) if linked via name
        # This allows using credentials from Unit Tracking
        if self.name:
            progress_unit = self.env['product_module.progress'].search([
                ('name', '=', self.name),
                ('arkite_api_base', '!=', False),
                ('arkite_api_key', '!=', False)
            ], limit=1)
            if progress_unit:
                return {
                    'api_base': progress_unit.arkite_api_base,
                    'api_key': progress_unit.arkite_api_key,
                    'unit_id': progress_unit.arkite_unit_id or os.getenv('ARKITE_UNIT_ID'),
                }
        
        # Fallback to environment variables (for backward compatibility)
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        unit_id = os.getenv('ARKITE_UNIT_ID')
        
        if not api_base or not api_key:
            raise UserError(_('No Arkite unit assigned to this project and environment variables are not configured. Please assign a unit or configure ARKITE_API_BASE and ARKITE_API_KEY.'))
        
        return {
            'api_base': api_base,
            'api_key': api_key,
            'unit_id': unit_id,
        }
    
    def action_create_unit_from_tracking(self):
        """Open a wizard to select a Unit Tracking entry and create an Arkite Unit from it"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Arkite Unit from Unit Tracking'),
            'res_model': 'product_module.progress',
            'view_mode': 'list',
            'view_id': self.env.ref('product_module.view_progress_list').id,
            'target': 'new',
            'domain': [('arkite_unit_id', '!=', False), ('arkite_api_base', '!=', False), ('arkite_api_key', '!=', False)],
            'context': {
                'create': False,
                'select_multi': False,
                'default_action': 'create_arkite_unit',
            }
        }
    
    def action_create_arkite_project(self):
        """Create a new Arkite project and link it to this Odoo project"""
        self.ensure_one()
        
        # Get credentials from unit or env
        creds = self._get_arkite_credentials()
        api_base = creds['api_base']
        api_key = creds['api_key']
        unit_id = creds.get('unit_id')
        
        if not unit_id:
            raise UserError(_('Unit ID is required. Please assign an Arkite unit to this project or configure ARKITE_UNIT_ID in environment variables.'))
        
        # Use project name for Arkite project
        project_name = self.name
        project_comment = self.description or f"Created from Odoo project: {self.name}"
        
        url = f"{api_base}/projects/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        payload = [{
            "Name": project_name,
            "Comment": project_comment,
            "UnitIds": [int(unit_id)],
        }]
        
        try:
            response = requests.post(url, params=params, json=payload, headers=headers, verify=False, timeout=10)
            
            # Check response
            try:
                response_data = response.json()
            except:
                response_data = None
            
            has_error = False
            error_msg = None
            if response_data:
                if isinstance(response_data, dict):
                    if response_data.get('Type') == 'ERROR':
                        has_error = True
                        error_msg = response_data.get('ErrorMessage', 'Unknown error')
            
            project_id = None
            if response.ok and not has_error:
                if isinstance(response_data, list) and response_data:
                    project_id = str(response_data[0].get("Id") or response_data[0].get("ProjectId"))
                elif isinstance(response_data, dict):
                    project_id = str(response_data.get("Id") or response_data.get("ProjectId"))
            
            # Check if project was created (Arkite API sometimes returns error but still creates)
            if not project_id:
                time.sleep(1)
                project_id = self._get_arkite_project_id_by_name(project_name)
            
            if project_id:
                self.write({
                    'arkite_project_id': project_id,
                    'arkite_project_name': project_name
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('Arkite project created and linked successfully. Project ID: %s') % project_id,
                        'type': 'success',
                    }
                }
            else:
                raise UserError(_('Failed to create Arkite project: %s') % (error_msg or f'HTTP {response.status_code}'))
                
        except requests.exceptions.RequestException as e:
            raise UserError(_('Error connecting to Arkite API: %s') % str(e))
    
    def action_duplicate_arkite_project(self):
        """Open template selection to duplicate from template"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Select Template to Duplicate'),
            'res_model': 'product_module.arkite.project.selection',
            'view_mode': 'form',
            'view_id': self.env.ref('product_module.view_arkite_template_selection').id,
            'target': 'new',
            'context': {
                'default_selection_type': 'template',
                'active_id': self.id,
                'active_model': 'product_module.project',
            }
        }
    
    def action_link_arkite_project(self):
        """Open project selection to link existing Arkite project"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Select Arkite Project to Link'),
            'res_model': 'product_module.arkite.project.selection',
            'view_mode': 'form',
            'view_id': self.env.ref('product_module.view_arkite_project_selection').id,
            'target': 'new',
            'context': {
                'default_selection_type': 'project',
                'active_id': self.id,
                'active_model': 'product_module.project',
            }
        }
    
    def action_load_arkite_project(self):
        """Load Arkite project by ID and auto-load steps, variants, processes, detections"""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_('Please enter an Arkite Project ID first.'))
        
        # Get credentials
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error getting credentials: %s", e)
            raise UserError(_('Error getting API credentials: %s') % str(e))
        
        project_id = self.arkite_project_id
        url = f"{api_base}/projects/{project_id}"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        try:
            _logger.info("Loading Arkite project %s from: %s", project_id, url)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if not response.ok:
                error_text = response.text[:500] if response.text else "No error details"
                _logger.error("Failed to load project: HTTP %s - %s", response.status_code, error_text)
                raise UserError(_('Failed to load project: HTTP %s\n\nError: %s\n\nPlease check:\n1. Project ID is correct: %s\n2. API credentials are valid\n3. Arkite server is accessible') % (response.status_code, error_text, project_id))
            
            project = response.json()
            project_name = project.get("Name") or project.get("ProjectName") or "Unknown"
            
            self.write({
                'arkite_project_name': project_name,
                'arkite_project_loaded': True,
            })
            
            # Auto-load steps, variants, processes, and detections
            self.action_load_arkite_steps()
            self.action_load_arkite_variants()
            self.action_load_arkite_processes()
            self.action_load_arkite_detections()
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Project Loaded'),
                    'message': _('Project "%s" loaded successfully.') % project_name,
                    'type': 'success',
                    'sticky': False,
                }
            }
        except requests.exceptions.ConnectionError as e:
            _logger.error("Connection error loading Arkite project: %s", e, exc_info=True)
            raise UserError(_('Connection error: Cannot reach Arkite API at %s\n\nPlease check:\n1. API Base URL is correct\n2. Arkite server is running and accessible\n3. Network connectivity\n\nError: %s') % (api_base, str(e)))
        except requests.exceptions.Timeout as e:
            _logger.error("Timeout error loading Arkite project: %s", e, exc_info=True)
            raise UserError(_('Timeout error: Arkite API did not respond in time\n\nPlease check:\n1. API Base URL is correct\n2. Arkite server is running\n\nError: %s') % str(e))
        except requests.exceptions.RequestException as e:
            _logger.error("Request error loading Arkite project: %s", e, exc_info=True)
            raise UserError(_('Connection error: %s\n\nPlease check your API configuration.') % str(e))
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error loading Arkite project: %s", e, exc_info=True)
            raise UserError(_('Error loading project: %s') % str(e))
    
    def action_load_arkite_steps(self):
        """Load job steps from Arkite project"""
        self.ensure_one()
        if not self.arkite_project_id:
            return False
        
        # Get credentials
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            _logger.warning("Could not get credentials for loading steps")
            return False
        
        # Clear existing steps
        self.arkite_job_step_ids.unlink()
        
        try:
            url = f"{api_base}/projects/{self.arkite_project_id}/steps/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if response.ok:
                steps = response.json()
                if isinstance(steps, list):
                    # Filter for job steps (ProcessId = 0 or null, or Type = "Job")
                    job_steps = [s for s in steps if s.get("Type") == "Job" or not s.get("ProcessId") or str(s.get("ProcessId")) == "0"]
                    
                    for step in job_steps:
                        self.env['product_module.arkite.job.step.temp'].create({
                            'project_id': self.id,
                            'step_id': str(step.get("Id", "")),
                            'step_name': step.get("Name", "Unnamed"),
                            'step_type': step.get("StepType", "WORK_INSTRUCTION"),
                            'step_instruction': step.get("TextInstruction", {}).get("en-US", "") if isinstance(step.get("TextInstruction"), dict) else "",
                            'sequence': step.get("Index", 0),
                            'index': step.get("Index", 0),
                            'parent_step_id': str(step.get("ParentStepId", "")) if step.get("ParentStepId") else "",
                            'detection_id': str(step.get("DetectionId", "")) if step.get("DetectionId") else "",
                            'material_id': str(step.get("MaterialId", "")) if step.get("MaterialId") else "",
                            'button_id': str(step.get("ButtonId", "")) if step.get("ButtonId") else "",
                        })
        except requests.exceptions.ConnectionError as e:
            _logger.error("Connection error loading steps: %s", e, exc_info=True)
            return False
        except requests.exceptions.Timeout as e:
            _logger.error("Timeout error loading steps: %s", e, exc_info=True)
            return False
        except Exception as e:
            _logger.error("Error loading Arkite steps: %s", e, exc_info=True)
        
        return False
    
    def action_load_arkite_variants(self):
        """Load variants from Arkite project"""
        self.ensure_one()
        if not self.arkite_project_id:
            return False
        
        # Get credentials
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            _logger.warning("Could not get credentials for loading variants")
            return False
        
        # Clear existing variants
        self.arkite_variant_ids.unlink()
        
        try:
            url = f"{api_base}/projects/{self.arkite_project_id}/variants/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("Loading variants from: %s", url)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if response.ok:
                variants = response.json()
                if isinstance(variants, list):
                    for variant in variants:
                        self.env['product_module.arkite.variant.temp'].create({
                            'project_id': self.id,
                            'variant_id': str(variant.get("Id", "")),
                            'name': variant.get("Name", "Unnamed"),
                            'description': variant.get("Description", ""),
                        })
        except requests.exceptions.ConnectionError as e:
            _logger.error("Connection error loading variants: %s", e, exc_info=True)
            return False
        except requests.exceptions.Timeout as e:
            _logger.error("Timeout error loading variants: %s", e, exc_info=True)
            return False
        except Exception as e:
            _logger.error("Error loading Arkite variants: %s", e, exc_info=True)
        
        return False
    
    def action_load_arkite_processes(self):
        """Load processes from Arkite project"""
        self.ensure_one()
        if not self.arkite_project_id:
            return False
        
        # Get credentials
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            _logger.warning("Could not get credentials for loading processes")
            return False
        
        # Clear existing processes
        self.arkite_process_ids.unlink()
        
        try:
            url = f"{api_base}/projects/{self.arkite_project_id}/processes/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("Loading processes from: %s", url)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if response.ok:
                processes = response.json()
                if isinstance(processes, list):
                    for process in processes:
                        self.env['product_module.arkite.process.temp'].create({
                            'project_id': self.id,
                            'process_id': str(process.get("Id", "")),
                            'name': process.get("Name", "Unnamed"),
                            'comment': process.get("Comment", ""),
                        })
        except requests.exceptions.ConnectionError as e:
            _logger.error("Connection error loading processes: %s", e, exc_info=True)
            return False
        except requests.exceptions.Timeout as e:
            _logger.error("Timeout error loading processes: %s", e, exc_info=True)
            return False
        except Exception as e:
            _logger.error("Error loading Arkite processes: %s", e, exc_info=True)
        
        return False
    
    def action_load_process_list(self):
        """Load list of available processes (exact copy from wizard)"""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_("Please link to an Arkite project first."))
        
        # Get credentials
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration.'))
        
        try:
            url = f"{api_base}/projects/{self.arkite_project_id}/processes/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if not response.ok:
                raise UserError(_("Failed to fetch processes: HTTP %s") % response.status_code)
            
            processes = response.json()
            if not isinstance(processes, list):
                raise UserError(_("Unexpected response format for processes"))
            
            if not processes:
                raise UserError(_("No processes found in this project"))
            
            # Clear existing process records
            self.arkite_process_ids.unlink()
            
            # Create process temp records
            process_records = []
            for p in processes:
                process_id = str(p.get("Id", ""))
                process_name = p.get("Name", "Unnamed Process")
                process_comment = p.get("Comment", "")
                
                process_temp = self.env['product_module.arkite.process.temp'].create({
                    'project_id': self.id,
                    'process_id': process_id,
                    'name': process_name,
                    'comment': process_comment
                })
                process_records.append(process_temp.id)
            
            # Auto-select if only one process
            if len(process_records) == 1:
                process_temp = self.env['product_module.arkite.process.temp'].browse(process_records[0])
                self.selected_process_id_char = process_temp.process_id
                self.selected_arkite_process_id = process_temp.process_id
                # Automatically load steps
                return self.action_load_process_steps()
            
            # Reload form to show the loaded processes (one-time action, not disruptive)
            return {'type': 'ir.actions.client', 'tag': 'reload'}
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error loading process list: %s", e, exc_info=True)
            raise UserError(_("Error loading process list: %s") % str(e))
    
    def action_load_process_steps(self):
        """Load process steps for the selected process (like wizard)"""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_("Please link to an Arkite project first."))
        
        # Get selected process ID from char field or from selected_arkite_process_id
        selected_process_id = self.selected_process_id_char or self.selected_arkite_process_id
        if not selected_process_id:
            raise UserError(_("Please select a process first. Enter a process ID or click 'Select' on a process."))
        
        # If selected_process_id_char is a name, try to find matching process
        if selected_process_id and not selected_process_id.isdigit():
            # Try to find by name
            matching_process = self.arkite_process_ids.filtered(
                lambda p: selected_process_id.lower() in p.name.lower()
            )
            if matching_process:
                selected_process_id = matching_process[0].process_id
                self.selected_process_id_char = selected_process_id
                self.selected_arkite_process_id = selected_process_id
        
        # Get credentials
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration.'))
        
        # Clear existing process steps
        self.arkite_process_step_ids.unlink()
        
        try:
            # Get all steps for the project
            url_steps = f"{api_base}/projects/{self.arkite_project_id}/steps/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response_steps = requests.get(url_steps, params=params, headers=headers, verify=False, timeout=10)
            if not response_steps.ok:
                raise UserError(_("Failed to fetch steps: HTTP %s") % response_steps.status_code)
            
            all_steps = response_steps.json()
            if not isinstance(all_steps, list):
                raise UserError(_("Unexpected response format for steps"))
            
            # Filter steps for selected process - include ALL steps (root and child steps)
            selected_process_id_str = str(selected_process_id)
            process_steps = [s for s in all_steps if str(s.get("ProcessId", "")) == selected_process_id_str]
            
            # Sort by Index to maintain order
            process_steps.sort(key=lambda x: x.get("Index", 0))
            
            # Log for debugging
            _logger.info("[ARKITE] Found %s steps for process %s", len(process_steps), selected_process_id_str)
            for step in process_steps:
                _logger.info("[ARKITE] Step: %s (ID: %s, ParentStepId: %s, Index: %s)", 
                           step.get("Name"), step.get("Id"), step.get("ParentStepId"), step.get("Index"))
            
            # Get variants
            url_variants = f"{api_base}/projects/{self.arkite_project_id}/variants/"
            response_variants = requests.get(url_variants, params=params, headers=headers, verify=False, timeout=10)
            
            # Create variant temp records if needed
            variant_map = {}
            if response_variants.ok:
                variants = response_variants.json()
                if isinstance(variants, list):
                    for v in variants:
                        variant_id = str(v.get("Id", ""))
                        # Find or create variant temp record
                        variant_temp = self.env['product_module.arkite.variant.temp'].search([
                            ('variant_id', '=', variant_id),
                            ('project_id', '=', self.id)
                        ], limit=1)
                        if not variant_temp:
                            variant_temp = self.env['product_module.arkite.variant.temp'].create({
                                'project_id': self.id,
                                'variant_id': variant_id,
                                'name': v.get("Name", "Unknown"),
                                'description': v.get("Description", "")
                            })
                        variant_map[variant_id] = variant_temp
            
            # Create process step records - create root steps first, then children
            # Separate root steps (no parent) from child steps (have ParentStepId)
            root_steps = [s for s in process_steps if not s.get("ParentStepId") or str(s.get("ParentStepId", "")) == "0" or str(s.get("ParentStepId", "")) == ""]
            child_steps = [s for s in process_steps if s.get("ParentStepId") and str(s.get("ParentStepId", "")) != "0" and str(s.get("ParentStepId", "")) != ""]
            
            # Sort both lists by Index
            root_steps.sort(key=lambda x: x.get("Index", 0))
            child_steps.sort(key=lambda x: x.get("Index", 0))
            
            _logger.info("[ARKITE] Root steps: %s, Child steps: %s", len(root_steps), len(child_steps))
            
            # Create a mapping of step_id to record for parent lookup
            step_id_to_record = {}
            
            # Create root steps first
            for step in root_steps:
                step_id = str(step.get("Id", ""))
                step_name = step.get("Name") or ""
                if not step_name or not step_name.strip():
                    step_index_val = step.get("Index")
                    if step_index_val is not None:
                        step_name = f"Step {step_index_val}"
                    else:
                        step_name = f"Step {step_id}" if step_id else "Unnamed Step"
                step_type = step.get("StepType", "WORK_INSTRUCTION")
                variant_ids = step.get("VariantIds", [])
                for_all_variants = step.get("ForAllVariants", False)
                step_index = step.get("Index", 0)
                
                # Get variant records for this step
                step_variant_records = []
                for vid in variant_ids:
                    variant_id_str = str(vid)
                    if variant_id_str in variant_map:
                        step_variant_records.append(variant_map[variant_id_str].id)
                
                record = self.env['product_module.arkite.process.step'].create({
                    'project_id': self.id,
                    'process_id': selected_process_id_str,
                    'step_id': step_id,
                    'step_name': step_name,
                    'step_type': step_type,
                    'sequence': step_index * 10,
                    'index': step_index,
                    'parent_step_id': "",  # Root step has no parent
                    'parent_step_record': False,  # No parent record
                    'variant_ids': [(6, 0, step_variant_records)] if step_variant_records else [],
                    'for_all_variants': for_all_variants
                })
                step_id_to_record[step_id] = record
            
            # Create child steps (nested under parent steps) - may need multiple passes for deep nesting
            max_iterations = 10  # Prevent infinite loops
            iteration = 0
            remaining_child_steps = child_steps.copy()
            
            while remaining_child_steps and iteration < max_iterations:
                iteration += 1
                processed_this_iteration = []
                
                for step in remaining_child_steps:
                    step_id = str(step.get("Id", ""))
                    parent_step_id = str(step.get("ParentStepId", ""))
                    
                    # Check if parent already exists
                    if parent_step_id in step_id_to_record:
                        step_name = step.get("Name") or ""
                        if not step_name or not step_name.strip():
                            step_index_val = step.get("Index")
                            if step_index_val is not None:
                                step_name = f"Step {step_index_val}"
                            else:
                                step_name = f"Step {step_id}" if step_id else "Unnamed Step"
                        step_type = step.get("StepType", "WORK_INSTRUCTION")
                        variant_ids = step.get("VariantIds", [])
                        for_all_variants = step.get("ForAllVariants", False)
                        step_index = step.get("Index", 0)
                        
                        # Get variant records for this step
                        step_variant_records = []
                        for vid in variant_ids:
                            variant_id_str = str(vid)
                            if variant_id_str in variant_map:
                                step_variant_records.append(variant_map[variant_id_str].id)
                        
                        parent_record = step_id_to_record[parent_step_id]
                        record = self.env['product_module.arkite.process.step'].create({
                            'project_id': self.id,
                            'process_id': selected_process_id_str,
                            'step_id': step_id,
                            'step_name': step_name,
                            'step_type': step_type,
                            'sequence': step_index * 10,
                            'index': step_index,
                            'parent_step_id': parent_step_id,  # Store parent step ID
                            'parent_step_record': parent_record.id,  # Link to parent record
                            'variant_ids': [(6, 0, step_variant_records)] if step_variant_records else [],
                            'for_all_variants': for_all_variants
                        })
                        step_id_to_record[step_id] = record
                        processed_this_iteration.append(step)
                
                # Remove processed steps
                for step in processed_this_iteration:
                    remaining_child_steps.remove(step)
            
            if remaining_child_steps:
                _logger.warning("[ARKITE] Could not create %s child steps - parent not found", len(remaining_child_steps))
            
            # Invalidate cache to force field refresh
            self.invalidate_recordset(['arkite_process_step_ids', 'selected_arkite_process_name'])
            
            # Ensure data is committed
            self.env.cr.commit()
            
            # Return empty - let JavaScript handle the refresh
            return {}
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error loading process steps: %s", e, exc_info=True)
            raise UserError(_("Error loading process steps: %s") % str(e))
    
    def action_load_arkite_process_steps(self):
        """Load process steps for the selected process"""
        self.ensure_one()
        if not self.arkite_project_id or not self.selected_arkite_process_id:
            raise UserError(_('Please select a process first to load its steps.'))
        
        # Get the process ID from the selected process record
        process_id = self.selected_arkite_process_id.process_id
        
        # Get process name from selected process
        selected_process = self.arkite_process_ids.filtered(
            lambda p: p.process_id == self.selected_arkite_process_id
        )
        process_name = selected_process.name if selected_process else str(process_id)
        
        # Get credentials
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            _logger.warning("Could not get credentials for loading process steps")
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration.'))
        
        # Clear existing process steps
        self.arkite_process_step_ids.unlink()
        
        try:
            # Use the correct API endpoint for process steps
            selected_process_id_str = str(process_id)
            url = f"{api_base}/projects/{self.arkite_project_id}/processes/{selected_process_id_str}/steps/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("Loading process steps for process %s from: %s", process_id, url)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if response.ok:
                process_steps = response.json()
                if isinstance(process_steps, list):
                    process_steps.sort(key=lambda x: x.get("Index", 0))
                    
                    # Get variants for variant assignment
                    variants = {}
                    try:
                        variants_url = f"{api_base}/projects/{self.arkite_project_id}/variants/"
                        variants_response = requests.get(variants_url, params=params, headers=headers, verify=False, timeout=10)
                        if variants_response.ok:
                            variants_list = variants_response.json()
                            if isinstance(variants_list, list):
                                for v in variants_list:
                                    variant_record = self.env['product_module.arkite.variant.temp'].search([
                                        ('project_id', '=', self.id),
                                        ('variant_id', '=', str(v.get("Id", "")))
                                    ], limit=1)
                                    if variant_record:
                                        variants[str(v.get("Id", ""))] = variant_record
                    except Exception as e:
                        _logger.warning("Could not load variants for process steps: %s", e)
                    
                    # Create process step records
                    for step in process_steps:
                        step_variants = []
                        variant_ids = step.get("VariantIds", [])
                        if variant_ids:
                            for variant_id in variant_ids:
                                variant_id_str = str(variant_id)
                                if variant_id_str in variants and variants[variant_id_str]:
                                    step_variants.append((4, variants[variant_id_str].id))
                        
                        self.env['product_module.arkite.process.step'].create({
                            'project_id': self.id,
                            'process_id': selected_process_id_str,
                            'step_id': str(step.get("Id", "")),
                            'step_name': step.get("Name", "Unnamed"),
                            'step_type': step.get("StepType", "WORK_INSTRUCTION"),
                            'sequence': step.get("Index", 0) * 10,  # Convert Index to sequence
                            'index': step.get("Index", 0),
                            'for_all_variants': step.get("ForAllVariants", False),
                            'variant_ids': step_variants,
                        })
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Process Steps Loaded'),
                            'message': _('Loaded %s steps for process "%s".') % (len(process_steps), process_name),
                            'type': 'success',
                            'sticky': False,
                        }
                    }
        except requests.exceptions.ConnectionError as e:
            _logger.error("Connection error loading process steps: %s", e, exc_info=True)
            raise UserError(_('Connection error: Cannot reach Arkite API.\n\nPlease check:\n1. API Base URL is correct\n2. Arkite server is running and accessible\n3. Network connectivity\n\nError: %s') % str(e))
        except requests.exceptions.Timeout as e:
            _logger.error("Timeout error loading process steps: %s", e, exc_info=True)
            raise UserError(_('Timeout error: Arkite API did not respond in time.\n\nError: %s') % str(e))
        except Exception as e:
            _logger.error("Error loading Arkite process steps: %s", e, exc_info=True)
            raise UserError(_('Error loading process steps: %s') % str(e))
        
        return False
    
    
    def action_load_arkite_detections(self):
        """Load detections from Arkite project"""
        self.ensure_one()
        if not self.arkite_project_id:
            return False
        
        # Get credentials
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            _logger.warning("Could not get credentials for loading detections")
            return False
        
        # Clear existing detections
        self.arkite_detection_ids.unlink()
        
        try:
            url = f"{api_base}/projects/{self.arkite_project_id}/detections/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("Loading detections from: %s", url)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if response.ok:
                detections = response.json()
                if isinstance(detections, list):
                    for detection in detections:
                        self.env['product_module.arkite.detection.temp'].create({
                            'project_id': self.id,
                            'detection_id': str(detection.get("Id", "")),
                            'name': detection.get("Name", "Unnamed"),
                            'detection_type': detection.get("DetectionType", "OBJECT"),
                            'is_job_specific': bool(detection.get("JobId")),
                            'job_id': str(detection.get("JobId", "")) if detection.get("JobId") else "",
                        })
        except requests.exceptions.ConnectionError as e:
            _logger.error("Connection error loading detections: %s", e, exc_info=True)
            return False
        except requests.exceptions.Timeout as e:
            _logger.error("Timeout error loading detections: %s", e, exc_info=True)
            return False
        except Exception as e:
            _logger.error("Error loading Arkite detections: %s", e, exc_info=True)
        
        return False
    
    def action_sync_from_arkite(self):
        """Sync project data from Arkite: materials, processes, name, etc."""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_('Please create or link an Arkite project first.'))
        
        # Get credentials
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception as e:
            _logger.error("[ARKITE SYNC] Credential error: %s", e, exc_info=True)
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration. Error: %s') % str(e))
        
        synced_items = []
        error_messages = []
        
        # 1. Sync project name and info
        try:
            url = f"{api_base}/projects/{self.arkite_project_id}"
            params = {"apiKey": api_key}
            response = requests.get(url, params=params, verify=False, timeout=10)
            if response.ok:
                project_data = response.json()
                if isinstance(project_data, dict):
                    arkite_name = project_data.get("Name", "")
                    if arkite_name and arkite_name != self.name:
                        self.write({'name': arkite_name})
                        synced_items.append(_('Project name'))
        except Exception as e:
            _logger.warning("[ARKITE] Error syncing project info: %s", e)
        
        # 2. Sync materials from Arkite
        try:
            url = f"{api_base}/projects/{self.arkite_project_id}/materials/"
            params = {"apiKey": api_key}
            response = requests.get(url, params=params, verify=False, timeout=10)
            if response.ok:
                arkite_materials = response.json()
                _logger.info("[ARKITE SYNC] Fetched %s materials from Arkite", len(arkite_materials) if isinstance(arkite_materials, list) else 0)
                
                if isinstance(arkite_materials, list):
                    # Log all materials from Arkite for debugging
                    _logger.info("[ARKITE SYNC] Raw materials from Arkite: %s", arkite_materials)
                    
                    arkite_material_ids = {str(m.get("Id", "")) for m in arkite_materials if m.get("Id")}
                    existing_material_ids = set(self.material_ids.filtered(lambda m: m.project_id == self and m.arkite_material_id).mapped('arkite_material_id'))
                    
                    _logger.info("[ARKITE SYNC] Arkite has %s materials (IDs: %s)", len(arkite_material_ids), arkite_material_ids)
                    _logger.info("[ARKITE SYNC] Odoo has %s materials with Arkite IDs (IDs: %s)", len(existing_material_ids), existing_material_ids)
                    _logger.info("[ARKITE SYNC] All Odoo materials for this project: %s", [(m.name, m.arkite_material_id) for m in self.material_ids.filtered(lambda m: m.project_id == self)])
                    
                    # Find materials in Arkite but not in Odoo
                    new_material_ids = arkite_material_ids - existing_material_ids
                    _logger.info("[ARKITE SYNC] Found %s new materials to create", len(new_material_ids))
                    
                    created_count = 0
                    updated_count = 0
                    
                    for material_data in arkite_materials:
                        arkite_id = str(material_data.get("Id", ""))
                        if not arkite_id:
                            continue
                            
                        if arkite_id in new_material_ids:
                            # Create new material in Odoo
                            picking_bin_ids = material_data.get("PickingBinIds", [])
                            picking_bin_str = ", ".join(str(bid) for bid in picking_bin_ids) if picking_bin_ids else ""
                            
                            # Map Arkite material type to Odoo type
                            arkite_type = material_data.get("Type", "")
                            if arkite_type == "PickingBinMaterial":
                                odoo_type = "PickingBinMaterial"
                            elif arkite_type == "StandardMaterial":
                                odoo_type = "StandardMaterial"
                            elif arkite_type == "Material" or not arkite_type:
                                # Default to StandardMaterial if type is "Material" or empty
                                odoo_type = "StandardMaterial"
                            else:
                                # Unknown type, default to StandardMaterial
                                _logger.warning("[ARKITE SYNC] Unknown material type '%s', defaulting to StandardMaterial", arkite_type)
                                odoo_type = "StandardMaterial"
                            
                            try:
                                self.env['product_module.material'].create({
                                    'project_id': self.id,
                                    'page_id': self.page_id.id if self.page_id else False,
                                    'name': material_data.get("Name", "Unnamed"),
                                    'material_type': odoo_type,
                                    'description': material_data.get("Description", ""),
                                    'image_id': str(material_data.get("ImageId", "")) if material_data.get("ImageId") and material_data.get("ImageId") != "0" else "",
                                    'picking_bin_ids_text': picking_bin_str,
                                    'arkite_material_id': arkite_id,
                                })
                                created_count += 1
                                _logger.info("[ARKITE SYNC] Created material: %s (ID: %s, Type: %s -> %s)", 
                                           material_data.get("Name"), arkite_id, arkite_type, odoo_type)
                            except Exception as e:
                                _logger.error("[ARKITE SYNC] Error creating material %s: %s", arkite_id, e, exc_info=True)
                    
                    # Update existing materials
                    for material in self.material_ids.filtered(lambda m: m.project_id == self):
                        if material.arkite_material_id and material.arkite_material_id in arkite_material_ids:
                            # Find matching Arkite material
                            for arkite_material in arkite_materials:
                                if str(arkite_material.get("Id", "")) == material.arkite_material_id:
                                    picking_bin_ids = arkite_material.get("PickingBinIds", [])
                                    picking_bin_str = ", ".join(str(bid) for bid in picking_bin_ids) if picking_bin_ids else ""
                                    
                                    # Map Arkite material type to Odoo type
                                    arkite_type = arkite_material.get("Type", "")
                                    if arkite_type == "PickingBinMaterial":
                                        odoo_type = "PickingBinMaterial"
                                    elif arkite_type == "StandardMaterial":
                                        odoo_type = "StandardMaterial"
                                    elif arkite_type == "Material" or not arkite_type:
                                        odoo_type = "StandardMaterial"
                                    else:
                                        odoo_type = material.material_type  # Keep existing type if unknown
                                    
                                    material.write({
                                        'name': arkite_material.get("Name", material.name),
                                        'material_type': odoo_type,
                                        'description': arkite_material.get("Description", material.description or ""),
                                        'image_id': str(arkite_material.get("ImageId", "")) if arkite_material.get("ImageId") else material.image_id,
                                        'picking_bin_ids_text': picking_bin_str,
                                    })
                                    updated_count += 1
                                    _logger.info("[ARKITE SYNC] Updated material: %s (ID: %s)", material.name, material.arkite_material_id)
                                    break
                        elif not material.arkite_material_id:
                            # Material exists in Odoo but doesn't have Arkite ID - try to match by name
                            for arkite_material in arkite_materials:
                                arkite_name = arkite_material.get("Name", "")
                                if arkite_name and arkite_name == material.name:
                                    # Link this material to Arkite material
                                    picking_bin_ids = arkite_material.get("PickingBinIds", [])
                                    picking_bin_str = ", ".join(str(bid) for bid in picking_bin_ids) if picking_bin_ids else ""
                                    
                                    # Map Arkite material type to Odoo type
                                    arkite_type = arkite_material.get("Type", "")
                                    if arkite_type == "PickingBinMaterial":
                                        odoo_type = "PickingBinMaterial"
                                    elif arkite_type == "StandardMaterial":
                                        odoo_type = "StandardMaterial"
                                    elif arkite_type == "Material" or not arkite_type:
                                        odoo_type = "StandardMaterial"
                                    else:
                                        odoo_type = material.material_type  # Keep existing type if unknown
                                    
                                    material.write({
                                        'arkite_material_id': str(arkite_material.get("Id", "")),
                                        'material_type': odoo_type,
                                        'description': arkite_material.get("Description", material.description or ""),
                                        'image_id': str(arkite_material.get("ImageId", "")) if arkite_material.get("ImageId") else material.image_id,
                                        'picking_bin_ids_text': picking_bin_str,
                                    })
                                    updated_count += 1
                                    _logger.info("[ARKITE SYNC] Linked material by name: %s (ID: %s)", material.name, material.arkite_material_id)
                                    break
                    
                    if created_count > 0:
                        synced_items.append(_('%s new material(s)') % created_count)
                    if updated_count > 0:
                        synced_items.append(_('%s updated material(s)') % updated_count)
                else:
                    _logger.warning("[ARKITE SYNC] Materials response is not a list: %s", type(arkite_materials))
                    error_messages.append(_('Unexpected response format from Arkite API'))
            else:
                error_text = response.text[:500] if response.text else "No response body"
                _logger.error("[ARKITE SYNC] Failed to fetch materials: HTTP %s - %s", response.status_code, error_text)
                error_messages.append(_('Failed to fetch materials: HTTP %s') % response.status_code)
        except requests.exceptions.RequestException as e:
            _logger.error("[ARKITE SYNC] Network error syncing materials: %s", e, exc_info=True)
            error_messages.append(_('Network error: %s') % str(e))
        except Exception as e:
            _logger.error("[ARKITE SYNC] Error syncing materials: %s", e, exc_info=True)
            error_messages.append(_('Error: %s') % str(e))
        
        # 3. Sync processes from Arkite
        # Try both endpoints: /processes/ and /steps/ (some projects might have processes as steps)
        try:
            arkite_processes = []
            
            # First try: GET /projects/{projectId}/processes/
            url = f"{api_base}/projects/{self.arkite_project_id}/processes/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("[ARKITE SYNC] Fetching processes from: %s (project ID: %s)", url, self.arkite_project_id)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            _logger.info("[ARKITE SYNC] Processes endpoint response status: %s", response.status_code)
            
            if response.ok:
                processes_from_endpoint = response.json()
                if isinstance(processes_from_endpoint, list):
                    arkite_processes = processes_from_endpoint
                    _logger.info("[ARKITE SYNC] Got %s processes from /processes/ endpoint", len(arkite_processes))
            
            # If no processes found, try getting from /steps/ endpoint and extract unique ProcessIds
            if not arkite_processes or len(arkite_processes) == 0:
                _logger.info("[ARKITE SYNC] No processes from /processes/ endpoint, trying /steps/ endpoint...")
                steps_url = f"{api_base}/projects/{self.arkite_project_id}/steps/"
                steps_response = requests.get(steps_url, params=params, headers=headers, verify=False, timeout=10)
                _logger.info("[ARKITE SYNC] Steps endpoint response status: %s", steps_response.status_code)
                
                if steps_response.ok:
                    all_steps = steps_response.json()
                    _logger.info("[ARKITE SYNC] Steps endpoint returned %s steps", len(all_steps) if isinstance(all_steps, list) else 0)
                    _logger.info("[ARKITE SYNC] First 3 steps sample: %s", all_steps[:3] if isinstance(all_steps, list) and len(all_steps) > 0 else "No steps")
                    
                    if isinstance(all_steps, list):
                        # Extract unique ProcessIds (non-zero ProcessIds are processes)
                        process_ids_found = {}
                        for step in all_steps:
                            process_id = step.get("ProcessId")
                            step_type = step.get("Type", "")
                            step_name = step.get("Name", "")
                            
                            # Log step details for debugging
                            _logger.info("[ARKITE SYNC] Step: Name='%s', Type='%s', ProcessId='%s', Id='%s'", 
                                       step_name, step_type, process_id, step.get("Id", ""))
                            
                            # Check if this step represents a process
                            # ProcessId can be 0, null, or a number. If it's a number > 0, it's a process step
                            # But we need to find the actual process definitions, not just process steps
                            # Processes might be steps with Type="Process" or similar
                            if process_id and str(process_id) != "0" and str(process_id) not in process_ids_found:
                                # Create a process-like object from the step
                                process_ids_found[str(process_id)] = {
                                    "Id": process_id,
                                    "Name": step_name or f"Process {process_id}",
                                    "Comment": step.get("Comment", ""),
                                }
                        
                        if process_ids_found:
                            arkite_processes = list(process_ids_found.values())
                            _logger.info("[ARKITE SYNC] Found %s processes from /steps/ endpoint (extracted from ProcessIds)", len(arkite_processes))
                        else:
                            _logger.warning("[ARKITE SYNC] No processes found in /steps/ endpoint. All %s steps have ProcessId=0, null, or no ProcessId", len(all_steps))
                            _logger.info("[ARKITE SYNC] This might mean: 1) Project has no processes, 2) Processes are job steps (ProcessId=0), or 3) Processes need to be created first")
            
            # Now process the arkite_processes list (from either endpoint)
            _logger.info("[ARKITE SYNC] Total processes found: %s", len(arkite_processes) if isinstance(arkite_processes, list) else 0)
            
            if isinstance(arkite_processes, list) and len(arkite_processes) == 0:
                _logger.warning("[ARKITE SYNC] No processes found in Arkite project %s after checking both /processes/ and /steps/ endpoints", self.arkite_project_id)
            else:
                _logger.info("[ARKITE SYNC] Raw processes from Arkite: %s", arkite_processes)
                # Log each process individually
                for idx, proc in enumerate(arkite_processes):
                    _logger.info("[ARKITE SYNC] Process %s: %s", idx + 1, proc)
                
                if isinstance(arkite_processes, list) and len(arkite_processes) > 0:
                    # Get existing process IDs from instruction_ids (Assembly Processes)
                    # Filter by project_id.id == self.id to ensure correct comparison
                    existing_instructions = self.instruction_ids.filtered(lambda i: i.project_id.id == self.id and i.arkite_process_id)
                    existing_process_ids = set(existing_instructions.mapped('arkite_process_id'))
                    arkite_process_ids = {str(p.get("Id", "")) for p in arkite_processes if p.get("Id")}
                    
                    _logger.info("[ARKITE SYNC] Total instruction_ids for this project: %s", len(self.instruction_ids))
                    _logger.info("[ARKITE SYNC] Instructions with project_id=%s: %s", self.id, len(self.instruction_ids.filtered(lambda i: i.project_id.id == self.id)))
                    _logger.info("[ARKITE SYNC] Instructions with arkite_process_id: %s", len(existing_instructions))
                    _logger.info("[ARKITE SYNC] Arkite has %s processes (IDs: %s)", len(arkite_process_ids), arkite_process_ids)
                    _logger.info("[ARKITE SYNC] Odoo has %s processes with Arkite IDs (IDs: %s)", len(existing_process_ids), existing_process_ids)
                    
                    new_process_ids = arkite_process_ids - existing_process_ids
                    _logger.info("[ARKITE SYNC] Found %s new processes to create", len(new_process_ids))
                    
                    process_created_count = 0
                    process_updated_count = 0
                    
                    for process_data in arkite_processes:
                        arkite_process_id = str(process_data.get("Id", ""))
                        if not arkite_process_id:
                            _logger.warning("[ARKITE SYNC] Process data missing Id: %s", process_data)
                            continue
                        
                        process_name = process_data.get("Name", "Unnamed Process")
                        _logger.info("[ARKITE SYNC] Processing process: Name='%s', Id='%s'", process_name, arkite_process_id)
                        
                        if arkite_process_id in new_process_ids:
                            # Create new process in instruction_ids (Assembly Processes)
                            try:
                                new_instruction = self.env['product_module.instruction'].create({
                                    'project_id': self.id,
                                    'title': process_name,
                                    'sequence': process_created_count * 10 + 10,  # Auto-increment sequence
                                    'arkite_process_id': arkite_process_id,
                                    'arkite_process_type': process_data.get("Type", ""),
                                    'arkite_comment': process_data.get("Comment", ""),
                                })
                                process_created_count += 1
                                _logger.info("[ARKITE SYNC] Successfully created assembly process: %s (ID: %s, Odoo ID: %s)", 
                                           process_name, arkite_process_id, new_instruction.id)
                            except Exception as e:
                                _logger.error("[ARKITE SYNC] Error creating assembly process %s (ID: %s): %s", 
                                            process_name, arkite_process_id, e, exc_info=True)
                        elif arkite_process_id in existing_process_ids:
                            # Update existing process
                            process = self.instruction_ids.filtered(lambda i: i.project_id.id == self.id and i.arkite_process_id == arkite_process_id)
                            if process:
                                # Map Arkite trigger to Odoo trigger field
                                arkite_trigger = process_data.get("ProcessTrigger") or process_data.get("Trigger") or ""
                                trigger_mapping = {
                                    'ProjectLoaded': 'project_loaded',
                                    'AlarmClock': 'alarm_clock',
                                    'ReceiveCommunication': 'receive_communication',
                                    'Timer': 'timer',
                                    'VariableChanged': 'variable_changed',
                                    'Watchdog': 'watchdog',
                                }
                                process_trigger = trigger_mapping.get(arkite_trigger, 'project_loaded') if arkite_trigger else 'project_loaded'
                                
                                process.write({
                                    'title': process_name,
                                    'arkite_process_type': process_data.get("Type", ""),
                                    'arkite_comment': process_data.get("Comment", ""),
                                    'process_trigger': process_trigger,
                                })
                                process_updated_count += 1
                                _logger.info("[ARKITE SYNC] Updated assembly process: %s (ID: %s)", process.title, arkite_process_id)
                    
                    # If no processes have Arkite IDs, try to match by name for all processes
                    if not existing_process_ids:
                        for process_data in arkite_processes:
                            arkite_process_id = str(process_data.get("Id", ""))
                            if not arkite_process_id:
                                continue
                            
                            process_name = process_data.get("Name", "")
                            process = self.instruction_ids.filtered(lambda i: i.project_id.id == self.id and i.title == process_name and not i.arkite_process_id)
                            if process:
                                process.write({
                                    'arkite_process_id': arkite_process_id,
                                    'title': process_name,
                                })
                                process_updated_count += 1
                                _logger.info("[ARKITE SYNC] Linked assembly process by name: %s (ID: %s)", process.title, arkite_process_id)
                    
                    if process_created_count > 0:
                        synced_items.append(_('%s new process(es)') % process_created_count)
                    if process_updated_count > 0:
                        synced_items.append(_('%s updated process(es)') % process_updated_count)
                    
                    _logger.info("[ARKITE SYNC] Assembly process sync summary: Created=%s, Updated=%s, Total in Arkite=%s", 
                               process_created_count, process_updated_count, len(arkite_processes))
                    
                    # Force refresh of instruction_ids to ensure UI updates
                    if process_created_count > 0 or process_updated_count > 0:
                        # Invalidate cache and recompute count
                        self.invalidate_recordset(['instruction_ids', 'instruction_count'])
                        # Force recompute of instruction_count
                        self._compute_instruction_count()
                        _logger.info("[ARKITE SYNC] Refreshed instruction_ids cache. Current count: %s", len(self.instruction_ids))
                        _logger.info("[ARKITE SYNC] instruction_count field value: %s", self.instruction_count)
        except requests.exceptions.RequestException as e:
            _logger.error("[ARKITE SYNC] Network error syncing processes: %s", e, exc_info=True)
            error_messages.append(_('Network error syncing processes: %s') % str(e))
        except Exception as e:
            _logger.error("[ARKITE SYNC] Error syncing processes: %s", e, exc_info=True)
            error_messages.append(_('Error syncing processes: %s') % str(e))
        
        # Invalidate cache to force form refresh
        self.invalidate_recordset(['material_ids', 'instruction_ids', 'arkite_process_ids'])
        
        # Determine message type
        if error_messages:
            msg_type = 'warning'
        elif synced_items:
            msg_type = 'success'
        else:
            msg_type = 'info'
        
        message = _('Synced from Arkite: %s') % ', '.join(synced_items) if synced_items else _('No changes found in Arkite project.')
        
        # Log sync summary
        _logger.info("[ARKITE SYNC] Sync complete: %s", message)
        
        # Return notification - JavaScript will handle field refresh without full page reload
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sync Complete'),
                'message': message,
                'type': msg_type,
                'sticky': True if error_messages else False,
            }
        }
    
    def action_link_existing_materials(self):
        """Open a wizard to select and link existing materials to this project"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Link Existing Materials',
            'res_model': 'product_module.material.link.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_project_id': self.id,
                'active_id': self.id,
            },
        }
    
    def action_load_arkite_materials(self):
        """Load materials from Arkite project"""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_('Please create or link an Arkite project first.'))
        
        # Get credentials
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            _logger.warning("Could not get credentials for loading materials")
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration.'))
        
        # Clear existing materials
        self.arkite_material_ids.unlink()
        
        try:
            url = f"{api_base}/projects/{self.arkite_project_id}/materials/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("Loading materials from: %s", url)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if response.ok:
                materials = response.json()
                if isinstance(materials, list):
                    for material in materials:
                        picking_bin_ids = material.get("PickingBinIds", [])
                        picking_bin_str = ", ".join(str(bid) for bid in picking_bin_ids) if picking_bin_ids else ""
                        
                        self.env['product_module.arkite.material.temp'].create({
                            'project_id': self.id,
                            'material_id': str(material.get("Id", "")),
                            'name': material.get("Name", "Unnamed"),
                            'material_type': material.get("Type", "PickingBinMaterial"),
                            'description': material.get("Description", ""),
                            'image_id': str(material.get("ImageId", "")) if material.get("ImageId") else "",
                            'picking_bin_ids_text': picking_bin_str,
                        })
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Materials Loaded'),
                            'message': _('Loaded %s materials from Arkite project.') % len(materials),
                            'type': 'success',
                            'sticky': False,
                        }
                    }
        except requests.exceptions.ConnectionError as e:
            _logger.error("Connection error loading materials: %s", e, exc_info=True)
            raise UserError(_('Connection error: Cannot reach Arkite API.\n\nPlease check:\n1. API Base URL is correct\n2. Arkite server is running and accessible\n3. Network connectivity\n\nError: %s') % str(e))
        except requests.exceptions.Timeout as e:
            _logger.error("Timeout error loading materials: %s", e, exc_info=True)
            raise UserError(_('Timeout error: Arkite API did not respond in time.\n\nError: %s') % str(e))
        except Exception as e:
            _logger.error("Error loading Arkite materials: %s", e, exc_info=True)
            raise UserError(_('Error loading materials: %s') % str(e))
        
        return False
    
    def action_help_browse_images(self):
        """Show available Arkite image IDs in a notification"""
        self.ensure_one()
        if not self.arkite_project_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Arkite Project'),
                    'message': _('Please link this project to an Arkite project first.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('API Error'),
                    'message': _('Could not get API credentials. Please check your Arkite unit configuration.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        url = f"{api_base}/projects/{self.arkite_project_id}/images/"
        params = {"apiKey": api_key}
        
        try:
            response = requests.get(url, params=params, verify=False, timeout=10)
            if not response.ok:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Failed to fetch images: HTTP %s') % response.status_code,
                        'type': 'warning',
                        'sticky': False,
                    }
                }
            
            images = response.json()
            if not isinstance(images, list):
                images = []
            
            if not images:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Images Found'),
                        'message': _('No images found in this Arkite project. Upload images in Arkite first.'),
                        'type': 'info',
                        'sticky': False,
                    }
                }
            
            image_ids = [str(img.get('Id', '')) for img in images if img.get('Id')]
            if image_ids:
                message = _('Available Image IDs: %s\n\nCopy an ID and paste it into the Image ID field.') % ', '.join(image_ids[:30])
                if len(image_ids) > 30:
                    message += _('\n(Showing first 30 of %s images)') % len(image_ids)
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Available Images (%s)') % len(image_ids),
                        'message': message,
                        'type': 'info',
                        'sticky': True,
                    }
                }
        except Exception as e:
            _logger.error("Error fetching images: %s", e)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error connecting to Arkite API: %s') % str(e),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        return False
    
    def action_help_load_picking_bins(self):
        """Load picking bin IDs from detections into the first material with empty picking_bin_ids_text"""
        self.ensure_one()
        if not self.arkite_project_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Arkite Project'),
                    'message': _('Please link this project to an Arkite project first.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Get picking bin detections
        picking_bin_detections = self.env['product_module.arkite.detection.temp'].search([
            ('project_id', '=', self.id),
            ('detection_type', '=', 'PICKING_BIN')
        ])
        
        if not picking_bin_detections:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Picking Bins Found'),
                    'message': _('No picking bin detections found. Load detections first in the Detections tab.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        picking_bin_ids = [det.detection_id for det in picking_bin_detections if det.detection_id]
        if not picking_bin_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Valid IDs'),
                    'message': _('No valid picking bin IDs found in detections.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Find first material with empty picking_bin_ids_text
        material = self.material_ids.filtered(lambda m: not m.picking_bin_ids_text or not m.picking_bin_ids_text.strip())
        if not material:
            # If all have picking bins, use the first one
            material = self.material_ids[0] if self.material_ids else None
        
        if material:
            material.picking_bin_ids_text = ", ".join(picking_bin_ids)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Picking Bins Loaded'),
                    'message': _('Loaded %s picking bin ID(s) into material "%s".') % (len(picking_bin_ids), material.name),
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Materials'),
                    'message': _('Please add a material first.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
    
    def action_manage_arkite_steps(self):
        """Open Arkite step management for this project"""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_('Please create or link an Arkite project first.'))
        
        # Create or get existing wizard record for this project
        wizard = self.env['product_module.arkite.job.step.wizard'].search([
            ('project_id', '=', self.arkite_project_id)
        ], limit=1)
        
        if not wizard:
            wizard = self.env['product_module.arkite.job.step.wizard'].create({
                'project_id': self.arkite_project_id,
            })
            # Auto-load the project
            wizard.action_load_project()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manage Arkite Steps - %s') % self.name,
            'res_model': 'product_module.arkite.job.step.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _get_arkite_project_id_by_name(self, project_name):
        """Get Arkite project ID by name"""
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except UserError:
            return None
        
        url = f"{api_base}/projects/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if response.ok:
                projects = response.json()
                if isinstance(projects, list):
                    for proj in projects:
                        if proj.get("Name") == project_name:
                            return str(proj.get("Id") or proj.get("ProjectId"))
        except Exception as e:
            _logger.error("Error fetching Arkite projects: %s", e)
        
        return None
    
    @api.onchange('arkite_project_id')
    def _onchange_arkite_project_id(self):
        """Load Arkite project name when ID is set and auto-load processes"""
        if self.arkite_project_id:
            try:
                creds = self._get_arkite_credentials()
                api_base = creds['api_base']
                api_key = creds['api_key']
                
                url = f"{api_base}/projects/{self.arkite_project_id}"
                params = {"apiKey": api_key}
                headers = {"Content-Type": "application/json"}
                
                try:
                    response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                    if response.ok:
                        project = response.json()
                        self.arkite_project_name = project.get("Name") or ""
                        
                        # Auto-load processes if not already loaded
                        if self.arkite_linked and not self.arkite_process_ids:
                            try:
                                self.action_load_process_list()
                            except Exception:
                                pass  # Don't show error, just skip auto-load
                        # Optionally auto-load the project
                        # self.action_load_arkite_project()
                except Exception:
                    pass
            except UserError:
                pass
    
    def unlink(self):
        """Override unlink to delete project from Arkite when deleted in Odoo"""
        # Store Arkite project IDs before deletion
        arkite_project_ids = []
        for record in self:
            if record.arkite_project_id:
                arkite_project_ids.append(record.arkite_project_id)
        
        # Delete from Odoo first
        result = super().unlink()
        
        # Delete from Arkite after Odoo deletion succeeds
        if arkite_project_ids:
            for record in self:
                try:
                    creds = record._get_arkite_credentials()
                    api_base = creds['api_base']
                    api_key = creds['api_key']
                    
                    for arkite_project_id in arkite_project_ids:
                        try:
                            url = f"{api_base}/projects/{arkite_project_id}"
                            params = {"apiKey": api_key}
                            headers = {"Content-Type": "application/json"}
                            
                            # Delete project from Arkite
                            response = requests.delete(url, params=params, headers=headers, verify=False, timeout=10)
                            if response.ok:
                                _logger.info("[ARKITE] Deleted project %s", arkite_project_id)
                            elif response.status_code == 404:
                                # Already deleted - that's fine
                                _logger.debug("[ARKITE] Project %s already deleted", arkite_project_id)
                            else:
                                _logger.warning("[ARKITE] Failed to delete project %s: HTTP %s", arkite_project_id, response.status_code)
                        except Exception as e:
                            _logger.warning("[ARKITE] Error deleting project %s: %s", arkite_project_id, e)
                            # Continue with deletion even if API call fails
                except UserError:
                    # No credentials available - skip deletion
                    _logger.warning("[ARKITE] No credentials available to delete project")
                    pass
        
        return result
    
    def write(self, vals):
        """Override write to sync all materials to Arkite when project is saved, and delete removed materials"""
        # Track materials before write to detect removals
        materials_before = set()
        if self.arkite_project_id and 'material_ids' not in vals:
            # If material_ids is being modified, track current materials
            materials_before = set(self.material_ids.filtered(lambda m: m.project_id == self and m.arkite_material_id).mapped('arkite_material_id'))
        
        result = super().write(vals)
        
        # After saving, sync all materials to Arkite if project has Arkite project linked
        if self.arkite_project_id:
            # Get current materials with Arkite IDs
            materials_after = set(self.material_ids.filtered(lambda m: m.project_id == self and m.arkite_material_id).mapped('arkite_material_id'))
            
            # Find materials that were removed (had Arkite ID before but not in current list)
            removed_material_ids = materials_before - materials_after
            
            # Delete removed materials from Arkite
            if removed_material_ids:
                try:
                    creds = self._get_arkite_credentials()
                    api_base = creds['api_base']
                    api_key = creds['api_key']
                    
                    for arkite_material_id in removed_material_ids:
                        url = f"{api_base}/projects/{self.arkite_project_id}/materials/{arkite_material_id}/"
                        params = {"apiKey": api_key}
                        try:
                            response = requests.delete(url, params=params, verify=False, timeout=10)
                            if response.ok:
                                _logger.info("[ARKITE] Deleted material %s from project", arkite_material_id)
                            else:
                                _logger.warning("[ARKITE] Failed to delete material %s: HTTP %s", arkite_material_id, response.status_code)
                        except Exception as e:
                            _logger.warning("[ARKITE] Error deleting material %s: %s", arkite_material_id, e)
                except Exception as e:
                    _logger.warning("[ARKITE] Could not get credentials to delete materials: %s", e)
            
            # Sync current materials to Arkite
            for material in self.material_ids:
                if material.project_id == self:
                    # Sync material to Arkite (create if no arkite_material_id, update if exists)
                    if not material.arkite_material_id:
                        material._sync_to_arkite(create=True)
                    else:
                        material._sync_to_arkite(create=False)
        
        return result

