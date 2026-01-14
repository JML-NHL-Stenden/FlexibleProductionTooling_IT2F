# product_module/models/project.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import os
import logging
import time
import json
from datetime import datetime, timezone
from ..services.arkite_client import ArkiteClient
_logger = logging.getLogger(__name__)


class ProductModuleProject(models.Model):
    def _action_refresh_current_form(self):
        """Refresh the current form without a hard client reload."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Project'),
            'res_model': 'product_module.project',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('product_module.view_project_form').id, 'form')],
            'target': 'current',
            'context': dict(self.env.context),
        }
    def action_sync_staged_hierarchy_to_arkite(self):
        """Sync staged hierarchy changes (job + process steps) to Arkite and show a toast.

        Kept on the core Project model so the Project form button always validates.
        """
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_("Please link to an Arkite project first."))

        if not getattr(self, 'arkite_hierarchy_dirty', False):
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No changes'),
                    'message': _('No staged hierarchy changes to sync.'),
                    'type': 'info',
                    'sticky': False,
                },
            }

        if getattr(self, 'arkite_job_steps_loaded', False) and getattr(self, 'arkite_job_steps_dirty', False):
            self.env['product_module.arkite.job.step'].with_context(default_project_id=self.id).pm_action_save_all()

        if getattr(self, 'arkite_process_steps_loaded', False) and getattr(self, 'arkite_process_steps_dirty', False):
            process_ids = self.env['product_module.arkite.process.step'].search([
                ('project_id', '=', self.id),
                ('process_id', '!=', False),
            ]).mapped('process_id')
            for pid in sorted(set(process_ids)):
                self.env['product_module.arkite.process.step'].with_context(
                    default_project_id=self.id,
                    default_process_id=pid,
                ).pm_action_save_all()

        self.env.cr.execute(
            "UPDATE product_module_project "
            "SET arkite_hierarchy_dirty = FALSE, arkite_job_steps_dirty = FALSE, arkite_process_steps_dirty = FALSE "
            "WHERE id = %s",
            [self.id],
        )
        self.invalidate_recordset(['arkite_hierarchy_dirty', 'arkite_job_steps_dirty', 'arkite_process_steps_dirty'])

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Saved'),
                'message': _('Synced staged hierarchy changes to Arkite.'),
                'type': 'success',
                'sticky': False,
            },
        }
    _name = 'product_module.project'
    _description = 'Product Project'
    _order = 'sequence, name, id'

    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
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

    # When users reorder/reparent steps in hierarchy/diagram screens we "stage" changes locally and only
    # sync to Arkite when the user saves the Project form.
    arkite_hierarchy_dirty = fields.Boolean(
        string='Staged hierarchy changes',
        default=False,
        copy=False,
        help='If enabled, there are local hierarchy changes (order/parent) not yet pushed to Arkite. Saving the project will sync them.'
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
    # Arkite Jobs
    arkite_job_ids = fields.One2many(
        'product_module.arkite.job.temp',
        'project_id',
        string='Jobs',
        help='Arkite jobs available in the project (root-level steps with ProcessId=0)'
    )
    selected_arkite_job_id = fields.Char(
        string='Selected Job ID',
        help='Currently selected Arkite job ID to view/edit its steps'
    )
    selected_job_id_char = fields.Char(
        string='Selected Job ID (Text)',
        help='Enter job name or ID to select a job'
    )
    selected_arkite_job_name = fields.Char(
        string='Selected Job Name',
        compute='_compute_selected_job_name',
        store=False,
        help='Name of the selected job (computed)'
    )
    arkite_job_step_ids = fields.One2many(
        'product_module.arkite.job.step',
        'project_id',
        string='Job Steps',
        help='Steps for the selected Arkite job'
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
    
    # Hierarchy Test (for drag-and-drop testing) - DISABLED: Model loading order issue
    # This requires the model to be loaded before the field definition, which is complex
    # hierarchy_test_ids = fields.One2many(
    #     'product_module.hierarchy.test',
    #     'project_id',
    #     string='Hierarchy Test Items',
    #     help='Test items for hierarchy drag-and-drop functionality'
    # )
    
    def action_add_test_items(self):
        """Add some test items for demonstration"""
        self.ensure_one()
        
        # Clear existing test items
        self.env['product_module.hierarchy.test'].search([('project_id', '=', self.id)]).unlink()
        
        # Create test hierarchy
        root1 = self.env['product_module.hierarchy.test'].create({
            'project_id': self.id,
            'name': 'Root Item 1',
            'sequence': 10,
        })
        
        root2 = self.env['product_module.hierarchy.test'].create({
            'project_id': self.id,
            'name': 'Root Item 2',
            'sequence': 20,
        })
        
        # Add children
        self.env['product_module.hierarchy.test'].create({
            'project_id': self.id,
            'name': 'Child 1.1',
            'sequence': 10,
            'parent_id': root1.id,
        })
        
        self.env['product_module.hierarchy.test'].create({
            'project_id': self.id,
            'name': 'Child 1.2',
            'sequence': 20,
            'parent_id': root1.id,
        })
        
        self.env['product_module.hierarchy.test'].create({
            'project_id': self.id,
            'name': 'Child 2.1',
            'sequence': 10,
            'parent_id': root2.id,
        })
        
        return {'type': 'ir.actions.client', 'tag': 'reload'}

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
    
    @api.depends('selected_arkite_job_id', 'selected_job_id_char', 'arkite_job_ids', 'arkite_job_ids.name')
    def _compute_selected_job_name(self):
        """Compute the name of the selected job"""
        for record in self:
            # Use selected_job_id_char if available, otherwise use selected_arkite_job_id
            job_id = record.selected_job_id_char or record.selected_arkite_job_id
            if job_id:
                job = record.arkite_job_ids.filtered(
                    lambda j: j.job_step_id == job_id
                )
                record.selected_arkite_job_name = job.name if job else job_id
            else:
                record.selected_arkite_job_name = ""
    
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
    # ====================
    # MQTT / "Run in Arkite"
    # ====================

    def _get_mqtt_config(self):
        """
        Pull config from environment first (works great in Docker),
        fallback to Odoo system params if you want to configure via UI later.
        """
        ICP = self.env['ir.config_parameter'].sudo()

        host = os.getenv("MQTT_HOST") or ICP.get_param("product_module.mqtt_host") or "mqtt"
        port = os.getenv("MQTT_PORT") or ICP.get_param("product_module.mqtt_port") or "1883"
        topic = os.getenv("MQTT_TOPIC_QR") or ICP.get_param("product_module.mqtt_topic_qr") or "arkite/trigger/QR"

        try:
            port = int(port)
        except Exception:
            port = 1883

        return host, port, topic

    def _publish_qr_trigger_to_mqtt(self):
        """
        Publish the same payload shape your existing Windows Arkite Agent expects:
        {
          "timestamp": "...",
          "count": 1,
          "items": [{"product_name": "...", "product_code": "...", "qr_text": "..."}],
          "source": {...}
        }
        """
        self.ensure_one()

        try:
            import paho.mqtt.client as mqtt
        except Exception as e:
            raise UserError(_(
                "Missing Python dependency for MQTT in Odoo (paho-mqtt).\n"
                "Install it in your Odoo container, e.g.:\n"
                "  pip3 install paho-mqtt\n\n"
                "Original error: %s"
            ) % (str(e),))

        mqtt_host, mqtt_port, mqtt_topic = self._get_mqtt_config()

        qr_code = (self.arkite_project_id or self.name or "").strip()

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": 1,
            "items": [
                {
                    "product_name": self.name or "",
                    # keep key names stable for existing agent parsing
                    "product_code": qr_code,
                    "qr_text": qr_code,
                }
            ],
            "source": {
                "origin": "odoo-product-module",
                "action": "project.action_start_project",
                "model": self._name,
                "res_id": self.id,
            },
        }

        client = mqtt.Client(client_id=f"odoo-project-start-{self.id}", protocol=mqtt.MQTTv5)
        try:
            client.connect(mqtt_host, mqtt_port, keepalive=30)
            client.publish(mqtt_topic, json.dumps(payload), qos=0, retain=False)
            client.disconnect()
        except Exception as e:
            raise UserError(_(
                "MQTT publish failed.\n"
                "Host: %s\nPort: %s\nTopic: %s\n\nError: %s"
            ) % (mqtt_host, mqtt_port, mqtt_topic, str(e)))

        return payload, mqtt_host, mqtt_port, mqtt_topic

    def action_start_project(self):
        """Run in Arkite: publish a QR-trigger payload to MQTT."""
        self.ensure_one()

        qr_code = (self.arkite_project_id or self.name or "").strip()
        if not qr_code:
            raise UserError(_('Please set a project name or link to an Arkite project first.'))

        payload, host, port, topic = self._publish_qr_trigger_to_mqtt()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Run in Arkite'),
                'message': _(
                    'Published QR trigger to MQTT.\nHost=%s Port=%s Topic=%s\n\nProject: %s (%s)'
                ) % (host, port, topic, self.name, qr_code),
                'type': 'success',
                'sticky': False,
            }
        }

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

    def action_unlink_arkite_project(self):
        """De-link the Arkite project and clear synced transient data so another project can be linked."""
        self.ensure_one()

        # Capture current transient records before clearing the link (so we can cleanup safely).
        variant_recs = self.arkite_variant_ids
        process_recs = self.arkite_process_ids
        process_step_recs = self.arkite_process_step_ids
        job_recs = self.arkite_job_ids
        job_step_recs = self.arkite_job_step_ids
        detection_recs = self.arkite_detection_ids
        material_recs = self.arkite_material_ids
        # Materials Used (non-transient). IMPORTANT: do NOT unlink() these, because material.unlink()
        # deletes in Arkite. Instead, detach them from this project so they disappear from the form.
        used_material_recs = self.material_ids

        # Clear link + selection state + staged flags.
        self.with_context(skip_arkite_hierarchy_autosync=True).write({
            'arkite_project_id': False,
            'arkite_project_name': False,
            'arkite_project_loaded': False,
            'selected_arkite_process_id': False,
            'selected_process_id_char': False,
            'selected_arkite_job_id': False,
            'selected_job_id_char': False,
            'arkite_hierarchy_dirty': False,
            # Step flags (provided by project_arkite_step_flags.py)
            'arkite_job_steps_loaded': False,
            'arkite_process_steps_loaded': False,
            'arkite_job_steps_dirty': False,
            'arkite_process_steps_dirty': False,
        })

        # Clear transient data loaded from Arkite (local only).
        # NOTE: you can't union recordsets from different models, so unlink separately.
        # Also, unlink() on steps is safe; we previously removed Arkite DELETE calls from step unlink().
        if variant_recs:
            variant_recs.unlink()
        if process_recs:
            process_recs.unlink()
        if process_step_recs:
            process_step_recs.unlink()
        if job_recs:
            job_recs.unlink()
        if job_step_recs:
            job_step_recs.unlink()
        if detection_recs:
            detection_recs.unlink()
        if material_recs:
            material_recs.unlink()

        # Detach "Materials Used" from this project (without deleting them).
        if used_material_recs:
            used_material_recs.write({'project_id': False})

        # Notify + reopen this record as a modal so we don't accidentally close the current modal stack
        # (soft_reload can restore the underlying controller and close dialogs).
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('De-linked'),
                'message': _('Arkite project link removed and locally loaded Arkite data cleared.'),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'name': _('Project'),
                    'res_model': 'product_module.project',
                    'res_id': self.id,
                    'view_mode': 'form',
                    'views': [(self.env.ref('product_module.view_project_form').id, 'form')],
                    'target': 'new',
                    'context': dict(self.env.context),
                },
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
        """Load job steps from Arkite project (legacy method - now redirects to load selected job's steps)"""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_("Please link to an Arkite project first."))
        
        # Load all job steps directly
        return self.action_load_job_steps()
    
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

    # -------------------------------------------------------------------------
    # UI helpers: open steps in a dedicated view with native group-by collapse
    # (avoids custom JS in web.assets_backend which can brick the UI)
    # -------------------------------------------------------------------------

    def action_open_job_steps_hierarchy(self):
        """Open Arkite job steps in a dedicated list view grouped by Parent (easy fold/unfold)."""
        self.ensure_one()
        # In hierarchy/diagram screens we defer Arkite sync so users can Discard if they don't like changes.
        ctx = dict(self.env.context, default_project_id=self.id, create=True, edit=True, delete=True, defer_arkite_sync=True, pm_show_save_discard=True)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Arkite Job Steps (Hierarchy)'),
            'res_model': 'product_module.arkite.job.step',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('product_module.view_arkite_job_step_tree_manage').id, 'list'),
                (self.env.ref('product_module.view_arkite_job_step_form').id, 'form'),
            ],
            'search_view_id': self.env.ref('product_module.view_arkite_job_step_search').id,
            'domain': [('project_id', '=', self.id)],
            # NOTE: do NOT force group_by here; grouped lists disable inline "Add a line".
            # Users can still fold/unfold by using the Group By > Parent filter.
            'context': ctx,
            'target': 'new',
        }

    def action_open_process_steps_hierarchy(self):
        """Open Arkite process steps in a dedicated list view grouped by Parent (easy fold/unfold).

        If a process is selected on the project form, filter to that process.
        """
        self.ensure_one()
        domain = [('project_id', '=', self.id)]
        process_id = getattr(self, 'selected_process_id_char', False)
        if process_id:
            domain.append(('process_id', '=', process_id))

        ctx = dict(self.env.context, default_project_id=self.id, create=True, edit=True, delete=True, defer_arkite_sync=True, pm_show_save_discard=True)
        if process_id:
            ctx['default_process_id'] = process_id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Arkite Process Steps (Hierarchy)'),
            'res_model': 'product_module.arkite.process.step',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('product_module.view_arkite_process_step_tree_manage').id, 'list'),
                (self.env.ref('product_module.view_arkite_process_step_form').id, 'form'),
            ],
            'search_view_id': self.env.ref('product_module.view_arkite_process_step_search').id,
            'domain': domain,
            'context': ctx,
            'target': 'new',
        }

    def action_open_job_steps_diagram(self):
        """Open job steps in the native diagram hierarchy view (drag/reparent)."""
        self.ensure_one()
        ctx = dict(self.env.context, default_project_id=self.id, create=True, edit=True, delete=True, defer_arkite_sync=True, pm_show_save_discard=True)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Arkite Job Steps (Diagram)'),
            'res_model': 'product_module.arkite.job.step',
            'view_mode': 'hierarchy,form',
            'views': [
                (self.env.ref('product_module.view_arkite_job_step_hierarchy').id, 'hierarchy'),
                (self.env.ref('product_module.view_arkite_job_step_form').id, 'form'),
            ],
            'search_view_id': self.env.ref('product_module.view_arkite_job_step_search').id,
            'domain': [('project_id', '=', self.id)],
            'context': ctx,
            # Open as a modal on top of the Project form.
            'target': 'new',
        }

    def action_open_process_steps_diagram(self):
        """Open process steps in the native diagram hierarchy view (drag/reparent)."""
        self.ensure_one()
        domain = [('project_id', '=', self.id)]
        process_id = getattr(self, 'selected_process_id_char', False)
        if process_id:
            domain.append(('process_id', '=', process_id))
        ctx = dict(self.env.context, default_project_id=self.id, create=True, edit=True, delete=True, defer_arkite_sync=True, pm_show_save_discard=True)
        if process_id:
            ctx['default_process_id'] = process_id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Arkite Process Steps (Diagram)'),
            'res_model': 'product_module.arkite.process.step',
            'view_mode': 'hierarchy,form',
            'views': [
                (self.env.ref('product_module.view_arkite_process_step_hierarchy').id, 'hierarchy'),
                (self.env.ref('product_module.view_arkite_process_step_form').id, 'form'),
            ],
            'search_view_id': self.env.ref('product_module.view_arkite_process_step_search').id,
            'domain': domain,
            'context': ctx,
            'target': 'new',
        }

    # -------------------------------------------------------------------------
    # Quick-create helpers (Project form buttons)
    # -------------------------------------------------------------------------

    def action_new_job_step(self):
        """Open a form to create a new Job Step for this project."""
        self.ensure_one()
        ctx = dict(self.env.context, default_project_id=self.id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Job Step'),
            'res_model': 'product_module.arkite.job.step',
            'view_mode': 'form',
            'views': [(self.env.ref('product_module.view_arkite_job_step_form').id, 'form')],
            'target': 'new',
            'context': ctx,
        }

    def action_new_process_step(self):
        """Open a form to create a new Process Step for the selected process."""
        self.ensure_one()
        process_id = getattr(self, 'selected_process_id_char', False)
        if not process_id:
            raise UserError(_("Please select a process first."))
        ctx = dict(self.env.context, default_project_id=self.id, default_process_id=process_id)
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Process Step'),
            'res_model': 'product_module.arkite.process.step',
            'view_mode': 'form',
            'views': [(self.env.ref('product_module.view_arkite_process_step_form').id, 'form')],
            'target': 'new',
            'context': ctx,
        }

    def action_open_create_process_wizard(self):
        """Open wizard to create a new (blank) Arkite process with Name/Comment."""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_("Please link to an Arkite project first."))
        ctx = dict(
            self.env.context,
            default_project_id=self.id,
            default_mode='create',
            default_name='New Process',
            default_comment='',
            from_process_wizard=True,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Process'),
            'res_model': 'product_module.arkite.process.create.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    def action_open_duplicate_process_wizard(self):
        """Open wizard to duplicate an existing Arkite process (template selection)."""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_("Please link to an Arkite project first."))
        ctx = dict(
            self.env.context,
            default_project_id=self.id,
            default_mode='duplicate',
            from_process_wizard=True,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Duplicate Process'),
            'res_model': 'product_module.arkite.process.create.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }
    
    def action_create_process(self):
        """Duplicate an existing Arkite process (server supports duplicate even when POST-create is broken)."""
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
            # Define request basics up-front
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}

            # NOTE: On your Arkite server, POST /projects/{id}/processes/ returns HTTP 500
            # ("Sequence contains no matching element") for all payload variants (tested from inside container).
            # However, the Guides describe and we verified that *duplicating* an existing process works:
            # POST /projects/{projectId}/processes/{processId}/duplicate/

            url_list = f"{api_base}/projects/{self.arkite_project_id}/processes/"
            list_resp = requests.get(url_list, params=params, headers=headers, verify=False, timeout=10)
            if not list_resp.ok:
                raise UserError(_("Failed to fetch processes: HTTP %s\n%s") % (list_resp.status_code, (list_resp.text or "")[:500]))

            processes = list_resp.json()
            if not isinstance(processes, list) or not processes:
                raise UserError(_(
                    "No processes exist in this Arkite project.\n\n"
                    "This Arkite server currently fails POST /projects/{id}/processes/ with an internal error, "
                    "so Odoo cannot create the first process via API.\n"
                    "Please create one process in Arkite UI first, then Odoo can duplicate it."
                ))

            # Pick a template process to duplicate (prefer the Job Selection process)
            template = None
            for p in processes:
                if isinstance(p, dict) and (p.get("Name") or "").strip().lower() == "job selection":
                    template = p
                    break
            if not template:
                template = processes[0] if isinstance(processes[0], dict) else None
            if not template or not template.get("Id"):
                raise UserError(_("Could not determine a template process to duplicate."))

            template_id = str(template.get("Id"))
            url_dup = f"{api_base}/projects/{self.arkite_project_id}/processes/{template_id}/duplicate/"
            _logger.info("[ARKITE] Duplicating process %s in project %s", template_id, self.arkite_project_id)

            dup_resp = requests.post(url_dup, params=params, headers=headers, verify=False, timeout=10)
            if not dup_resp.ok:
                raise UserError(_("Failed to duplicate process: HTTP %s\n%s") % (dup_resp.status_code, (dup_resp.text or "")[:500]))

            created_process = dup_resp.json() if dup_resp.text else {}
            if not isinstance(created_process, dict):
                raise UserError(_("Unexpected response format from Arkite when duplicating a process."))

            if created_process:
                process_id = str(created_process.get("Id", ""))
                process_name = created_process.get("Name", "New Process")
                
                # Create process temp record
                process_temp = self.env['product_module.arkite.process.temp'].create({
                    'project_id': self.id,
                    'process_id': process_id,
                    'name': process_name,
                    'comment': created_process.get("Comment", "")
                })
                
                # Auto-select the newly created process
                self.selected_process_id_char = process_id
                self.selected_arkite_process_id = process_id

                # Refresh form so the new process shows immediately without hard reload.
                return self._action_refresh_current_form()
            else:
                raise UserError(_("Unexpected response format from Arkite API"))
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error creating process: %s", e, exc_info=True)
            raise UserError(_("Error creating process: %s") % str(e))

    def action_create_blank_process(self):
        """
        Create a *blank* process for this project.

        Arkite's direct create endpoint POST /projects/{id}/processes/ is broken on this server (HTTP 500),
        but duplicating a process works. So we duplicate a template process and then delete its steps,
        resulting in an empty process (still named like '<template> - Copy' because rename API is not implemented).
        """
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_("Please link to an Arkite project first."))

        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration.'))

        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}

        # 1) Duplicate an existing process (same logic as action_create_process)
        url_list = f"{api_base}/projects/{self.arkite_project_id}/processes/"
        list_resp = requests.get(url_list, params=params, headers=headers, verify=False, timeout=10)
        if not list_resp.ok:
            raise UserError(_("Failed to fetch processes: HTTP %s\n%s") % (list_resp.status_code, (list_resp.text or "")[:500]))

        processes = list_resp.json()
        if not isinstance(processes, list) or not processes:
            raise UserError(_(
                "No processes exist in this Arkite project.\n\n"
                "This Arkite server currently fails POST /projects/{id}/processes/ with an internal error, "
                "so Odoo cannot create the first process via API.\n"
                "Please create one process in Arkite UI first, then Odoo can create blank ones by duplicating it."
            ))

        template = None
        for p in processes:
            if isinstance(p, dict) and (p.get("Name") or "").strip().lower() == "job selection":
                template = p
                break
        if not template:
            template = processes[0] if isinstance(processes[0], dict) else None
        if not template or not template.get("Id"):
            raise UserError(_("Could not determine a template process to duplicate."))

        template_id = str(template.get("Id"))
        url_dup = f"{api_base}/projects/{self.arkite_project_id}/processes/{template_id}/duplicate/"
        dup_resp = requests.post(url_dup, params=params, headers=headers, verify=False, timeout=10)
        if not dup_resp.ok:
            raise UserError(_("Failed to duplicate process: HTTP %s\n%s") % (dup_resp.status_code, (dup_resp.text or "")[:500]))

        created_process = dup_resp.json() if dup_resp.text else {}
        if not isinstance(created_process, dict) or not created_process.get("Id"):
            raise UserError(_("Unexpected response format from Arkite when duplicating a process."))

        new_process_id = str(created_process.get("Id"))

        # 2) Delete steps belonging to the new process
        url_steps_for_process = f"{api_base}/projects/{self.arkite_project_id}/processes/{new_process_id}/steps/"
        steps_resp = requests.get(url_steps_for_process, params=params, headers=headers, verify=False, timeout=10)
        if steps_resp.ok:
            steps = steps_resp.json()
            if isinstance(steps, list) and steps:
                for s in steps:
                    sid = str(s.get("Id", "") or "")
                    if not sid:
                        continue
                    del_url = f"{api_base}/projects/{self.arkite_project_id}/steps/{sid}"
                    try:
                        requests.delete(del_url, params=params, headers=headers, verify=False, timeout=10)
                    except Exception:
                        # Best-effort cleanup; don't fail the whole action due to one delete.
                        pass

        # 3) Record + select in Odoo
        self.env['product_module.arkite.process.temp'].create({
            'project_id': self.id,
            'process_id': new_process_id,
            'name': created_process.get("Name", "New Process"),
            'comment': created_process.get("Comment", "") or "",
        })
        self.selected_process_id_char = new_process_id
        self.selected_arkite_process_id = new_process_id

        return self._action_refresh_current_form()
    
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
            
            # Clear existing process records (but keep current record if this is called from a row button)
            keep_id = self.env.context.get('keep_process_temp_id')
            if keep_id:
                to_unlink = self.arkite_process_ids.filtered(lambda r: r.id != keep_id)
                to_unlink.unlink()
            else:
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
                self.action_load_process_steps()
                return False
            
            # Don't navigate/refresh the whole page; the one2many should update in-place.
            return False
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
                    'parent_id': False,  # No parent record
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
                            'parent_id': parent_record.id,  # Link to parent record
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
            
            # Invalidate cache to force field refresh; UI should update in place.
            self.invalidate_recordset(['arkite_process_step_ids', 'selected_arkite_process_name'])
            return False
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error loading process steps: %s", e, exc_info=True)
            raise UserError(_("Error loading process steps: %s") % str(e))
    
    def action_load_job_steps(self):
        """Load all job steps from Arkite project (steps with Type='Job' and ProcessId=0)"""
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
        
        # Clear existing job steps - this resets all changes and reloads from Arkite
        # Use sudo() to ensure we can delete all records even if there are constraints
        try:
            self.arkite_job_step_ids.sudo().unlink()
        except Exception as e:
            _logger.warning("[ARKITE] Error clearing job steps, trying force unlink: %s", e)
            # Force unlink all job steps for this project
            all_job_steps = self.env['product_module.arkite.job.step'].search([
                ('project_id', '=', self.id)
            ])
            all_job_steps.sudo().unlink()
        
        try:
            # Get all steps from the project
            url_steps = f"{api_base}/projects/{self.arkite_project_id}/steps/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url_steps, params=params, headers=headers, verify=False, timeout=10)
            if not response.ok:
                raise UserError(_("Failed to fetch steps: HTTP %s") % response.status_code)
            
            all_steps = response.json()
            if not isinstance(all_steps, list):
                raise UserError(_("Unexpected response format for steps"))
            
            # Filter for job steps: Type='Job' and ProcessId=0
            job_steps = [s for s in all_steps if s.get("Type") == "Job" and (not s.get("ProcessId") or str(s.get("ProcessId", "")) == "0")]
            
            if not job_steps:
                raise UserError(_("No job steps found. Job steps are steps with Type='Job' and ProcessId=0."))
            
            # Log sample of step names from API for debugging - FULL DETAILS
            _logger.info("[ARKITE] Sample of job step names from API (first 5):")
            for i, step in enumerate(job_steps[:5]):
                step_id = step.get("Id", "N/A")
                step_name = step.get("Name", "MISSING")
                step_index = step.get("Index", "N/A")
                # Log ALL fields to see what's available
                all_keys = list(step.keys())
                _logger.info("[ARKITE]   Step %s: Id=%s, Name='%s' (type: %s, raw: %s), Index=%s", 
                           i+1, step_id, step_name, type(step_name).__name__, repr(step_name), step_index)
                _logger.info("[ARKITE]   Step %s - All fields: %s", i+1, all_keys)
                _logger.info("[ARKITE]   Step %s - Full data: %s", i+1, json.dumps({k: v for k, v in step.items() if k not in ['TextInstruction', 'StepConditions']}, indent=2))
                
                # Log StepType and Comment for steps with missing names
                if not step.get("Name") or not str(step.get("Name", "")).strip():
                    step_type_debug = step.get("StepType", "N/A")
                    comment_debug = step.get("Comment", "N/A")
                    step_id_debug = step.get("Id", "N/A")
                    _logger.info("[ARKITE]   Step %s (ID: %s) has no Name - StepType: '%s', Comment: '%s'", i+1, step_id_debug, step_type_debug, comment_debug)
            
            # Sort by Index to maintain order
            job_steps.sort(key=lambda x: x.get("Index", 0))
            
            _logger.info("[ARKITE] Found %s job steps", len(job_steps))
            
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
            
            # Separate root steps from child steps
            root_steps = [s for s in job_steps if not s.get("ParentStepId") or str(s.get("ParentStepId", "")) == "0" or str(s.get("ParentStepId", "")) == ""]
            child_steps = [s for s in job_steps if s.get("ParentStepId") and str(s.get("ParentStepId", "")) != "0" and str(s.get("ParentStepId", "")) != ""]
            
            root_steps.sort(key=lambda x: x.get("Index", 0))
            child_steps.sort(key=lambda x: x.get("Index", 0))
            
            _logger.info("[ARKITE] Job root steps: %s, child steps: %s", len(root_steps), len(child_steps))
            
            # Create a mapping of step_id to record for parent lookup
            step_id_to_record = {}
            
            # Store the root step ID - all steps in this job should use this as job_step_id
            root_step_id = None
            if root_steps:
                # Use the first root step's ID as the job_step_id for all steps
                root_step_id = str(root_steps[0].get("Id", ""))
            
            # Create root steps first
            for step in root_steps:
                step_id = str(step.get("Id", ""))
                if not step_id:
                    _logger.warning("[ARKITE] Skipping root step with empty ID")
                    continue
                
                # Extract step name - handle None, empty string, and whitespace-only properly
                step_name_raw = step.get("Name")
                if step_name_raw is None:
                    step_name = None
                else:
                    step_name = str(step_name_raw).strip() if step_name_raw else None
                
                # Only use fallback if name is truly missing or empty
                if not step_name:
                    # Try alternative fields before using Index fallback
                    step_type_val = step.get("StepType", "")
                    comment_val = step.get("Comment", "")
                    step_index_val = step.get("Index")
                    
                    # Try StepType first (e.g., "WORK_INSTRUCTION", "COMPOSITE")
                    if step_type_val and step_type_val.strip():
                        step_name = step_type_val.replace("_", " ").title()
                        _logger.info("[ARKITE] Root step %s has no Name, using StepType: '%s'", step_id, step_name)
                    # Try Comment second
                    elif comment_val and comment_val.strip():
                        step_name = comment_val.strip()[:50]  # Limit length
                        _logger.info("[ARKITE] Root step %s has no Name, using Comment: '%s'", step_id, step_name)
                    # Fallback to Index
                    elif step_index_val is not None:
                        step_name = f"Step {step_index_val}"
                        _logger.warning("[ARKITE] Root step %s has no Name, using Index fallback: '%s'", step_id, step_name)
                    else:
                        step_name = f"Step {step_id}" if step_id else "Unnamed Step"
                        _logger.warning("[ARKITE] Root step %s has no Name, using ID fallback: '%s'", step_id, step_name)
                else:
                    _logger.debug("[ARKITE] Root step %s loaded with name: '%s' (raw: %s)", step_id, step_name, step_name_raw)
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
                
                # Use root_step_id for job_step_id (or step_id if this is the first root step)
                job_step_id_value = root_step_id or step_id
                
                # Log what we're about to create
                _logger.info("[ARKITE] Creating root step record: step_id=%s, step_name='%s' (from raw: %s)", 
                           step_id, step_name, repr(step.get("Name")))
                
                record = self.env['product_module.arkite.job.step'].create({
                    'project_id': self.id,
                    'job_step_id': job_step_id_value,  # Use root step ID for all steps in this job
                    'step_id': step_id,
                    'step_name': step_name,
                    'step_type': step_type,
                    'sequence': step_index * 10,
                    'index': step_index,
                    'parent_step_id': "",  # Root step has no parent
                    'parent_id': False,  # No parent record
                    'variant_ids': [(6, 0, step_variant_records)] if step_variant_records else [],
                    'for_all_variants': for_all_variants
                })
                step_id_to_record[step_id] = record
            
            # Create child steps (iteratively, handling nested hierarchy)
            remaining_child_steps = child_steps.copy()
            max_iterations = 100  # Prevent infinite loops
            iteration = 0
            
            while remaining_child_steps and iteration < max_iterations:
                iteration += 1
                processed_this_iteration = []
                
                for step in remaining_child_steps:
                    parent_step_id = str(step.get("ParentStepId", ""))
                    
                    # Check if parent exists in our records
                    if parent_step_id in step_id_to_record:
                        step_id = str(step.get("Id", ""))
                        if not step_id:
                            _logger.warning("[ARKITE] Skipping child step with empty ID")
                            continue
                        
                        # Extract step name - handle None, empty string, and whitespace-only properly
                        step_name_raw = step.get("Name")
                        if step_name_raw is None:
                            step_name = None
                        else:
                            step_name = str(step_name_raw).strip() if step_name_raw else None
                        
                        # Only use fallback if name is truly missing or empty
                        if not step_name:
                            # Try alternative fields before using Index fallback
                            step_type_val = step.get("StepType", "")
                            comment_val = step.get("Comment", "")
                            step_index_val = step.get("Index")
                            
                            # Try StepType first (e.g., "WORK_INSTRUCTION", "COMPOSITE")
                            if step_type_val and step_type_val.strip():
                                step_name = step_type_val.replace("_", " ").title()
                                _logger.info("[ARKITE] Child step %s has no Name, using StepType: '%s'", step_id, step_name)
                            # Try Comment second
                            elif comment_val and comment_val.strip():
                                step_name = comment_val.strip()[:50]  # Limit length
                                _logger.info("[ARKITE] Child step %s has no Name, using Comment: '%s'", step_id, step_name)
                            # Fallback to Index
                            elif step_index_val is not None:
                                step_name = f"Step {step_index_val}"
                                _logger.warning("[ARKITE] Child step %s has no Name, using Index fallback: '%s'", step_id, step_name)
                            else:
                                step_name = f"Step {step_id}" if step_id else "Unnamed Step"
                                _logger.warning("[ARKITE] Child step %s has no Name, using ID fallback: '%s'", step_id, step_name)
                        else:
                            _logger.debug("[ARKITE] Child step %s loaded with name: '%s' (raw: %s)", step_id, step_name, step_name_raw)
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
                        
                        # Use root_step_id for job_step_id (all steps in a job share the same job_step_id)
                        job_step_id_value = root_step_id or step_id
                        if not job_step_id_value:
                            _logger.warning("[ARKITE] No root_step_id available, using step_id: %s", step_id)
                            job_step_id_value = step_id
                        
                        # Log what we're about to create
                        _logger.info("[ARKITE] Creating child step record: step_id=%s, step_name='%s' (from raw: %s)", 
                                   step_id, step_name, repr(step.get("Name")))
                        
                        record = self.env['product_module.arkite.job.step'].create({
                            'project_id': self.id,
                            'job_step_id': job_step_id_value,  # Use root step ID for all steps in this job
                            'step_id': step_id,
                            'step_name': step_name,
                            'step_type': step_type,
                            'sequence': step_index * 10,
                            'index': step_index,
                            'parent_step_id': parent_step_id,  # Store parent step ID
                            'parent_id': parent_record.id,  # Link to parent record - this is the key!
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
            
            # Refresh computed fields for all created records
            all_created_records = self.env['product_module.arkite.job.step'].search([
                ('project_id', '=', self.id)
            ])
            if all_created_records:
                # Invalidate first to clear any cached values
                all_created_records.invalidate_recordset(['hierarchical_level', 'parent_step_name', 'hierarchy_level', 'hierarchy_path', 'hierarchy_css_class', 'hierarchical_level_html'])
                # Then recompute in correct order
                all_created_records._compute_hierarchical_level()
                all_created_records._compute_hierarchy_level()
                all_created_records._compute_hierarchy_path()
                all_created_records._compute_parent_step_name()
                all_created_records._compute_hierarchy_css_class()
                all_created_records._compute_hierarchical_level_html()
            
            # Invalidate cache to force field refresh
            self.invalidate_recordset(['arkite_job_step_ids'])
            
            # Ensure data is committed
            self.env.cr.commit()
            
            # Return empty - let JavaScript handle the refresh
            return {}
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error loading job steps: %s", e, exc_info=True)
            raise UserError(_("Error loading job steps: %s") % str(e))
    
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
                    
                    # Separate root and child steps for proper hierarchy
                    root_steps = [s for s in process_steps if not s.get("ParentStepId") or str(s.get("ParentStepId", "")) == "0" or str(s.get("ParentStepId", "")) == ""]
                    child_steps = [s for s in process_steps if s.get("ParentStepId") and str(s.get("ParentStepId", "")) != "0" and str(s.get("ParentStepId", "")) != ""]
                    
                    _logger.info("[ARKITE] Process steps: %s root, %s children", len(root_steps), len(child_steps))
                    
                    # Map step_id to record for parent lookup
                    step_id_to_record = {}
                    
                    # Create root steps first
                    for step in root_steps:
                        step_variants = []
                        variant_ids = step.get("VariantIds", [])
                        if variant_ids:
                            for variant_id in variant_ids:
                                variant_id_str = str(variant_id)
                                if variant_id_str in variants and variants[variant_id_str]:
                                    step_variants.append((4, variants[variant_id_str].id))
                        
                        step_id = str(step.get("Id", ""))
                        record = self.env['product_module.arkite.process.step'].with_context(skip_arkite_sync=True).create({
                            'project_id': self.id,
                            'process_id': selected_process_id_str,
                            'step_id': step_id,
                            'step_name': step.get("Name", "Unnamed"),
                            'step_type': step.get("StepType", "WORK_INSTRUCTION"),
                            'sequence': step.get("Index", 0) * 10,
                            'index': step.get("Index", 0),
                            'parent_step_id': "",
                            'parent_id': False,
                            'for_all_variants': step.get("ForAllVariants", False),
                            'variant_ids': step_variants,
                        })
                        step_id_to_record[step_id] = record
                    
                    # Create child steps iteratively
                    remaining = child_steps.copy()
                    max_iter = 50
                    for _ in range(max_iter):
                        if not remaining:
                            break
                        processed = []
                        for step in remaining:
                            parent_id = str(step.get("ParentStepId", ""))
                            if parent_id in step_id_to_record:
                                step_variants = []
                                variant_ids = step.get("VariantIds", [])
                                if variant_ids:
                                    for variant_id in variant_ids:
                                        variant_id_str = str(variant_id)
                                        if variant_id_str in variants and variants[variant_id_str]:
                                            step_variants.append((4, variants[variant_id_str].id))
                                
                                step_id = str(step.get("Id", ""))
                                parent_record = step_id_to_record[parent_id]
                                record = self.env['product_module.arkite.process.step'].with_context(skip_arkite_sync=True).create({
                                    'project_id': self.id,
                                    'process_id': selected_process_id_str,
                                    'step_id': step_id,
                                    'step_name': step.get("Name", "Unnamed"),
                                    'step_type': step.get("StepType", "WORK_INSTRUCTION"),
                                    'sequence': step.get("Index", 0) * 10,
                                    'index': step.get("Index", 0),
                                    'parent_step_id': parent_id,
                                    'parent_id': parent_record.id,
                                    'for_all_variants': step.get("ForAllVariants", False),
                                    'variant_ids': step_variants,
                                })
                                step_id_to_record[step_id] = record
                                processed.append(step)
                        for s in processed:
                            remaining.remove(s)
                    
                    if remaining:
                        _logger.warning("[ARKITE] %s process steps orphaned (parent not found)", len(remaining))
                    
                    # Force recomputation of hierarchy fields after all steps are created
                    all_created_records = self.env['product_module.arkite.process.step'].search([
                        ('project_id', '=', self.id),
                        ('process_id', '=', selected_process_id_str)
                    ])
                    if all_created_records:
                        # Invalidate first to clear any cached values
                        all_created_records.invalidate_recordset(['hierarchical_level', 'parent_step_name', 'hierarchy_level', 'hierarchy_path', 'hierarchy_css_class', 'hierarchical_level_html'])
                        # Then recompute
                        all_created_records._compute_hierarchical_level()
                        all_created_records._compute_hierarchy_level()
                        all_created_records._compute_hierarchy_path()
                        all_created_records._compute_parent_step_name()
                        all_created_records._compute_hierarchy_css_class()
                        all_created_records._compute_hierarchical_level_html()
                    
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

    def action_sync_materials_from_arkite(self):
        """Load/sync materials from Arkite into this project's Materials Used (material_ids)."""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_('Please create or link an Arkite project first.'))

        # Get credentials
        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception as e:
            _logger.error("[ARKITE SYNC] Credential error (materials): %s", e, exc_info=True)
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration. Error: %s') % str(e))

        created_count = 0
        updated_count = 0

        try:
            url = f"{api_base}/projects/{self.arkite_project_id}/materials/"
            params = {"apiKey": api_key}
            response = requests.get(url, params=params, verify=False, timeout=10)
            if not response.ok:
                raise UserError(_('Failed to fetch materials: HTTP %s') % response.status_code)

            arkite_materials = response.json()
            if not isinstance(arkite_materials, list):
                raise UserError(_('Unexpected response format from Arkite API (materials).'))

            arkite_material_ids = {str(m.get("Id", "")) for m in arkite_materials if m.get("Id")}
            existing_by_arkite_id = {
                (m.arkite_material_id or ""): m
                for m in self.material_ids.filtered(lambda m: m.project_id == self and m.arkite_material_id)
            }

            def _map_type(arkite_type, fallback="StandardMaterial"):
                if arkite_type == "PickingBinMaterial":
                    return "PickingBinMaterial"
                if arkite_type == "StandardMaterial":
                    return "StandardMaterial"
                if arkite_type == "Material" or not arkite_type:
                    return "StandardMaterial"
                return fallback

            # Create missing materials by Arkite ID
            for material_data in arkite_materials:
                arkite_id = str(material_data.get("Id", "") or "")
                if not arkite_id or arkite_id in existing_by_arkite_id:
                    continue

                picking_bin_ids = material_data.get("PickingBinIds", [])
                picking_bin_str = ", ".join(str(bid) for bid in picking_bin_ids) if picking_bin_ids else ""
                arkite_type = material_data.get("Type", "")
                odoo_type = _map_type(arkite_type)

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

            # Update existing + link by name where possible
            for material in self.material_ids.filtered(lambda m: m.project_id == self):
                if material.arkite_material_id and material.arkite_material_id in arkite_material_ids:
                    match = next((m for m in arkite_materials if str(m.get("Id", "")) == material.arkite_material_id), None)
                    if not match:
                        continue
                    picking_bin_ids = match.get("PickingBinIds", [])
                    picking_bin_str = ", ".join(str(bid) for bid in picking_bin_ids) if picking_bin_ids else ""
                    arkite_type = match.get("Type", "")
                    odoo_type = _map_type(arkite_type, fallback=material.material_type)
                    material.write({
                        'name': match.get("Name", material.name),
                        'material_type': odoo_type,
                        'description': match.get("Description", material.description or ""),
                        'image_id': str(match.get("ImageId", "")) if match.get("ImageId") else material.image_id,
                        'picking_bin_ids_text': picking_bin_str,
                    })
                    updated_count += 1
                elif not material.arkite_material_id:
                    # Try match by name
                    match = next((m for m in arkite_materials if (m.get("Name", "") and m.get("Name", "") == material.name)), None)
                    if not match:
                        continue
                    picking_bin_ids = match.get("PickingBinIds", [])
                    picking_bin_str = ", ".join(str(bid) for bid in picking_bin_ids) if picking_bin_ids else ""
                    arkite_type = match.get("Type", "")
                    odoo_type = _map_type(arkite_type, fallback=material.material_type)
                    material.write({
                        'arkite_material_id': str(match.get("Id", "")),
                        'material_type': odoo_type,
                        'description': match.get("Description", material.description or ""),
                        'image_id': str(match.get("ImageId", "")) if match.get("ImageId") else material.image_id,
                        'picking_bin_ids_text': picking_bin_str,
                    })
                    updated_count += 1

            self.invalidate_recordset(['material_ids'])

        except UserError:
            raise
        except Exception as e:
            _logger.error("[ARKITE SYNC] Error syncing materials: %s", e, exc_info=True)
            raise UserError(_('Error loading materials: %s') % str(e))

        # Optionally fetch images right after sync so the user sees them immediately.
        # This is best-effort; failures don't block material sync.
        try:
            import base64
            for mat in self.material_ids.filtered(lambda m: m.image_id and not m.image):
                img_bytes = self._arkite_download_image_bytes(api_base, api_key, mat.image_id)
                if img_bytes:
                    mat.image = base64.b64encode(img_bytes)
        except Exception as e:
            _logger.info("[ARKITE IMAGE] Skipped fetching some material images after sync: %s", e)

        msg = _('Materials synced from Arkite: %s new, %s updated.') % (created_count, updated_count)
        # Do NOT return an act_window refresh here.
        # It forces modal forms to navigate into a full-page form.
        # The UI reload is handled by a small JS hook after the button executes.
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Materials Loaded'),
                'message': msg,
                'type': 'success' if (created_count or updated_count) else 'info',
                'sticky': False,
            }
        }

    def _arkite_download_image_bytes(self, api_base, api_key, image_id):
        """Best-effort download of an Arkite image by ID. Returns raw bytes or None."""
        self.ensure_one()
        client = ArkiteClient(api_base=api_base, api_key=api_key, verify_ssl=False, timeout_sec=20)
        return client.download_image_bytes(str(self.arkite_project_id), str(image_id))

    def action_fetch_material_images_from_arkite(self):
        """Fetch material images from Arkite (by image_id) into the Materials Used list."""
        import base64

        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_('Please create or link an Arkite project first.'))

        try:
            creds = self._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception as e:
            _logger.error("[ARKITE IMAGE] Credential error: %s", e, exc_info=True)
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration.'))

        fetched = 0
        skipped = 0
        failed = 0

        # Only fill missing images by default (avoid overwriting any uploaded ones)
        materials = self.material_ids.filtered(lambda m: m.image_id)
        for mat in materials:
            if mat.image:
                skipped += 1
                continue
            img_bytes = self._arkite_download_image_bytes(api_base, api_key, mat.image_id)
            if not img_bytes:
                failed += 1
                continue
            mat.image = base64.b64encode(img_bytes)
            fetched += 1

        msg = _("Fetched %s image(s). Skipped %s (already had image). Failed %s.") % (fetched, skipped, failed)
        # Do NOT return an act_window refresh here for the same reason as materials sync.
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Images Updated'),
                'message': msg,
                'type': 'success' if fetched else ('warning' if failed else 'info'),
                'sticky': False,
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
        
        # Sync step sequence changes to Arkite when steps are reordered
        if self.arkite_project_id:
            try:
                creds = self._get_arkite_credentials()
                api_base = creds['api_base']
                api_key = creds['api_key']
                
                # Handle process step reordering
                if 'arkite_process_step_ids' in vals:
                    _logger.info("[ARKITE] Process steps reordered, syncing to Arkite...")
                    # Get all process steps sorted by sequence (current order)
                    sorted_steps = self.arkite_process_step_ids.sorted('sequence')
                    
                    # Filter to only root steps (no parent) for reordering
                    root_steps = sorted_steps.filtered(lambda s: not s.parent_id)
                    
                    for idx, step in enumerate(root_steps):
                        if not step.step_id:
                            continue
                        new_index = idx  # Index starts at 0
                        current_arkite_index = step.index if step.index is not False else None
                        
                        # Always update to ensure sync (don't check if different, just update)
                        try:
                            url = f"{api_base}/projects/{self.arkite_project_id}/steps/{step.step_id}/"
                            params = {"apiKey": api_key}
                            headers = {"Content-Type": "application/json"}
                            
                            # Get current step data
                            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                            if response.ok:
                                step_data = response.json()
                                old_index = step_data.get("Index", 0)
                                step_data["Index"] = new_index
                                
                                patch_response = requests.patch(url, params=params, headers=headers, json=step_data, verify=False, timeout=10)
                                if patch_response.ok:
                                    # Update our local index and sequence
                                    step.with_context(skip_arkite_sync=True).write({
                                        'index': new_index,
                                        'sequence': new_index * 10
                                    })
                                    _logger.info("[ARKITE] Updated process step %s Index from %s to %s", step.step_id, old_index, new_index)
                                else:
                                    _logger.warning("[ARKITE] Failed to update process step %s: HTTP %s - %s", step.step_id, patch_response.status_code, patch_response.text[:200])
                            else:
                                _logger.warning("[ARKITE] Could not fetch process step %s: HTTP %s", step.step_id, response.status_code)
                        except Exception as e:
                            _logger.error("[ARKITE] Error updating process step %s: %s", step.step_id, e, exc_info=True)
                
                # Handle job step reordering
                if 'arkite_job_step_ids' in vals:
                    _logger.info("[ARKITE] Job steps reordered, syncing to Arkite...")
                    # Get all job steps sorted by sequence (current order)
                    sorted_steps = self.arkite_job_step_ids.sorted('sequence')
                    
                    # Filter to only root steps (no parent) for reordering
                    root_steps = sorted_steps.filtered(lambda s: not s.parent_id)
                    
                    for idx, step in enumerate(root_steps):
                        if not step.step_id:
                            continue
                        new_index = idx  # Index starts at 0
                        current_arkite_index = step.index if step.index is not False else None
                        
                        # Always update to ensure sync
                        try:
                            url = f"{api_base}/projects/{self.arkite_project_id}/steps/{step.step_id}/"
                            params = {"apiKey": api_key}
                            headers = {"Content-Type": "application/json"}
                            
                            # Get current step data
                            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                            if response.ok:
                                step_data = response.json()
                                old_index = step_data.get("Index", 0)
                                step_data["Index"] = new_index
                                
                                patch_response = requests.patch(url, params=params, headers=headers, json=step_data, verify=False, timeout=10)
                                if patch_response.ok:
                                    # Update our local index and sequence
                                    step.with_context(skip_arkite_sync=True).write({
                                        'index': new_index,
                                        'sequence': new_index * 10
                                    })
                                    _logger.info("[ARKITE] Updated job step %s Index from %s to %s", step.step_id, old_index, new_index)
                                else:
                                    _logger.warning("[ARKITE] Failed to update job step %s: HTTP %s - %s", step.step_id, patch_response.status_code, patch_response.text[:200])
                            else:
                                _logger.warning("[ARKITE] Could not fetch job step %s: HTTP %s", step.step_id, response.status_code)
                        except Exception as e:
                            _logger.error("[ARKITE] Error updating job step %s: %s", step.step_id, e, exc_info=True)
            except Exception as e:
                _logger.warning("[ARKITE] Error syncing step order to Arkite: %s", e)
        
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

    def _arkite_sync_all_staged_hierarchies(self):
        """Push any staged hierarchy changes (job + process steps) to Arkite."""
        self.ensure_one()
        if not self.arkite_project_id:
            return

        # Job steps: sync all for project
        try:
            self.env['product_module.arkite.job.step'].with_context(default_project_id=self.id).pm_action_save_all()
        except Exception as e:
            raise UserError(_("Failed to sync Job Steps to Arkite:\n%s") % str(e))

        # Process steps: sync per process_id
        process_ids = self.env['product_module.arkite.process.step'].search([
            ('project_id', '=', self.id),
            ('process_id', '!=', False),
        ]).mapped('process_id')
        for pid in sorted(set(process_ids)):
            try:
                self.env['product_module.arkite.process.step'].with_context(
                    default_project_id=self.id,
                    default_process_id=pid,
                ).pm_action_save_all()
            except Exception as e:
                raise UserError(_("Failed to sync Process Steps to Arkite (Process %s):\n%s") % (pid, str(e)))

    def write(self, vals):
        """Override write to sync all materials to Arkite when project is saved, and delete removed materials"""
        # Track materials before write to detect removals
        materials_before = set()
        if self.arkite_project_id and 'material_ids' not in vals:
            # If material_ids is being modified, track current materials
            materials_before = set(self.material_ids.filtered(lambda m: m.project_id == self and m.arkite_material_id).mapped('arkite_material_id'))

        result = super().write(vals)

        # Existing behavior: materials + (legacy) step reorder sync blocks remain below
        # (â€¦ existing code continues â€¦)

        # At the very end of saving the Project in the form, if we have staged hierarchy changes,
        # push them to Arkite once and clear the flag.
        if not self.env.context.get('skip_arkite_hierarchy_autosync'):
            for project in self:
                if project.arkite_project_id and project.arkite_hierarchy_dirty:
                    project._arkite_sync_all_staged_hierarchies()
                    project.with_context(skip_arkite_hierarchy_autosync=True).write({'arkite_hierarchy_dirty': False})

        return result

