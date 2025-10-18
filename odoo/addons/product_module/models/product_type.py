# product_module/models/product_type.py
from odoo import models, fields, api


class ProductModuleType(models.Model):
    _name = 'product_module.type'
    _description = 'Product Category'
    _order = 'name, id'

    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    name = fields.Char(string='Category Name', required=True)
    image = fields.Binary(string='Image', attachment=True)
    description = fields.Text(string='Description')
    
    # Related products (Many2many relationship)
    product_ids = fields.Many2many('product_module.product', string='Products')
    product_count = fields.Integer(string='Total Variants', compute='_compute_product_count')

    @api.depends('product_ids')
    def _compute_product_count(self):
        """Count number of products for this type"""
        for record in self:
            record.product_count = len(record.product_ids)

    # Note: Variant sequencing is now simplified - products in categories are just counted