# product_module/models/arkite_detection_temp.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import os
import logging

_logger = logging.getLogger(__name__)

class ArkiteDetectionTemp(models.TransientModel):
    """Temporary model for displaying detections in list view"""
    _name = 'product_module.arkite.detection.temp'
    _description = 'Arkite Detection (Temporary)'
    _rec_name = 'name'
    _order = 'sequence, id'
    
    wizard_id = fields.Many2one('product_module.arkite.job.step.wizard', string='Wizard', required=True, ondelete='cascade')
    detection_id = fields.Char(string='Detection ID', readonly=True, help='Arkite Detection ID (auto-filled when loaded from Arkite)')
    name = fields.Char(string='Name', required=True)
    detection_type = fields.Selection([
        ('OBJECT', 'Object'),
        ('TOOL', 'Tool'),
        ('ACTIVITY', 'Activity'),
        ('PICKING_BIN', 'Picking Bin'),
        ('VIRTUAL_BUTTON', 'Virtual Button'),
        ('QUALITY_CHECK', 'Quality Check'),
        ('OBJECT_WITH_QUALITY_CHECK', 'Object with Quality Check'),
        ('GROUP', 'Group'),
    ], string='Detection Type', required=True, default='OBJECT')
    sequence = fields.Integer(string='Sequence', default=10)
    is_job_specific = fields.Boolean(string='Job-Specific', readonly=True, help='True if this detection is job-specific (not project-wide)')
    job_id = fields.Char(string='Job ID', readonly=True, help='Job ID if this detection is job-specific')
    
    @api.model
    def create(self, vals):
        """Override create to create detection in Arkite if detection_id is empty (new detection)"""
        # If detection_id is provided, it's a loaded detection - just create the record
        if vals.get('detection_id'):
            return super().create(vals)
        
        # Otherwise, create a new detection in Arkite
        wizard = self.env['product_module.arkite.job.step.wizard'].browse(vals.get('wizard_id'))
        if not wizard or not wizard.project_id:
            raise UserError("Please load a project first (Step 1)")
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        # Build detection payload
        detection_data = {
            "Name": vals.get('name', 'Unnamed Detection'),
            "DetectionType": vals.get('detection_type', 'OBJECT'),
        }
        
        # Add JobId if job-specific (for now, we'll create project-wide detections)
        # TODO: Add UI to specify if detection should be job-specific
        
        url = f"{api_base}/projects/{wizard.project_id}/detections/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        _logger.info("[ARKITE] Creating detection: %s", detection_data)
        
        try:
            response = requests.post(url, params=params, headers=headers, json=[detection_data], verify=False, timeout=10)
        except Exception as e:
            _logger.error("[ARKITE] ERROR creating detection: %s", e, exc_info=True)
            raise UserError(f"Failed to create detection: {str(e)}")
        
        _logger.info("[ARKITE] POST /projects/{id}/detections/ STATUS: %s", response.status_code)
        
        if not response.ok:
            error_text = response.text[:500] if response.text else "Unknown error"
            _logger.error("[ARKITE] Server refused request: %s", error_text)
            raise UserError(f"Failed to create detection: HTTP {response.status_code}\n{error_text}")
        
        try:
            created_detections = response.json()
            if isinstance(created_detections, list) and created_detections:
                created = created_detections[0]
                vals['detection_id'] = str(created.get("Id", ""))
                _logger.info("[ARKITE] Created detection with ID: %s", vals['detection_id'])
            else:
                # API might return single object instead of list
                if isinstance(created_detections, dict):
                    vals['detection_id'] = str(created_detections.get("Id", ""))
                else:
                    raise UserError("Unexpected response format from Arkite API")
        except Exception as e:
            _logger.error("[ARKITE] Error parsing detection creation response: %s", e)
            raise UserError(f"Failed to parse detection creation response: {str(e)}")
        
        return super().create(vals)
    
    def write(self, vals):
        """Override write to update detection in Arkite if name or type changes"""
        result = super().write(vals)
        
        # Only update in Arkite if name or detection_type changed and detection_id exists
        if not self.detection_id:
            return result
        
        fields_to_sync = ['name', 'detection_type']
        if not any(field in vals for field in fields_to_sync):
            return result
        
        wizard = self.wizard_id
        if not wizard or not wizard.project_id:
            return result
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            return result
        
        # Build update payload
        update_data = {}
        if 'name' in vals:
            update_data["Name"] = vals['name']
        if 'detection_type' in vals:
            update_data["DetectionType"] = vals['detection_type']
        
        if not update_data:
            return result
        
        url = f"{api_base}/projects/{wizard.project_id}/detections/{self.detection_id}/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        _logger.info("[ARKITE] Updating detection %s: %s", self.detection_id, update_data)
        
        try:
            response = requests.patch(url, params=params, headers=headers, json=update_data, verify=False, timeout=10)
            if not response.ok:
                _logger.warning("[ARKITE] Failed to update detection: HTTP %s, %s", response.status_code, response.text[:200])
        except Exception as e:
            _logger.warning("[ARKITE] Error updating detection: %s", e)
        
        return result
    
    def unlink(self):
        """Override unlink to delete detection from Arkite"""
        for record in self:
            if record.detection_id:
                wizard = record.wizard_id
                if wizard and wizard.project_id:
                    api_base = os.getenv('ARKITE_API_BASE')
                    api_key = os.getenv('ARKITE_API_KEY')
                    
                    if api_base and api_key:
                        url = f"{api_base}/projects/{wizard.project_id}/detections/{record.detection_id}/"
                        params = {"apiKey": api_key}
                        
                        try:
                            response = requests.delete(url, params=params, verify=False, timeout=10)
                            if response.ok:
                                _logger.info("[ARKITE] Deleted detection %s", record.detection_id)
                            else:
                                _logger.warning("[ARKITE] Failed to delete detection: HTTP %s", response.status_code)
                        except Exception as e:
                            _logger.warning("[ARKITE] Error deleting detection: %s", e)
        
        return super().unlink()
