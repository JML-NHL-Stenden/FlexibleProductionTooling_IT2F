# product_module/models/product.py
from odoo import models, fields, api
import base64
import io


class ProductModuleProduct(models.Model):
    _name = 'product_module.product'
    _description = 'Registered Product for Assembly'
    _order = 'sequence, id'
    
    sequence = fields.Integer(string='Sequence', default=10)
    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    product_type_ids = fields.Many2many('product_module.type', string='Product Categories', help='Select multiple categories for this product')

    # Product Information
    name = fields.Char(string='Product Name', required=True)
    product_code = fields.Char(string='Product Code', required=True)
    variant = fields.Char(string='Variant')
    description = fields.Text(string='Product Description')
    image = fields.Binary(string='Image', attachment=True)

    # QR Code fields
    qr_text = fields.Char(string='QR Text', compute='_compute_qr', store=False)
    qr_image = fields.Binary(string='QR Code', compute='_compute_qr', attachment=True, store=False)
    qr_image_name = fields.Char(string='QR Filename', compute='_compute_qr_filename', store=False)

    # Note: Variant sequence is now handled through the product_type_ids relationship
    
    # Instructions
    instruction_ids = fields.One2many('product_module.instruction', 'product_id', string='Assembly Instructions')
    instruction_count = fields.Integer(string='Instruction Count', compute='_compute_instruction_count')

    @api.depends('product_code')
    def _compute_qr(self):
        """Generate QR code from product_code"""
        for record in self:
            code = (record.product_code or '').strip()
            record.qr_text = code or False
            
            if not code:
                record.qr_image = False
                continue
            
            try:
                import qrcode
            except ImportError:
                # If qrcode lib is missing, skip the image (text still available)
                record.qr_image = False
                continue

            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=2,
            )
            qr.add_data(code)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

            # Convert to binary
            buf = io.BytesIO()
            img.save(buf, format='PNG')
            record.qr_image = base64.b64encode(buf.getvalue())

    @api.depends('product_code')
    def _compute_qr_filename(self):
        """Generate filename for QR code download"""
        for record in self:
            if record.product_code:
                record.qr_image_name = f'qr_{record.product_code}.png'
            else:
                record.qr_image_name = 'qr_code.png'

    @api.depends('instruction_ids')
    def _compute_instruction_count(self):
        """Count number of instructions for this product"""
        for record in self:
            record.instruction_count = len(record.instruction_ids)

    # Note: Sequence assignment is now handled in the product_type model

    def action_select_product(self):
        """Select this product for the Product Details tab"""
        if self.page_id:
            self.page_id.selected_product_id = self.id
            return {
                'type': 'ir.actions.client',
                'tag': 'reload',
            }
        return False

    def action_edit_product(self):
        """Open this product for editing"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Edit Product',
            'res_model': 'product_module.product',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }


