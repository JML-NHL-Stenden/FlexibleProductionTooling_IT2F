# product_module/models/product_type.py
from odoo import models, fields, api
from odoo.exceptions import UserError


class ProductModuleType(models.Model):
    _name = 'product_module.type'
    _description = 'Product Category'
    _order = 'name, id'

    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    name = fields.Char(string='Category Name', required=True, size=12)
    image = fields.Binary(string='Image', attachment=True)
    description = fields.Text(string='Description', size=250)
    
    # Related products (Many2many relationship)
    product_ids = fields.Many2many('product_module.product', string='Products')
    product_count = fields.Integer(string='Total Variants', compute='_compute_product_count')

    @api.depends('product_ids')
    def _compute_product_count(self):
        """Count number of products for this type"""
        for record in self:
            record.product_count = len(record.product_ids)

    # Note: Variant sequencing is now simplified - products in categories are just counted

    # Input constrains
    @api.constrains('name')
    def _check_name_length(self):
        for record in self:
            if record.name and len(record.name) > 12:
                raise UserError(_('Category Name cannot exceed 12 characters.'))
    
    @api.constrains('description')
    def _check_description_length(self):
        for record in self:
            if record.description and len(record.description) > 250:
                raise UserError(_('Description cannot exceed 250 characters.'))
