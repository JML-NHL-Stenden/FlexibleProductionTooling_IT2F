# product_module/models/material.py
from odoo import models, fields, api

class ProductModuleMaterial(models.Model):
    _name = 'product_module.material'
    _description = 'Product Material'
    _order = 'name, id'

    # Basic fields
    name = fields.Char(string='Material Name', required=True)
    material_type = fields.Char(string='Material Type', required=True)
    image = fields.Binary(string='Image', attachment=True)

    # Relationships
    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    product_ids = fields.Many2many(
        'product_module.product',
        string='Used in Products',
        help='Products that use this material'
    )
    product_type_ids = fields.Many2many(
        'product_module.type',
        string='Used in Categories',
        help='Categories that use this material'
    )

    # Computed fields
    usage_count = fields.Integer(
        string='Usage Count',
        compute='_compute_usage_count',
        help='Number of products using this material'
    )

    @api.depends('product_ids')
    def _compute_usage_count(self):
        """Compute number of products using this material"""
        for record in self:
            record.usage_count = len(record.product_ids)

