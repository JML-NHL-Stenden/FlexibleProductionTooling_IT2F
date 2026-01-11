# product_module/models/arkite_process_temp.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)

class ArkiteProcessTemp(models.TransientModel):
    """Temporary model for process selection"""
    _name = 'product_module.arkite.process.temp'
    _description = 'Arkite Process (Temporary)'
    _rec_name = 'name'
    
    wizard_id = fields.Many2one('product_module.arkite.job.step.wizard', string='Wizard', ondelete='cascade')
    job_id = fields.Many2one('product_module.type', string='Job', ondelete='cascade')
    project_id = fields.Many2one('product_module.project', string='Project', ondelete='cascade')
    process_id = fields.Char(string='Process ID', required=True)
    name = fields.Char(string='Name', required=True)
    process_name = fields.Char(string='Process Name', related='name', store=False)
    comment = fields.Text(string='Comment')
    
    def action_select_process(self):
        """Select this process and automatically load its steps"""
        self.ensure_one()
        if self.project_id:
            # Set both selected process fields to keep them in sync
            self.project_id.write({
                'selected_arkite_process_id': self.process_id,
                'selected_process_id_char': self.process_id
            })
            
            # Invalidate cache to force recomputation
            self.project_id.invalidate_recordset(['selected_arkite_process_name', 'arkite_process_ids', 'arkite_process_step_ids'])
            
            # Automatically load steps for the selected process, then reload the form so the UI updates.
            self.project_id.action_load_process_steps()
            # Don't navigate/refresh the whole page.
            return False
        return False

    def action_delete_process(self):
        """Delete this process in Arkite, then refresh the project form list."""
        self.ensure_one()
        if not self.project_id or not self.project_id.arkite_project_id:
            raise UserError(_("Please link to an Arkite project first."))

        try:
            creds = self.project_id._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration.'))

        process_id = str(self.process_id or "")
        if not process_id:
            raise UserError(_("Missing process ID."))

        url = f"{api_base}/projects/{self.project_id.arkite_project_id}/processes/{process_id}/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}

        _logger.info("[ARKITE] Deleting process %s from project %s", process_id, self.project_id.arkite_project_id)
        resp = requests.delete(url, params=params, headers=headers, verify=False, timeout=10)
        if not resp.ok and resp.status_code != 204:
            raise UserError(_("Failed to delete process: HTTP %s\n%s") % (resp.status_code, (resp.text or "")[:500]))

        # If we deleted the currently selected process, clear selection.
        if self.project_id.selected_process_id_char == process_id or self.project_id.selected_arkite_process_id == process_id:
            self.project_id.write({'selected_process_id_char': False, 'selected_arkite_process_id': False})

        # Remove this line locally so the list updates without any page refresh.
        self.unlink()
        return False
