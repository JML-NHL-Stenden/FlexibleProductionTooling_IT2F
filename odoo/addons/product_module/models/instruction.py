# product_module/models/instruction.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ProductModuleInstruction(models.Model):
    _name = 'product_module.instruction'
    _description = 'Process for Product'
    _order = 'sequence, id'

    product_id = fields.Many2one(
        'product_module.product', 
        string='Product', 
        ondelete='cascade'
    )
    variant_id = fields.Many2one(
        'product_module.variant',
        string='Variant',
        ondelete='cascade'
    )
    sequence = fields.Integer(string='Step #', default=10, help='Order of process steps')
    title = fields.Char(string='Process Title', required=True, size=250)
    process_step = fields.Selection([
        ('alarm_clock', 'Alarm Clock'),
        ('project_loaded', 'Project Loaded'),
        ('receive_communication', 'Receive Communication'),
        ('timer', 'Timer'),
        ('variable_changed', 'Variable Changed'),
        ('watchdog', 'Watchdog'),
    ], string='Process Steps', default='timer')
    image = fields.Binary(string='Illustration', attachment=True)

    # Input constrains
    @api.constrains('product_id', 'variant_id')
    def _check_parent(self):
        for record in self:
            if not record.product_id and not record.variant_id:
                raise UserError(_('Process must be linked to either a Product or a Variant.'))
            if record.product_id and record.variant_id:
                raise UserError(_('Process cannot be linked to both Product and Variant.'))
    
    @api.constrains('title')
    def _check_title_length(self):
        for record in self:
            if record.title and len(record.title) > 250:
                raise UserError(_('Process Title cannot exceed 250 characters.'))


