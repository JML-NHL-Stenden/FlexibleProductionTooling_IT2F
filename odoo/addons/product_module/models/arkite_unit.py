# product_module/models/arkite_unit.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)


class ArkiteUnit(models.Model):
    """Model to store Arkite unit/workstation information and credentials"""
    _name = 'product_module.arkite.unit'
    _description = 'Arkite Unit/Workstation'
    _rec_name = 'display_name'
    _order = 'name'
    
    @api.model
    def create_from_env(self):
        """Helper method to create a unit from environment variables (for initial setup)"""
        import os
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        unit_id = os.getenv('ARKITE_UNIT_ID')
        template_name = os.getenv('ARKITE_TEMPLATE_NAME', '')
        
        if not api_base or not api_key or not unit_id:
            raise UserError(_('Missing required environment variables: ARKITE_API_BASE, ARKITE_API_KEY, or ARKITE_UNIT_ID'))
        
        # Check if unit already exists
        existing = self.search([('unit_id', '=', unit_id)], limit=1)
        if existing:
            return existing
        
        return self.create({
            'name': f'Workstation {unit_id}',
            'unit_id': unit_id,
            'api_base': api_base,
            'api_key': api_key,
            'template_name': template_name,
            'active': True,
        })
    
    name = fields.Char(
        string='Unit Name',
        required=True,
        help='Friendly name for this unit (e.g., "Production Line 1", "Workstation A")'
    )
    
    unit_id = fields.Char(
        string='Unit ID',
        required=True,
        help='Arkite Unit ID (numeric ID from Arkite system)'
    )
    
    api_base = fields.Char(
        string='API Base URL',
        required=True,
        help='Base URL for Arkite API (e.g., https://192.168.178.93/api/v1)'
    )
    
    api_key = fields.Char(
        string='API Key',
        required=True,
        help='API key for this unit'
    )
    
    template_name = fields.Char(
        string='Template Project Name',
        help='Default template project name to use for this unit'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Uncheck to archive this unit without deleting it'
    )
    
    description = fields.Text(
        string='Description',
        help='Additional notes about this unit'
    )
    
    # Related fields
    project_count = fields.Integer(
        string='Projects',
        compute='_compute_project_count',
        help='Number of projects assigned to this unit'
    )
    
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True,
        readonly=True
    )
    
    @api.depends('name', 'unit_id')
    def _compute_display_name(self):
        for record in self:
            if record.name and record.unit_id:
                record.display_name = f"{record.name} (ID: {record.unit_id})"
            elif record.name:
                record.display_name = record.name
            elif record.unit_id:
                record.display_name = f"Unit {record.unit_id}"
            else:
                record.display_name = "New Unit"
    
    @api.depends('name')
    def _compute_project_count(self):
        for record in self:
            if record.id:
                record.project_count = self.env['product_module.project'].search_count([
                    ('arkite_unit_id', '=', record.id)
                ])
            else:
                record.project_count = 0
    
    @api.constrains('unit_id')
    def _check_unit_id(self):
        for record in self:
            if record.unit_id and not record.unit_id.isdigit():
                raise UserError(_('Unit ID must be numeric.'))
    
    @api.constrains('api_base')
    def _check_api_base(self):
        for record in self:
            if record.api_base and not (record.api_base.startswith('http://') or record.api_base.startswith('https://')):
                raise UserError(_('API Base URL must start with http:// or https://'))
    
    def action_test_connection(self):
        """Test the connection to Arkite API with this unit's credentials"""
        self.ensure_one()
        
        if not self.api_base or not self.api_key:
            raise UserError(_('API Base URL and API Key are required to test connection.'))
        
        try:
            # Try to get units list or a simple endpoint
            url = f"{self.api_base}/units/{self.unit_id}"
            params = {"apiKey": self.api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            
            if response.ok:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connection Successful'),
                        'message': _('Successfully connected to Arkite API for unit "%s"') % self.name,
                        'type': 'success',
                    }
                }
            elif response.status_code == 401:
                raise UserError(_('Authentication failed. Please check your API key.'))
            elif response.status_code == 404:
                raise UserError(_('Unit ID %s not found on the Arkite server.') % self.unit_id)
            else:
                raise UserError(_('Connection failed: HTTP %s - %s') % (response.status_code, response.text[:100]))
        except requests.exceptions.RequestException as e:
            raise UserError(_('Connection error: %s') % str(e))
        except Exception as e:
            _logger.error("Error testing connection: %s", e)
            raise UserError(_('Error testing connection: %s') % str(e))
    
    def action_view_projects(self):
        """View all projects assigned to this unit"""
        self.ensure_one()
        return {
            'name': _('Projects for %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'product_module.project',
            'view_mode': 'list,form',
            'domain': [('arkite_unit_id', '=', self.id)],
            'context': {'default_arkite_unit_id': self.id, 'search_default_arkite_unit_id': self.id},
        }
