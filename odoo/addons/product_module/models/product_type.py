# product_module/models/product_type.py
from odoo import models, fields, api


class ProductModuleType(models.Model):
    _name = 'product_module.type'
    _description = 'Product Type/Category'
    _order = 'name, id'

    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    name = fields.Char(string='Type Name', required=True)
    image = fields.Binary(string='Image', attachment=True)
    description = fields.Text(string='Description')
    
    # Related products
    product_ids = fields.One2many('product_module.product', 'product_type_id', string='Products')
    product_count = fields.Integer(string='Total Variants', compute='_compute_product_count')

    @api.depends('product_ids')
    def _compute_product_count(self):
        """Count number of products for this type"""
        for record in self:
            record.product_count = len(record.product_ids)
