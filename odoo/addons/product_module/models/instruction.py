# product_module/models/instruction.py
from odoo import models, fields, api
from odoo.exceptions import UserError


class ProductModuleInstruction(models.Model):
    _name = 'product_module.instruction'
    _description = 'Assembly Instruction for Product'
    _order = 'sequence, id'

    arkite_step_id = fields.BigInteger(
        string="Arkite Step ID",
        index=True,
        required=True
    )
    product_id = fields.Many2one(
        'product_module.product', 
        string='Product', 
        required=True, 
        ondelete='cascade'
    )
    sequence = fields.Integer(string='Step #', default=10, help='Order of assembly steps')
    title = fields.Char(string='Step Title', required=True, size=250)
    description = fields.Text(string='Instructions', size=250)
    image = fields.Binary(string='Illustration', attachment=True)

    # Input constrains
    @api.constrains('title')
    def _check_title_length(self):
        for record in self:
            if record.title and len(record.title) > 250:
                raise UserError(_('Step Title cannot exceed 250 characters.'))
            
    @api.constrains('description')
    def _check_description_length(self):
        for record in self:
            if record.description and len(record.description) > 250:
                raise UserError(_('Instructions cannot exceed 250 characters.'))


