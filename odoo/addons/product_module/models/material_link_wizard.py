# product_module/models/material_link_wizard.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class MaterialLinkWizard(models.TransientModel):
    _name = 'product_module.material.link.wizard'
    _description = 'Link Materials to Project Wizard'
    
    project_id = fields.Many2one(
        'product_module.project',
        string='Project',
        required=True,
        readonly=True
    )
    material_ids = fields.Many2many(
        'product_module.material',
        'material_link_wizard_rel',
        'wizard_id',
        'material_id',
        string='Materials to Link',
        domain="['|', ('project_id', '=', False), ('project_id', '!=', project_id)]"
    )
    
    @api.model
    def default_get(self, fields_list):
        """Set default project from context"""
        res = super().default_get(fields_list)
        if 'active_id' in self.env.context:
            res['project_id'] = self.env.context['active_id']
        return res
    
    def action_link_materials(self):
        """Link selected materials to the project"""
        self.ensure_one()
        if not self.material_ids:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Materials Selected'),
                    'message': _('Please select at least one material to link.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        linked_count = 0
        for material in self.material_ids:
            if material.project_id != self.project_id:
                material.write({
                    'project_id': self.project_id.id,
                    'page_id': self.project_id.page_id.id if self.project_id.page_id else material.page_id,
                })
                linked_count += 1
        
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
