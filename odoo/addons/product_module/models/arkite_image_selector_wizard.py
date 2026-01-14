# product_module/models/arkite_image_selector_wizard.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging
import base64

_logger = logging.getLogger(__name__)


class ArkiteImageSelectorWizard(models.TransientModel):
    _name = 'product_module.arkite.image.selector.wizard'
    _description = 'Arkite Image Selector Wizard'

    project_id = fields.Many2one(
        'product_module.project',
        string='Project',
        required=True,
        readonly=True,
        help='Project to fetch images from'
    )
    
    material_id = fields.Many2one(
        'product_module.material',
        string='Material',
        readonly=True,
        help='Material to assign the selected image to (optional)'
    )
    
    image_ids = fields.One2many(
        'product_module.arkite.image.selector.line',
        'wizard_id',
        string='Available Images',
        help='Images available in Arkite project'
    )
    
    state = fields.Selection([
        ('loading', 'Loading...'),
        ('loaded', 'Loaded'),
        ('error', 'Error')
    ], string='State', default='loading', readonly=True)
    
    error_message = fields.Text(string='Error Message', readonly=True)
    
    @api.model
    def default_get(self, fields_list):
        """Auto-load images when wizard opens"""
        res = super().default_get(fields_list)
        
        project_id = self.env.context.get('default_project_id')
        if project_id:
            res['project_id'] = project_id
            
        return res
    
    def action_load_images(self):
        """Load images from Arkite"""
        self.ensure_one()
        
        if not self.project_id.arkite_project_id:
            self.write({
                'state': 'error',
                'error_message': 'Project is not linked to Arkite.'
            })
            return
        
        try:
            # Get credentials
            creds = self.project_id._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception as e:
            self.write({
                'state': 'error',
                'error_message': f'Could not get API credentials: {str(e)}'
            })
            return
        
        try:
            # Fetch images from Arkite
            url = f"{api_base}/projects/{self.project_id.arkite_project_id}/images/"
            params = {"apiKey": api_key}
            
            _logger.info("[ARKITE] Fetching images from: %s", url)
            response = requests.get(url, params=params, verify=False, timeout=20)
            
            if not response.ok:
                self.write({
                    'state': 'error',
                    'error_message': f'Failed to fetch images from Arkite: HTTP {response.status_code}'
                })
                return
            
            images = response.json()
            if not isinstance(images, list):
                images = []
            
            _logger.info("[ARKITE] Fetched %s images", len(images))
            
            # Clear existing lines
            self.image_ids.unlink()
            
            # Create image lines
            from ..services.arkite_client import ArkiteClient
            client = ArkiteClient(api_base=api_base, api_key=api_key, verify_ssl=False, timeout_sec=20)
            
            for img_data in images:
                image_id = str(img_data.get('Id', ''))
                if not image_id or image_id == '0':
                    continue
                
                # Try to download thumbnail
                thumbnail = None
                try:
                    img_bytes = client.download_image_bytes(str(self.project_id.arkite_project_id), image_id)
                    if img_bytes:
                        thumbnail = base64.b64encode(img_bytes)
                except Exception as e:
                    _logger.warning("[ARKITE] Could not download image %s: %s", image_id, e)
                
                # Get image name/description
                name = img_data.get('Name') or img_data.get('FileName') or f'Image {image_id}'
                
                self.env['product_module.arkite.image.selector.line'].create({
                    'wizard_id': self.id,
                    'image_id': image_id,
                    'name': name,
                    'thumbnail': thumbnail,
                })
            
            self.write({'state': 'loaded'})
            
            return {
                'type': 'ir.actions.do_nothing',
            }
            
        except Exception as e:
            _logger.error("[ARKITE] Error loading images: %s", e, exc_info=True)
            self.write({
                'state': 'error',
                'error_message': f'Error loading images: {str(e)}'
            })
            return


class ArkiteImageSelectorLine(models.TransientModel):
    _name = 'product_module.arkite.image.selector.line'
    _description = 'Arkite Image Selector Line'
    _order = 'image_id'
    
    wizard_id = fields.Many2one(
        'product_module.arkite.image.selector.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    
    image_id = fields.Char(
        string='Image ID',
        required=True,
        help='Arkite image ID'
    )
    
    name = fields.Char(
        string='Image Name',
        required=True,
        help='Name or filename of the image'
    )
    
    thumbnail = fields.Binary(
        string='Thumbnail',
        help='Preview thumbnail of the image'
    )
    
    def action_select_image(self):
        """Select this image and assign to material"""
        self.ensure_one()
        
        material_id = self.wizard_id.material_id
        if material_id:
            # Assign image_id to the material
            material_id.write({'image_id': self.image_id})
            
            # Try to download the full image
            success = False
            try:
                creds = self.wizard_id.project_id._get_arkite_credentials()
                from ..services.arkite_client import ArkiteClient
                client = ArkiteClient(
                    api_base=creds['api_base'],
                    api_key=creds['api_key'],
                    verify_ssl=False,
                    timeout_sec=20
                )
                
                img_bytes = client.download_image_bytes(
                    str(self.wizard_id.project_id.arkite_project_id),
                    self.image_id
                )
                
                if img_bytes:
                    material_id.write({'image': base64.b64encode(img_bytes)})
                    success = True
                    
            except Exception as e:
                _logger.warning("[ARKITE] Could not download full image: %s", e)
            
            # Close wizard and show notification
            message = _('Image "%s" (ID: %s) has been assigned to material "%s".') % (self.name, self.image_id, material_id.name)
            if success:
                message += _('\nImage downloaded successfully!')
            else:
                message += _('\nImage ID saved, but download failed. You can try "Fetch Images" later.')
            
            # Return close action with notification
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Image Selected'),
                    'message': message,
                    'type': 'success' if success else 'warning',
                    'sticky': False,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }
        else:
            # No specific material - just show info
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Image Selected'),
                    'message': _('Image ID: %s\nImage Name: %s') % (self.image_id, self.name),
                    'type': 'info',
                    'sticky': True,
                }
            }

