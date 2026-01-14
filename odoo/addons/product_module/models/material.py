# product_module/models/material.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
import base64
import io

_logger = logging.getLogger(__name__)

class ProductModuleMaterial(models.Model):
    _name = 'product_module.material'
    _description = 'Product Material'
    _order = 'name, id'
    
    @api.model
    def create(self, vals):
        """Auto-set page_id from project_id if not provided"""
        if not vals.get('page_id') and vals.get('project_id'):
            project = self.env['product_module.project'].browse(vals['project_id'])
            if project and project.page_id:
                vals['page_id'] = project.page_id.id
        return super().create(vals)
    
    def write(self, vals):
        """Auto-update page_id when project_id changes, and sync to Arkite if needed"""
        if 'project_id' in vals and not vals.get('page_id'):
            project = self.env['product_module.project'].browse(vals['project_id'])
            if project and project.page_id:
                vals['page_id'] = project.page_id.id
        
        # Track if we need to sync to Arkite
        sync_needed = False
        fields_to_sync = ['name', 'material_type', 'description', 'image_id', 'picking_bin_ids_text']
        if any(field in vals for field in fields_to_sync):
            sync_needed = True
        
        result = super().write(vals)
        
        # Sync to Arkite if relevant fields changed
        if sync_needed:
            for material in self:
                if material.project_id and material.project_id.arkite_project_id:
                    material._sync_to_arkite(create=False)
        
        return result

    # Basic fields
    name = fields.Char(string='Material Name', required=True)
    material_type = fields.Selection(
        [
            ('PickingBinMaterial', 'Picking Bin Material'),
            ('StandardMaterial', 'Standard Material'),
        ],
        string='Material Type',
        required=True,
        default='StandardMaterial'
    )
    description = fields.Text(string='Description')
    image = fields.Binary(string='Image', attachment=True)
    image_id = fields.Char(string='Arkite Image ID', help='Image ID from Arkite platform')
    picking_bin_ids_text = fields.Text(
        string='Picking Bin IDs',
        help='Comma-separated list of Picking Bin IDs (e.g., "1111,2222,3333")'
    )
    arkite_material_id = fields.Char(
        string='Arkite Material ID',
        readonly=True,
        help='Material ID from Arkite platform (auto-filled when synced)'
    )

    # Relationships
    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    project_id = fields.Many2one('product_module.project', string='Project', ondelete='set null', help='Project this material belongs to')
    project_ids = fields.Many2many('product_module.project', 'material_project_rel', 'material_id', 'project_id', string='Additional Projects', help='Additional projects that use this material')
    product_ids = fields.Many2many(
        'product_module.product',
        string='Used in Products',
        help='Products that use this material'
    )
    product_type_ids = fields.Many2many(
        'product_module.type',
        string='Used in Categories',
        help='Categories that use this material'
    )

    # Computed fields
    usage_count = fields.Integer(
        string='Usage Count',
        compute='_compute_usage_count',
        help='Number of products using this material'
    )

    @api.depends('product_ids')
    def _compute_usage_count(self):
        """Compute number of products using this material"""
        for record in self:
            record.usage_count = len(record.product_ids)
    
    @api.onchange('image')
    def _onchange_image_upload_to_arkite(self):
        """Upload image to Arkite when image is set and auto-fill image_id"""
        if not self.image or not self.project_id or not self.project_id.arkite_project_id:
            return
        
        # Get credentials
        try:
            creds = self.project_id._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            _logger.warning("Could not get credentials for image upload")
            return
        
        # Decode base64 image
        try:
            image_data = base64.b64decode(self.image)
        except Exception as e:
            _logger.error("Error decoding image: %s", e)
            return
        
        # Upload to Arkite
        url = f"{api_base}/projects/{self.project_id.arkite_project_id}/images/"
        params = {"apiKey": api_key}
        
        # Prepare file for upload
        # The API expects multipart/form-data with field name "filename"
        files = {
            'filename': ('image.png', image_data, 'image/png')  # Default to PNG, could detect type
        }
        
        try:
            response = requests.post(url, params=params, files=files, verify=False, timeout=30)
            if response.ok:
                result = response.json()
                # API returns a Resource object or list of Resource objects
                if isinstance(result, list) and result:
                    image_id = result[0].get('Id')
                elif isinstance(result, dict):
                    image_id = result.get('Id')
                else:
                    image_id = None
                
                if image_id:
                    self.image_id = str(image_id)
                    _logger.info("Uploaded image to Arkite, got ID: %s", image_id)
            else:
                _logger.warning("Failed to upload image to Arkite: HTTP %s - %s", response.status_code, response.text[:200])
        except Exception as e:
            _logger.error("Error uploading image to Arkite: %s", e, exc_info=True)
    
    def action_load_picking_bins_from_detections(self):
        """Helper method to load picking bin IDs from detections"""
        self.ensure_one()
        if not self.project_id:
            raise UserError(_('Project is required to load picking bins.'))
        
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
                    'message': _('No picking bin detections found in this project. Please load detections first in the Detections tab.'),
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
    
    def action_browse_arkite_images(self):
        """Open a wizard to browse and select images from Arkite"""
        self.ensure_one()
        # Get project (from project_id or first project_ids)
        project = self.project_id or (self.project_ids[:1] if self.project_ids else None)
        if not project or not project.arkite_project_id:
            raise UserError(_('Please link this material to a project with an Arkite project first.'))
        
        # Get credentials
        try:
            creds = project._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration.'))
        
        # Fetch images from Arkite
        url = f"{api_base}/projects/{project.arkite_project_id}/images/"
        params = {"apiKey": api_key}
        
        try:
            response = requests.get(url, params=params, verify=False, timeout=10)
            if not response.ok:
                raise UserError(_('Failed to fetch images from Arkite: HTTP %s') % response.status_code)
            
            images = response.json()
            if not isinstance(images, list):
                images = []
            
            if not images:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('No Images Found'),
                        'message': _('No images found in this Arkite project. Please upload images first in Arkite.'),
                        'type': 'warning',
                        'sticky': False,
                    }
                }
            
            # Create a simple selection dialog
            # For now, show a notification with available image IDs
            image_ids = [str(img.get('Id', '')) for img in images if img.get('Id')]
            if image_ids:
                message = _('Available Image IDs: %s\n\nEnter one of these IDs in the Image ID field.') % ', '.join(image_ids[:20])
                if len(image_ids) > 20:
                    message += _('\n(Showing first 20 of %s images)') % len(image_ids)
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Available Images'),
                        'message': message,
                        'type': 'info',
                        'sticky': True,
                    }
                }
            
        except requests.exceptions.RequestException as e:
            _logger.error("Error fetching images: %s", e)
            raise UserError(_('Error connecting to Arkite API: %s') % str(e))
        
        return False
    
    def _sync_to_arkite(self, create=False):
        """Sync material to Arkite (create or update)"""
        self.ensure_one()
        
        if not self.project_id or not self.project_id.arkite_project_id:
            return
        
        # Get credentials
        try:
            creds = self.project_id._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            _logger.warning("Could not get credentials for syncing material to Arkite")
            return
        
        # Parse picking bin IDs
        picking_bin_ids = []
        if self.picking_bin_ids_text:
            text = self.picking_bin_ids_text.strip()
            if text:
                try:
                    picking_bin_ids = [int(bid.strip()) for bid in text.split(',') if bid.strip().isdigit()]
                except ValueError:
                    _logger.warning("Invalid picking bin IDs format, skipping")
        
        # Build material payload
        material_data = {
            "Name": self.name or 'Unnamed Material',
            "Type": self.material_type or 'StandardMaterial',
            "Description": self.description or '',
        }
        
        if self.image_id:
            try:
                material_data["ImageId"] = int(self.image_id)
            except ValueError:
                pass  # Skip if not a valid number
        
        if picking_bin_ids:
            material_data["PickingBinIds"] = picking_bin_ids
        
        if create:
            # Create material in Arkite
            url = f"{api_base}/projects/{self.project_id.arkite_project_id}/materials/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("[ARKITE] Creating material: %s", material_data)
            
            try:
                response = requests.post(url, params=params, headers=headers, json=[material_data], verify=False, timeout=10)
                if response.ok:
                    created_materials = response.json()
                    if isinstance(created_materials, list) and created_materials:
                        created = created_materials[0]
                        arkite_id = str(created.get("Id", ""))
                        if arkite_id:
                            # Use sudo to write to avoid recursion
                            self.sudo().write({'arkite_material_id': arkite_id})
                            _logger.info("[ARKITE] Created material with ID: %s", arkite_id)
                    elif isinstance(created_materials, dict):
                        arkite_id = str(created_materials.get("Id", ""))
                        if arkite_id:
                            self.sudo().write({'arkite_material_id': arkite_id})
                            _logger.info("[ARKITE] Created material with ID: %s", arkite_id)
                else:
                    error_text = response.text[:500] if response.text else "Unknown error"
                    _logger.error("[ARKITE] Failed to create material: HTTP %s - %s", response.status_code, error_text)
            except requests.exceptions.RequestException as e:
                _logger.error("[ARKITE] Error creating material: %s", e, exc_info=True)
        else:
            # Update material in Arkite
            if not self.arkite_material_id:
                # If no Arkite ID exists, create it instead
                self._sync_to_arkite(create=True)
                return
            
            url = f"{api_base}/projects/{self.project_id.arkite_project_id}/materials/{self.arkite_material_id}/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("[ARKITE] Updating material %s: %s", self.arkite_material_id, material_data)
            
            try:
                response = requests.patch(url, params=params, headers=headers, json=material_data, verify=False, timeout=10)
                if response.ok:
                    _logger.info("[ARKITE] Updated material %s successfully", self.arkite_material_id)
                else:
                    _logger.warning("[ARKITE] Failed to update material: HTTP %s, %s", response.status_code, response.text[:200])
            except requests.exceptions.RequestException as e:
                _logger.error("[ARKITE] Error updating material: %s", e, exc_info=True)
    
    def unlink(self):
        """Delete material from Arkite when deleted in Odoo"""
        for material in self:
            if material.arkite_material_id and material.project_id and material.project_id.arkite_project_id:
                try:
                    creds = material.project_id._get_arkite_credentials()
                    api_base = creds['api_base']
                    api_key = creds['api_key']
                    
                    url = f"{api_base}/projects/{material.project_id.arkite_project_id}/materials/{material.arkite_material_id}/"
                    params = {"apiKey": api_key}
                    
                    response = requests.delete(url, params=params, verify=False, timeout=10)
                    if response.ok:
                        _logger.info("[ARKITE] Deleted material %s", material.arkite_material_id)
                    else:
                        _logger.warning("[ARKITE] Failed to delete material: HTTP %s", response.status_code)
                except Exception as e:
                    _logger.warning("[ARKITE] Error deleting material: %s", e)
        
        return super().unlink()
    
    def action_select_arkite_image(self):
        """Open Arkite image selector wizard to select an image for this material"""
        self.ensure_one()
        
        # Get project from material
        project = self.project_id
        if not project:
            raise UserError(_('Material must be linked to a project to select Arkite images.'))
        
        if not project.arkite_project_id:
            raise UserError(_('Project must be linked to an Arkite project first.'))
        
        # Create wizard with material context
        wizard = self.env['product_module.arkite.image.selector.wizard'].create({
            'project_id': project.id,
            'material_id': self.id,
        })
        
        # Auto-load images
        wizard.action_load_images()
        
        return {
            'name': _('Select Arkite Image for %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'product_module.arkite.image.selector.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_project_id': project.id,
                'default_material_id': self.id,
            }
        }
    
    def action_link_to_project(self):
        """Link selected materials to the project from context"""
        if not self:
            return False
        
        project_id = self.env.context.get('active_project_id')
        if not project_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('No project specified. Please use this action from the project form.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        project = self.env['product_module.project'].browse(project_id)
        if not project.exists():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Project not found.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        # Update materials to link to project
        linked_count = 0
        for material in self:
            if material.project_id != project:
                material.write({
                    'project_id': project.id,
                    'page_id': project.page_id.id if project.page_id else material.page_id,
                })
                linked_count += 1
        
        if linked_count > 0:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Linked %s material(s) to the project.') % linked_count,
                    'type': 'success',
                    'sticky': False,
                }
            }
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Info'),
                'message': _('Selected materials are already linked to this project.'),
                'type': 'info',
                'sticky': False,
            }
        }

