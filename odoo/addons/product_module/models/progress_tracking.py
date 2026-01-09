# product_module/models/progress_tracking.py - FIXED VERSION
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class ProductModuleProgress(models.Model):
    _name = 'product_module.progress'
    _description = 'Unit Progress Tracking'
    _order = 'name'
    
    @api.model
    def create(self, vals):
        """Auto-create Arkite Unit when Progress unit is created with all required fields"""
        record = super().create(vals)
        # Auto-create Arkite Unit if all required fields are present
        if record.arkite_unit_id and record.arkite_api_base and record.arkite_api_key:
            try:
                record._auto_create_arkite_unit()
            except Exception as e:
                _logger.warning("Failed to auto-create Arkite Unit: %s", e)
        return record
    
    def write(self, vals):
        """Auto-create or update Arkite Unit when Progress unit is updated with all required fields"""
        result = super().write(vals)
        # Check if any required fields were updated
        if any(field in vals for field in ['arkite_unit_id', 'arkite_api_base', 'arkite_api_key', 'name', 'arkite_template_name']):
            for record in self:
                if record.arkite_unit_id and record.arkite_api_base and record.arkite_api_key:
                    try:
                        record._auto_create_arkite_unit()
                    except Exception as e:
                        _logger.warning("Failed to auto-create/update Arkite Unit: %s", e)
        return result
    
    def _auto_create_arkite_unit(self):
        """Internal method to automatically create or update Arkite Unit"""
        self.ensure_one()
        if not self.arkite_unit_id or not self.arkite_api_base or not self.arkite_api_key:
            return
        
        # Check if Arkite Unit already exists with this unit_id
        existing = self.env['product_module.arkite.unit'].search([
            ('unit_id', '=', self.arkite_unit_id)
        ], limit=1)
        
        if existing:
            # Update existing unit with latest info
            existing.write({
                'name': self.name,
                'api_base': self.arkite_api_base,
                'api_key': self.arkite_api_key,
                'template_name': self.arkite_template_name or '',
                'active': True,
            })
        else:
            # Create new Arkite Unit
            self.env['product_module.arkite.unit'].create({
                'name': self.name,
                'unit_id': self.arkite_unit_id,
                'api_base': self.arkite_api_base,
                'api_key': self.arkite_api_key,
                'template_name': self.arkite_template_name or '',
                'active': True,
                'description': f'Auto-created from Unit Tracking: {self.name}',
            })

    # Basic fields
    name = fields.Char(string='Unit Name', required=True)

    # Relationships
    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    product_id = fields.Many2one('product_module.product', string='Product')
    
    # Arkite Project Tracking
    arkite_project_id = fields.Char(
        string='Arkite Project ID',
        help='ID of the currently loaded Arkite project on this unit'
    )
    arkite_project_name = fields.Char(
        string='Arkite Project Name',
        compute='_compute_arkite_project_info',
        store=False,
        help='Name of the currently loaded Arkite project'
    )
    arkite_projects_list_id = fields.Many2one(
        'product_module.arkite.unit.projects',
        string='Projects List',
        compute='_compute_projects_list',
        store=False,
        help='Temporary list of available projects'
    )
    arkite_projects_html = fields.Html(
        compute='_compute_projects_html',
        store=False,
        string='Available Projects'
    )
    
    # Arkite API Configuration
    arkite_unit_id = fields.Char(
        string='Arkite Unit ID',
        help='Arkite Unit ID (numeric ID from Arkite system). Leave empty if not using Arkite.'
    )
    arkite_api_base = fields.Char(
        string='Arkite API Base URL',
        help='Base URL for Arkite API (e.g., https://192.168.178.93/api/v1). Leave empty if not using Arkite.'
    )
    arkite_api_key = fields.Char(
        string='Arkite API Key',
        help='API key for this unit. Leave empty if not using Arkite.'
    )
    arkite_template_name = fields.Char(
        string='Arkite Template Name',
        help='Default template project name to use for this unit (optional)'
    )

    # Progress tracking
    progress_percentage = fields.Integer(string='Progress %', compute='_compute_progress_percentage', store=True)
    total_steps = fields.Integer(string='Total Processes', compute='_compute_total_steps', store=True)
    completed_steps = fields.Integer(string='Completed Steps', default=0)

    # Display fields for better UX
    product_name = fields.Char(string='Product Name', related='product_id.name', store=True)
    product_code = fields.Char(string='Product Code', related='product_id.product_code', store=True)
    product_image = fields.Binary(string='Product Image', related='product_id.image')
    product_description = fields.Text(string='Product Description', related='product_id.description')
    instruction_count = fields.Integer(string='Process Count', related='product_id.instruction_count')
    
    # Current step information
    current_step_number = fields.Integer(string='Current Step Number', compute='_compute_current_step_info', store=False)
    current_step_title = fields.Char(string='Current Step Title', compute='_compute_current_step_info', store=False)
    current_step_description = fields.Text(string='Current Step Description', compute='_compute_current_step_info', store=False)
    
    # Arkite project progress (from API)
    arkite_loaded_project_id = fields.Char(
        string='Loaded Project ID',
        compute='_compute_arkite_project_info',
        store=False,
        help='ID of project currently loaded on the unit (from Arkite API)'
    )
    arkite_loaded_project_name = fields.Char(
        string='Loaded Project Name',
        compute='_compute_arkite_project_info',
        store=False,
        help='Name of project currently loaded on the unit (from Arkite API)'
    )
    arkite_active_process_id = fields.Char(
        string='Active Process ID',
        compute='_compute_arkite_project_info',
        store=False,
        help='ID of currently active process on the unit'
    )
    arkite_active_step_info = fields.Text(
        string='Active Step Info',
        compute='_compute_arkite_project_info',
        store=False,
        help='Information about the currently active step'
    )

    @api.depends('completed_steps', 'total_steps')
    def _compute_progress_percentage(self):
        for record in self:
            if record.total_steps > 0:
                record.progress_percentage = min(100, int((record.completed_steps / record.total_steps) * 100))
            else:
                record.progress_percentage = 0

    @api.depends('product_id', 'product_id.instruction_ids')
    def _compute_total_steps(self):
        """Compute total_steps based on product process count - FIXED VERSION"""
        for record in self:
            if record.product_id and record.product_id.instruction_ids:
                # Always get the current process count from the product
                record.total_steps = len(record.product_id.instruction_ids)
            elif record.product_id:
                record.total_steps = 0
            else:
                record.total_steps = 0

    @api.depends('completed_steps', 'product_id', 'product_id.instruction_ids')
    def _compute_current_step_info(self):
        """Get current step information from product processes or Arkite"""
        for record in self:
            # Priority: Use Arkite project info if available
            if record.arkite_loaded_project_id:
                if record.arkite_active_step_info:
                    record.current_step_title = f'Project: {record.arkite_loaded_project_name or "Unknown"}'
                    record.current_step_description = record.arkite_active_step_info
                    # Try to extract step number from info
                    try:
                        if 'Step' in record.arkite_active_step_info:
                            parts = record.arkite_active_step_info.split('Step')
                            if len(parts) > 1:
                                step_num = parts[1].strip().split()[0]
                                record.current_step_number = int(step_num)
                            else:
                                record.current_step_number = 1
                        else:
                            record.current_step_number = 1
                    except:
                        record.current_step_number = 1
                else:
                    record.current_step_number = 0
                    record.current_step_title = f'Project: {record.arkite_loaded_project_name or "Unknown"}'
                    record.current_step_description = 'No active step information available'
                continue
            
            # Fallback to product-based tracking
            if not record.product_id or not record.product_id.instruction_ids:
                record.current_step_number = 0
                record.current_step_title = 'No processes available'
                record.current_step_description = 'Add processes to the product or load an Arkite project'
                continue
                
            # Get sorted processes
            instructions = record.product_id.instruction_ids.sorted('sequence')
            
            if record.completed_steps >= len(instructions):
                # All steps completed
                record.current_step_number = len(instructions)
                record.current_step_title = 'All steps completed'
                record.current_step_description = 'Process is finished'
            else:
                # Get next process to complete (current step)
                current_instruction = instructions[record.completed_steps]
                record.current_step_number = record.completed_steps + 1
                record.current_step_title = current_instruction.title or f'Step {record.completed_steps + 1}'
                # Get the process step label
                process_step_label = dict(current_instruction._fields['process_step'].selection).get(current_instruction.process_step, 'No process step selected')
                record.current_step_description = process_step_label
    
    def _compute_projects_list(self):
        """Get or create the projects list record"""
        for record in self:
            if record.id:
                projects_record = self.env['product_module.arkite.unit.projects'].search([
                    ('progress_id', '=', record.id)
                ], limit=1)
                if not projects_record:
                    projects_record = self.env['product_module.arkite.unit.projects'].create({
                        'progress_id': record.id,
                    })
                record.arkite_projects_list_id = projects_record.id
            else:
                record.arkite_projects_list_id = False
    
    @api.depends('arkite_projects_list_id', 'arkite_projects_list_id.project_ids')
    def _compute_projects_html(self):
        """Compute HTML field to display projects inline"""
        for record in self:
            if record.arkite_projects_list_id:
                # Access projects directly - transient models are already in memory
                projects = record.arkite_projects_list_id.project_ids
                if projects:
                    html_parts = ['<div style="max-height: 400px; overflow-y: auto;">']
                    html_parts.append('<table class="table table-striped" style="width: 100%; margin: 0; border-collapse: collapse;">')
                    html_parts.append('<thead><tr style="background: #e9ecef;"><th style="padding: 8px; text-align: left; border: 1px solid #dee2e6;">Project Name</th><th style="padding: 8px; text-align: left; border: 1px solid #dee2e6;">Project ID</th></tr></thead>')
                    html_parts.append('<tbody>')
                    for proj in projects:
                        # Escape HTML to prevent XSS
                        proj_name = (proj.arkite_project_name or "N/A").replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                        proj_id = (proj.arkite_project_id or "N/A").replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
                        html_parts.append('<tr>')
                        html_parts.append(f'<td style="padding: 8px; border: 1px solid #dee2e6;">{proj_name}</td>')
                        html_parts.append(f'<td style="padding: 8px; border: 1px solid #dee2e6;">{proj_id}</td>')
                        html_parts.append('</tr>')
                    html_parts.append('</tbody>')
                    html_parts.append('</table>')
                    html_parts.append('</div>')
                    record.arkite_projects_html = ''.join(html_parts)
                else:
                    # No projects in the list
                    record.arkite_projects_html = '<div style="text-align: center; padding: 20px; color: #856404;"><i class="fa fa-info-circle"></i> No projects loaded yet.</div>'
                continue
            # No projects or no list
            record.arkite_projects_html = '<div style="text-align: center; padding: 20px; color: #856404;"><i class="fa fa-info-circle"></i> No projects loaded yet.</div>'
    
    def _compute_arkite_project_info(self):
        """Fetch current project and step info from Arkite API"""
        for record in self:
            record.arkite_project_name = ''
            record.arkite_loaded_project_id = ''
            record.arkite_loaded_project_name = ''
            record.arkite_active_process_id = ''
            record.arkite_active_step_info = ''
            
            if not record.arkite_api_base or not record.arkite_api_key or not record.arkite_unit_id:
                continue
            
            try:
                # Get loaded project
                url = f"{record.arkite_api_base}/units/{record.arkite_unit_id}/loadedProject"
                params = {"apiKey": record.arkite_api_key}
                headers = {"Content-Type": "application/json"}
                
                response = requests.get(url, params=params, headers=headers, verify=False, timeout=5)
                if response.ok:
                    project_data = response.json()
                    if project_data and project_data.get('Id'):
                        record.arkite_loaded_project_id = str(project_data.get('Id'))
                        record.arkite_loaded_project_name = project_data.get('Name', 'Unknown')
                        record.arkite_project_name = project_data.get('Name', 'Unknown')
                        
                        # Try to get active steps
                        # First, get processes for the project
                        processes_url = f"{record.arkite_api_base}/projects/{record.arkite_loaded_project_id}/processes"
                        processes_response = requests.get(processes_url, params=params, headers=headers, verify=False, timeout=5)
                        if processes_response.ok:
                            processes = processes_response.json()
                            if processes and isinstance(processes, list) and len(processes) > 0:
                                # Get first process ID
                                process_id = processes[0].get('Id')
                                if process_id:
                                    record.arkite_active_process_id = str(process_id)
                                    
                                    # Get active steps for this process
                                    steps_url = f"{record.arkite_api_base}/units/{record.arkite_unit_id}/processes/{process_id}/activeSteps"
                                    steps_response = requests.get(steps_url, params=params, headers=headers, verify=False, timeout=5)
                                    if steps_response.ok:
                                        steps_data = steps_response.json()
                                        if steps_data:
                                            step_info_parts = []
                                            if isinstance(steps_data, list):
                                                for step in steps_data[:3]:  # Show first 3 steps
                                                    step_name = step.get('Name', 'Unknown')
                                                    step_info_parts.append(step_name)
                                            elif isinstance(steps_data, dict):
                                                step_name = steps_data.get('Name', 'Unknown')
                                                step_info_parts.append(step_name)
                                            
                                            if step_info_parts:
                                                record.arkite_active_step_info = ' | '.join(step_info_parts)
                                            else:
                                                record.arkite_active_step_info = 'No active steps'
            except Exception as e:
                _logger.debug("Error fetching Arkite project info: %s", e)
                # Silently fail - don't show errors in computed fields

    @api.constrains('name')
    def _check_name(self):
        for record in self:
            if not record.name:
                raise UserError('Unit Name is required!')

    @api.constrains('completed_steps', 'total_steps')
    def _check_completed_steps(self):
        """Ensure completed steps don't exceed total steps"""
        for record in self:
            if record.total_steps > 0 and record.completed_steps > record.total_steps:
                record.completed_steps = record.total_steps
            elif record.completed_steps < 0:
                record.completed_steps = 0

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """When product changes, reset completed steps and update total steps"""
        for record in self:
            record.completed_steps = 0
            # Force recomputation of total_steps
            record._compute_total_steps()

    def action_mark_complete(self):
        """Mark the current step as complete"""
        for record in self:
            # Always refresh total steps from product first
            record._compute_total_steps()

            if record.total_steps == 0:
                raise UserError('This product has no assembly instructions!')
            elif record.completed_steps < record.total_steps:
                record.completed_steps += 1
            else:
                raise UserError('All steps are already completed!')

    def action_reset_progress(self):
        """Reset progress to zero"""
        for record in self:
            record.completed_steps = 0

    def action_open_product(self):
        """Open the associated product form"""
        self.ensure_one()
        if self.product_id:
            return {
                'type': 'ir.actions.act_window',
                'name': self.product_id.name,
                'res_model': 'product_module.product',
                'res_id': self.product_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def write(self, vals):
        """Override write to ensure total_steps is always current"""
        result = super().write(vals)
        # If product is being changed, recompute total_steps for affected records
        if 'product_id' in vals:
            self._compute_total_steps()
        return result

    @api.model
    def create(self, vals):
        """Override create to compute total_steps immediately"""
        record = super().create(vals)
        # Compute total_steps after creation
        record._compute_total_steps()
        return record

    @api.model
    def update_progress_from_instruction_change(self, product_id):
        """Update all progress records when product processes change"""
        if product_id:
            progress_records = self.search([('product_id', '=', product_id)])
            progress_records._compute_total_steps()
    
    def action_test_arkite_connection(self):
        """Test the connection to Arkite API and fetch available projects"""
        self.ensure_one()
        
        if not self.arkite_api_base or not self.arkite_api_key:
            raise UserError(_('API Base URL and API Key are required to test connection.'))
        
        if not self.arkite_unit_id:
            raise UserError(_('Arkite Unit ID is required to test connection.'))
        
        try:
            # Test connection
            url = f"{self.arkite_api_base}/units/{self.arkite_unit_id}"
            params = {"apiKey": self.arkite_api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            
            if not response.ok:
                if response.status_code == 401:
                    raise UserError(_('Authentication failed. Please check your API key.'))
                elif response.status_code == 404:
                    raise UserError(_('Unit ID %s not found on the Arkite server.') % self.arkite_unit_id)
                else:
                    raise UserError(_('Connection failed: HTTP %s - %s') % (response.status_code, response.text[:100]))
            
            # Connection successful - now fetch projects
            projects_url = f"{self.arkite_api_base}/projects"
            projects_response = requests.get(projects_url, params=params, headers=headers, verify=False, timeout=10)
            
            projects_list = []
            if projects_response.ok:
                projects_data = projects_response.json()
                if isinstance(projects_data, list):
                    projects_list = projects_data
                elif isinstance(projects_data, dict) and 'projects' in projects_data:
                    projects_list = projects_data['projects']
            
            # Store projects in a transient model for display
            # Create or update the projects list record
            projects_record = self.env['product_module.arkite.unit.projects'].search([
                ('progress_id', '=', self.id)
            ], limit=1)
            
            if not projects_record:
                projects_record = self.env['product_module.arkite.unit.projects'].create({
                    'progress_id': self.id,
                })
            
            # Clear existing projects
            projects_record.project_ids.unlink()
            
            # Add new projects
            for proj in projects_list:
                project_id = proj.get("Id") or proj.get("ProjectId")
                project_name = proj.get("Name") or proj.get("ProjectName", "Unnamed")
                if project_id:
                    self.env['product_module.arkite.unit.project'].create({
                        'parent_id': projects_record.id,
                        'arkite_project_id': str(project_id),
                        'arkite_project_name': project_name,
                    })
            
            # Refresh project info and projects list
            self._compute_projects_list()
            self._compute_projects_html()
            self._compute_arkite_project_info()
            
            # Return False - JavaScript will handle the update without any reload
            return False
        except UserError:
            raise
        except requests.exceptions.RequestException as e:
            raise UserError(_('Connection error: %s') % str(e))
        except Exception as e:
            _logger.error("Error testing connection: %s", e)
            raise UserError(_('Error testing connection: %s') % str(e))
    
    def action_create_arkite_unit(self):
        """Create an Arkite Unit record from this Progress unit for use in Projects"""
        self.ensure_one()
        
        if not self.arkite_unit_id or not self.arkite_api_base or not self.arkite_api_key:
            raise UserError(_('This unit is missing Arkite configuration. Please configure Arkite Unit ID, API Base URL, and API Key first.'))
        
        # Check if Arkite Unit already exists with this unit_id
        existing = self.env['product_module.arkite.unit'].search([
            ('unit_id', '=', self.arkite_unit_id)
        ], limit=1)
        
        if existing:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Unit Already Exists'),
                    'message': _('An Arkite Unit with ID "%s" already exists: "%s". You can use it in Projects.') % (self.arkite_unit_id, existing.name),
                    'type': 'info',
                    'sticky': False,
                }
            }
        
        # Create new Arkite Unit
        arkite_unit = self.env['product_module.arkite.unit'].create({
            'name': self.name,
            'unit_id': self.arkite_unit_id,
            'api_base': self.arkite_api_base,
            'api_key': self.arkite_api_key,
            'template_name': self.arkite_template_name or '',
            'active': True,
            'description': f'Created from Unit Tracking: {self.name}',
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Arkite Unit Created'),
                'message': _('Arkite Unit "%s" has been created. You can now select it in Projects.') % arkite_unit.name,
                'type': 'success',
                'sticky': False,
            }
        }
    
    def action_refresh_arkite_projects(self):
        """Refresh the list of projects from Arkite"""
        self.ensure_one()
        
        if not self.arkite_api_base or not self.arkite_api_key or not self.arkite_unit_id:
            raise UserError(_('API Base URL, API Key, and Unit ID are required to refresh projects.'))
        
        try:
            # Fetch projects
            projects_url = f"{self.arkite_api_base}/projects"
            params = {"apiKey": self.arkite_api_key}
            headers = {"Content-Type": "application/json"}
            
            projects_response = requests.get(projects_url, params=params, headers=headers, verify=False, timeout=10)
            
            projects_list = []
            if projects_response.ok:
                projects_data = projects_response.json()
                if isinstance(projects_data, list):
                    projects_list = projects_data
                elif isinstance(projects_data, dict) and 'projects' in projects_data:
                    projects_list = projects_data['projects']
            
            # Store projects in a transient model for display
            projects_record = self.env['product_module.arkite.unit.projects'].search([
                ('progress_id', '=', self.id)
            ], limit=1)
            
            if not projects_record:
                projects_record = self.env['product_module.arkite.unit.projects'].create({
                    'progress_id': self.id,
                })
            
            # Clear existing projects
            projects_record.project_ids.unlink()
            
            # Add new projects
            for proj in projects_list:
                project_id = proj.get("Id") or proj.get("ProjectId")
                project_name = proj.get("Name") or proj.get("ProjectName", "Unnamed")
                if project_id:
                    self.env['product_module.arkite.unit.project'].create({
                        'parent_id': projects_record.id,
                        'arkite_project_id': str(project_id),
                        'arkite_project_name': project_name,
                    })
            
            # Refresh project info and projects list
            self._compute_projects_list()
            self._compute_projects_html()
            self._compute_arkite_project_info()
            
            # Return False - JavaScript will handle the update without any reload
            return False
        except UserError:
            raise
        except requests.exceptions.RequestException as e:
            raise UserError(_('Connection error: %s') % str(e))
        except Exception as e:
            _logger.error("Error refreshing projects: %s", e)
            raise UserError(_('Error refreshing projects: %s') % str(e))
    
    def action_select_arkite_project(self, project_id):
        """Select an Arkite project to track"""
        self.ensure_one()
        if project_id:
            self.arkite_project_id = str(project_id)
            # Refresh project info
            self._compute_arkite_project_info()
            self._compute_projects_html()
            # Return reload to refresh the form and show updated project info
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
    
    def action_refresh_projects_html(self):
        """Force recomputation of the projects HTML field by re-fetching from API"""
        self.ensure_one()
        
        # Re-fetch projects from API to ensure we have the latest data
        if not self.arkite_api_base or not self.arkite_api_key:
            return {
                'html': '<div style="text-align: center; padding: 20px; color: #856404;"><i class="fa fa-info-circle"></i> API credentials not configured.</div>',
                'count': 0
            }
        
        try:
            import requests
            # Fetch projects directly from API
            projects_url = f"{self.arkite_api_base}/projects"
            params = {"apiKey": self.arkite_api_key}
            headers = {"Content-Type": "application/json"}
            
            projects_response = requests.get(projects_url, params=params, headers=headers, verify=False, timeout=10)
            
            projects_list = []
            if projects_response.ok:
                projects_data = projects_response.json()
                if isinstance(projects_data, list):
                    projects_list = projects_data
                elif isinstance(projects_data, dict) and 'projects' in projects_data:
                    projects_list = projects_data['projects']
            
            # Find or create the transient model record
            projects_record = self.env['product_module.arkite.unit.projects'].search([
                ('progress_id', '=', self.id)
            ], limit=1)
            
            if not projects_record:
                projects_record = self.env['product_module.arkite.unit.projects'].create({
                    'progress_id': self.id,
                })
            
            # Clear existing projects and add fresh ones
            projects_record.project_ids.unlink()
            
            for proj in projects_list:
                project_id = proj.get("Id") or proj.get("ProjectId")
                project_name = proj.get("Name") or proj.get("ProjectName", "Unnamed")
                if project_id:
                    self.env['product_module.arkite.unit.project'].create({
                        'parent_id': projects_record.id,
                        'arkite_project_id': str(project_id),
                        'arkite_project_name': project_name,
                    })
            
            # Update the reference
            self.arkite_projects_list_id = projects_record.id
            
            # Now recompute the HTML with fresh data
            self._compute_projects_html()
            
            return {
                'html': self.arkite_projects_html or '',
                'count': len(projects_list)
            }
        except Exception as e:
            _logger.error("Error refreshing projects HTML: %s", e)
            return {
                'html': f'<div style="text-align: center; padding: 20px; color: #dc3545;"><i class="fa fa-exclamation-circle"></i> Error: {str(e)}</div>',
                'count': 0
            }


class ArkiteUnitProjects(models.TransientModel):
    """Temporary model to store list of Arkite projects for a unit"""
    _name = 'product_module.arkite.unit.projects'
    _description = 'Arkite Unit Projects List'
    
    progress_id = fields.Many2one('product_module.progress', string='Unit', required=True, ondelete='cascade')
    project_ids = fields.One2many('product_module.arkite.unit.project', 'parent_id', string='Available Projects')


class ArkiteUnitProject(models.TransientModel):
    """Individual Arkite project in the list"""
    _name = 'product_module.arkite.unit.project'
    _description = 'Arkite Project in Unit List'
    _rec_name = 'arkite_project_name'
    
    parent_id = fields.Many2one('product_module.arkite.unit.projects', string='Parent', required=True, ondelete='cascade')
    arkite_project_id = fields.Char(string='Project ID', required=True)
    arkite_project_name = fields.Char(string='Project Name', required=True)
    
    def action_select_project(self):
        """Select this project for tracking"""
        self.ensure_one()
        if self.parent_id and self.parent_id.progress_id:
            self.parent_id.progress_id.arkite_project_id = self.arkite_project_id
            self.parent_id.progress_id._compute_arkite_project_info()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Project Selected'),
                    'message': _('Project "%s" is now being tracked.') % self.arkite_project_name,
                    'type': 'success',
                }
            }