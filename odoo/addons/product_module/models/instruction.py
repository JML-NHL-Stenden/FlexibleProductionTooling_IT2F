# product_module/models/instruction.py
from odoo import models, fields


class ProductModuleInstruction(models.Model):
    _name = 'product_module.instruction'
    _description = 'Assembly Instruction for Product'
    _order = 'sequence, id'

    product_id = fields.Many2one(
        'product_module.product', 
        string='Product', 
        required=True, 
        ondelete='cascade'
    )
    sequence = fields.Integer(string='Step #', default=10, help='Order of assembly steps')
    title = fields.Char(string='Step Title', required=True)
    description = fields.Text(string='Instructions')
    image = fields.Binary(string='Illustration', attachment=True)


