# product_module/models/product.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io
import csv
from io import StringIO, BytesIO


class ProductModuleProduct(models.Model):
    _name = 'product_module.product'
    _description = 'Registered Product for Assembly'
    _order = 'sequence, id'
    
    sequence = fields.Integer(string='Sequence', default=10)
    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    product_type_ids = fields.Many2many('product_module.type', string='Product Categories', help='Select multiple categories for this product')

    # Product Information
    name = fields.Char(string='Product Name', required=True, size=12)
    product_code = fields.Char(string='Product Code', required=True, size=16)
    variant = fields.Char(string='Variant', size=3)
    description = fields.Text(string='Product Description', size=250)
    image = fields.Binary(string='Image', attachment=True)

    # QR Code fields
    qr_text = fields.Char(string='QR Text', compute='_compute_qr', store=False)
    qr_image = fields.Binary(string='QR Code', compute='_compute_qr', attachment=True, store=False)
    qr_image_name = fields.Char(string='QR Filename', compute='_compute_qr_filename', store=False)

    # Components relationship
    component_ids = fields.Many2many('product_module.component', string='Components', help='Components used in this product')

    # Note: Variant sequence is now handled through the product_type_ids relationship

    # Instructions
    instruction_ids = fields.One2many('product_module.instruction', 'product_id', string='Assembly Instructions')
    instruction_count = fields.Integer(string='Instruction Count', compute='_compute_instruction_count')

    # Input constrains
    @api.constrains('name')
    def _check_name_length(self):
        for record in self:
            if record.name and len(record.name) > 12:
                raise UserError(_('Name cannot exceed 24 characters.'))
            
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

    # ...
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

    def action_import_instructions(self):
        """Open wizard to import instructions from CSV"""
        self.ensure_one()
        if not self.id:
            raise UserError(_('Please save the product first before importing instructions.'))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Import Instructions',
            'res_model': 'product_module.instruction.import.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_product_id': self.id}
        }

    def action_download_qr(self):
        """Download QR code as PNG image with product name"""
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
        final_img = Image.new('RGB', (qr_width, total_height), 'white')
        final_img.paste(qr_img, (0, 0))

        # Add product name text below QR code
        draw = ImageDraw.Draw(final_img)
        text = self.name or 'Product'

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
        filename = f"{self.product_code}_qr_code.png"
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

    def action_export_instructions(self):
        """Export product info and instructions to CSV file"""
        # Create CSV in memory
        output = StringIO()
        writer = csv.writer(output)

        # Write header with product info
        writer.writerow(['Product Name', 'Product Code', 'Step #', 'Title', 'Description'])

        # Write instruction data with product info in each row
        for instruction in self.instruction_ids.sorted(key=lambda r: r.sequence):
            writer.writerow([
                self.name or '',
                self.product_code or '',
                instruction.sequence,
                instruction.title or '',
                instruction.description or ''
            ])

        # Get CSV content
        csv_data = output.getvalue()
        output.close()

        # Encode to base64
        csv_bytes = csv_data.encode('utf-8')
        csv_base64 = base64.b64encode(csv_bytes)

        # Create attachment
        filename = f"{self.name or 'product'}_instructions.csv"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': csv_base64,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'text/csv'
        })

        # Return download action
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

