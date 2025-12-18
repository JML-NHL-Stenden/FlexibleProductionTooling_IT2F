# product_module/models/arkite_process_temp.py
from odoo import models, fields, api, _

class ArkiteProcessTemp(models.TransientModel):
    """Temporary model for process selection"""
    _name = 'product_module.arkite.process.temp'
    _description = 'Arkite Process (Temporary)'
    _rec_name = 'name'
    
    wizard_id = fields.Many2one('product_module.arkite.job.step.wizard', string='Wizard', ondelete='cascade')
    process_id = fields.Char(string='Process ID', required=True)
    name = fields.Char(string='Name', required=True)
    comment = fields.Text(string='Comment')
