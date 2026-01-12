# product_module/models/arkite_process_create_wizard.py
from odoo import models, fields, _
from odoo.exceptions import UserError
import requests
import logging

_logger = logging.getLogger(__name__)


class ArkiteProcessCreateWizard(models.TransientModel):
    _name = 'product_module.arkite.process.create.wizard'
    _description = 'Create Arkite Process (Wizard)'

    project_id = fields.Many2one('product_module.project', required=True, ondelete='cascade')

    mode = fields.Selection([
        ('create', 'Create (Blank)'),
        ('duplicate', 'Duplicate Existing'),
    ], default='create', required=True)

    name = fields.Char(string='Process Name', required=True, default='New Process')
    comment = fields.Text(string='Comment')

    template_process_id = fields.Many2one(
        'product_module.arkite.process.temp',
        string='Template Process',
        help='Process to duplicate (required for Duplicate mode).'
    )

    def action_confirm(self):
        self.ensure_one()
        if not self.project_id or not self.project_id.arkite_project_id:
            raise UserError(_("Please link to an Arkite project first."))

        try:
            creds = self.project_id._get_arkite_credentials()
            api_base = creds['api_base']
            api_key = creds['api_key']
        except Exception:
            raise UserError(_('Could not get API credentials. Please check your Arkite unit configuration.'))

        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        arkite_project_id = self.project_id.arkite_project_id

        if self.mode == 'create':
            # IMPORTANT: This Arkite server requires an 'Id' field in the DTO. Using 0 works.
            url = f"{api_base}/projects/{arkite_project_id}/processes/"
            payload = [{
                "Type": "Process",
                "Id": 0,
                "Name": (self.name or "New Process").strip(),
                "Comment": (self.comment or ""),
            }]
            _logger.info("[ARKITE] Creating process via POST /processes/ name=%s", payload[0]["Name"])
            resp = requests.post(url, params=params, json=payload, headers=headers, verify=False, timeout=10)
            if not resp.ok:
                raise UserError(_("Failed to create process: HTTP %s\n%s") % (resp.status_code, (resp.text or "")[:500]))

            created = resp.json()
            created_proc = created[0] if isinstance(created, list) and created else (created if isinstance(created, dict) else None)
            if not created_proc:
                raise UserError(_("Unexpected response format from Arkite when creating a process."))

            process_id = str(created_proc.get("Id", ""))
            process_name = created_proc.get("Name") or payload[0]["Name"]

            self.project_id.env['product_module.arkite.process.temp'].create({
                'project_id': self.project_id.id,
                'process_id': process_id,
                'name': process_name,
                'comment': created_proc.get("Comment", "") or "",
            })
            self.project_id.write({'selected_process_id_char': process_id, 'selected_arkite_process_id': process_id})
            # Do not navigate/reopen the project form from inside the wizard; just close the modal.
            # The user can click "Load Processes" if they want to refresh the list immediately.
            return {'type': 'ir.actions.act_window_close'}

        # duplicate
        if not self.template_process_id or not self.template_process_id.process_id:
            raise UserError(_("Please choose a template process to duplicate."))

        template_id = str(self.template_process_id.process_id)
        url_dup = f"{api_base}/projects/{arkite_project_id}/processes/{template_id}/duplicate/"
        _logger.info("[ARKITE] Duplicating process %s for project %s", template_id, arkite_project_id)
        resp = requests.post(url_dup, params=params, headers=headers, verify=False, timeout=10)
        if not resp.ok:
            raise UserError(_("Failed to duplicate process: HTTP %s\n%s") % (resp.status_code, (resp.text or "")[:500]))

        created_proc = resp.json() if resp.text else {}
        if not isinstance(created_proc, dict) or not created_proc.get("Id"):
            raise UserError(_("Unexpected response format from Arkite when duplicating a process."))

        process_id = str(created_proc.get("Id", ""))
        process_name = created_proc.get("Name", "New Process")

        self.project_id.env['product_module.arkite.process.temp'].create({
            'project_id': self.project_id.id,
            'process_id': process_id,
            'name': process_name,
            'comment': created_proc.get("Comment", "") or "",
        })
        self.project_id.write({'selected_process_id_char': process_id, 'selected_arkite_process_id': process_id})
        # Do not navigate/reopen the project form from inside the wizard; just close the modal.
        return {'type': 'ir.actions.act_window_close'}

