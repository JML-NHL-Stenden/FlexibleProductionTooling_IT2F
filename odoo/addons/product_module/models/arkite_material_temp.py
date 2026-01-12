# product_module/models/arkite_material_temp.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import os
import logging

_logger = logging.getLogger(__name__)

class ArkiteMaterialTemp(models.TransientModel):
    """Temporary model for managing materials in Arkite"""
    _name = 'product_module.arkite.material.temp'
    _description = 'Arkite Material (Temporary)'
    _rec_name = 'name'
    _order = 'name, id'
    
    project_id = fields.Many2one('product_module.project', string='Project', ondelete='cascade', required=True)
    material_id = fields.Char(string='Material ID', readonly=True, help='Arkite Material ID (auto-filled when loaded from Arkite)')
    name = fields.Char(string='Material Name', required=True)
    material_type = fields.Selection([
        ('PickingBinMaterial', 'Picking Bin Material'),
        ('StandardMaterial', 'Standard Material'),
    ], string='Type', default='PickingBinMaterial', required=True, help='Material type in Arkite')
    description = fields.Text(string='Description', help='Material description')
    image_id = fields.Char(string='Image ID', help='Arkite Image ID (optional)')
    picking_bin_ids_text = fields.Text(
        string='Picking Bin IDs',
        help='Enter picking bin IDs separated by commas (e.g., 1111,2222,3333). Leave empty if not applicable.'
    )
    
    def action_load_picking_bins_from_detections(self):
        """Helper method to load picking bin IDs from detections"""
        self.ensure_one()
        if not self.project_id:
            raise UserError(_('Project is required.'))
        
        # Get all picking bin detections for this project
        picking_bin_detections = self.env['product_module.arkite.detection.temp'].search([
            ('project_id', '=', self.project_id.id),
            ('detection_type', '=', 'PICKING_BIN')
        ])
        
        if not picking_bin_detections:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Picking Bins Found'),
                    'message': _('No picking bin detections found in this project. Please create picking bin detections first in the Detections tab.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Get detection IDs
        picking_bin_ids = [det.detection_id for det in picking_bin_detections if det.detection_id]
        
        if picking_bin_ids:
            self.picking_bin_ids_text = ", ".join(picking_bin_ids)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Picking Bins Loaded'),
                    'message': _('Loaded %s picking bin ID(s) from detections.') % len(picking_bin_ids),
                    'type': 'success',
                    'sticky': False,
                }
            }
        
        return False
    
    @api.model
    def create(self, vals):
        """Create material in Arkite and then in Odoo"""
        # Get project
        project = self.env['product_module.project'].browse(vals.get('project_id'))
        if not project or not project.arkite_project_id:
            raise UserError(_('Please link this project to an Arkite project first.'))
        
        # Get credentials
        try:
            creds = project._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration.'))
        
        # Parse picking bin IDs
        picking_bin_ids = []
        if vals.get('picking_bin_ids_text'):
            text = vals.get('picking_bin_ids_text', '').strip()
            if text:
                try:
                    picking_bin_ids = [int(bid.strip()) for bid in text.split(',') if bid.strip().isdigit()]
                except ValueError:
                    raise UserError(_('Invalid picking bin IDs format. Use comma-separated numbers (e.g., 1111,2222).'))
        
        # Build material payload
        material_data = {
            "Name": vals.get('name', 'Unnamed Material'),
            "Type": vals.get('material_type', 'PickingBinMaterial'),
            "Description": vals.get('description', ''),
        }
        
        if vals.get('image_id'):
            try:
                material_data["ImageId"] = int(vals['image_id'])
            except ValueError:
                pass  # Skip if not a valid number
        
        if picking_bin_ids:
            material_data["PickingBinIds"] = picking_bin_ids
        
        # Create material in Arkite
        url = f"{api_base}/projects/{project.arkite_project_id}/materials/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        _logger.info("[ARKITE] Creating material: %s", material_data)
        
        try:
            response = requests.post(url, params=params, headers=headers, json=[material_data], verify=False, timeout=10)
            if not response.ok:
                error_text = response.text[:500] if response.text else "Unknown error"
                _logger.error("[ARKITE] Failed to create material: HTTP %s - %s", response.status_code, error_text)
                raise UserError(_('Failed to create material in Arkite: HTTP %s\n%s') % (response.status_code, error_text))
            
            # Get created material ID
            created_materials = response.json()
            if isinstance(created_materials, list) and created_materials:
                created = created_materials[0]
                vals['material_id'] = str(created.get("Id", ""))
            elif isinstance(created_materials, dict):
                vals['material_id'] = str(created_materials.get("Id", ""))
            else:
                raise UserError(_('Unexpected response format from Arkite API'))
            
            _logger.info("[ARKITE] Created material with ID: %s", vals['material_id'])
            
        except requests.exceptions.RequestException as e:
            _logger.error("[ARKITE] Error creating material: %s", e, exc_info=True)
            raise UserError(_('Error connecting to Arkite API: %s') % str(e))
        
        return super().create(vals)
    
    def write(self, vals):
        """Update material in Arkite when fields change"""
        result = super().write(vals)
        
        # Only update in Arkite if material_id exists and relevant fields changed
        if not self.material_id:
            return result
        
        fields_to_sync = ['name', 'material_type', 'description', 'image_id', 'picking_bin_ids_text']
        if not any(field in vals for field in fields_to_sync):
            return result
        
        project = self.project_id
        if not project or not project.arkite_project_id:
            return result
        
        # Get credentials
        try:
            creds = project._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            _logger.warning("Could not get credentials for updating material")
            return result
        
        # Build update payload
        update_data = {}
        if 'name' in vals:
            update_data["Name"] = vals['name']
        if 'material_type' in vals:
            update_data["Type"] = vals['material_type']
        if 'description' in vals:
            update_data["Description"] = vals.get('description', '')
        if 'image_id' in vals:
            if vals['image_id']:
                try:
                    update_data["ImageId"] = int(vals['image_id'])
                except ValueError:
                    pass
        
        # Parse picking bin IDs if changed
        if 'picking_bin_ids_text' in vals:
            picking_bin_ids = []
            text = vals.get('picking_bin_ids_text', '').strip()
            if text:
                try:
                    picking_bin_ids = [int(bid.strip()) for bid in text.split(',') if bid.strip().isdigit()]
                except ValueError:
                    _logger.warning("Invalid picking bin IDs format, skipping update")
                    return result
            update_data["PickingBinIds"] = picking_bin_ids
        
        if not update_data:
            return result
        
        # Update material in Arkite
        url = f"{api_base}/projects/{project.arkite_project_id}/materials/{self.material_id}/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        _logger.info("[ARKITE] Updating material %s: %s", self.material_id, update_data)
        
        try:
            response = requests.patch(url, params=params, headers=headers, json=update_data, verify=False, timeout=10)
            if not response.ok:
                _logger.warning("[ARKITE] Failed to update material: HTTP %s, %s", response.status_code, response.text[:200])
        except Exception as e:
            _logger.warning("[ARKITE] Error updating material: %s", e)
        
        return result
    
    def unlink(self):
        """Delete material from Arkite"""
        for record in self:
            if record.material_id and record.project_id and record.project_id.arkite_project_id:
                try:
                    creds = record.project_id._get_arkite_credentials()
                    api_base = creds['api_base']
                    api_key = creds['api_key']
                    
                    url = f"{api_base}/projects/{record.project_id.arkite_project_id}/materials/{record.material_id}/"
                    params = {"apiKey": api_key}
                    
                    try:
                        response = requests.delete(url, params=params, verify=False, timeout=10)
                        if response.ok:
                            _logger.info("[ARKITE] Deleted material %s", record.material_id)
                        else:
                            _logger.warning("[ARKITE] Failed to delete material: HTTP %s", response.status_code)
                    except Exception as e:
                        _logger.warning("[ARKITE] Error deleting material: %s", e)
                except Exception:
                    pass
        
        return super().unlink()
