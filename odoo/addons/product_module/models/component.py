# product_module/models/component.py
from odoo import models, fields, api

class ProductModuleComponent(models.Model):
    _name = 'product_module.component'
    _description = 'Product Component'
    _order = 'name, id'

    # Basic fields
    name = fields.Char(string='Component Name', required=True)
    component_type = fields.Char(string='Component Type', required=True)
    image = fields.Binary(string='Image', attachment=True)

    # Relationships
    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    product_ids = fields.Many2many(
        'product_module.product',
        string='Used in Products',
        help='Products that use this component'
    )
    product_type_ids = fields.Many2many(
        'product_module.type',
        string='Used in Categories',
        help='Categories that use this component'
    )

    # Computed fields
    usage_count = fields.Integer(
        string='Usage Count',
        compute='_compute_usage_count',
        help='Number of products using this component'
    )

    @api.depends('product_ids')
    def _compute_usage_count(self):
        """Compute number of products using this component"""
        for record in self:
            record.usage_count = len(record.product_ids)