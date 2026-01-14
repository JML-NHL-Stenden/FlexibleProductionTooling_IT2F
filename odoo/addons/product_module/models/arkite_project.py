# product_module/models/arkite_project.py
from odoo import models, fields


class ArkiteProject(models.Model):
    _name = 'product_module.arkite_project'
    _description = 'Arkite Project'

    product_id = fields.Many2one(
        'product_module.product',
        string='Product',
        required=True,
        ondelete='cascade',
    )

    product_name = fields.Char(string='Product Name')
    product_code = fields.Char(string='Product Code')

    qr_text = fields.Char(string='QR Text')
    qr_image = fields.Binary(string='QR Code')
    qr_image_name = fields.Char(string='QR Filename')
