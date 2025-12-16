# product_module/models/variant.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io


class ProductModuleVariant(models.Model):
    _name = 'product_module.variant'
    _description = 'Product Variant'
    _order = 'sequence, id'
    
    sequence = fields.Integer(string='Sequence', default=10)
    parent_product_id = fields.Many2one('product_module.product', string='Parent Product', required=True, ondelete='cascade')
    
    # Variant Information (inherited from parent)
    name = fields.Char(string='Variant Name', required=True, size=12)
    product_code = fields.Char(string='Product Code', required=True, size=16)
    description = fields.Text(string='Product Description', size=250)
    image = fields.Binary(string='Image', attachment=True)
    
    # Jobs and Materials (can be different from parent)
    product_type_ids = fields.Many2many('product_module.type', string='Product Jobs', help='Select multiple jobs for this variant')
    material_ids = fields.Many2many('product_module.material', string='Materials', help='Materials used in this variant')
    
    # Processes (can be different from parent)
    instruction_ids = fields.One2many('product_module.instruction', 'variant_id', string='Processes')
    instruction_count = fields.Integer(string='Process Count', compute='_compute_instruction_count')
    
    # QR Code fields (computed based on variant's product_code)
    qr_text = fields.Char(string='QR Text', compute='_compute_qr', store=False)
    qr_image = fields.Binary(string='QR Code', compute='_compute_qr', attachment=True, store=False)
    qr_image_name = fields.Char(string='QR Filename', compute='_compute_qr_filename', store=False)
    
    # Input constraints
    @api.constrains('name')
    def _check_name_length(self):
        for record in self:
            if record.name and len(record.name) > 12:
                raise UserError(_('Name cannot exceed 12 characters.'))
            
    @api.constrains('product_code')
    def _check_code_length(self):
        for record in self:
            if record.product_code and len(record.product_code) > 16:
                raise UserError(_('Product Code cannot exceed 16 characters.'))
            
    @api.constrains('description')
    def _check_description_length(self):
        for record in self:
            if record.description and len(record.description) > 250:
                raise UserError(_('Description cannot exceed 250 characters.'))
    
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
        """Count number of processes for this variant"""
        for record in self:
            record.instruction_count = len(record.instruction_ids)
    
    def name_get(self):
        """Display variant name in dropdown"""
        result = []
        for record in self:
            name = record.name
            result.append((record.id, name))
        return result
    
    def action_download_qr(self):
        """Download QR code as PNG image with variant name"""
        self.ensure_one()

        if not self.product_code:
            raise UserError(_('Please set a product code first to generate QR code.'))

        try:
            import qrcode
            from PIL import Image, ImageDraw, ImageFont
        except ImportError:
            raise UserError(_('QR code generation library not available.'))

        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(self.product_code)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")

        # Create new image with space for text below QR code
        qr_width, qr_height = qr_img.size
        text_height = 80
        total_height = qr_height + text_height

        # Create white background image
        from io import BytesIO
        final_img = Image.new('RGB', (qr_width, total_height), 'white')
        final_img.paste(qr_img, (0, 0))

        # Add variant name text below QR code
        draw = ImageDraw.Draw(final_img)
        text = self.name or 'Variant'

        # Try to use a font, fallback to default if not available
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        except:
            font = ImageFont.load_default()

        # Calculate text position (centered)
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_x = (qr_width - text_width) // 2
        text_y = qr_height + 20

        # Draw text
        draw.text((text_x, text_y), text, fill='black', font=font)

        # Convert to bytes
        img_buffer = BytesIO()
        final_img.save(img_buffer, format='PNG')
        img_bytes = img_buffer.getvalue()
        img_base64 = base64.b64encode(img_bytes)

        # Create attachment
        filename = f"{self.product_code}_variant_qr_code.png"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': img_base64,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'image/png'
        })

        # Return download action
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }


