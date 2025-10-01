# product_module/models/page.py
from odoo import models, fields
from odoo.exceptions import UserError
import base64
import io
import uuid
from datetime import datetime, timezone

class ProductAssemblePage(models.Model):
    _name = 'product_module.page'
    _description = 'Static backend page for Product Assemble'

    # Tabs: Product Details, QR Code, Create Product Instructions
    # Product Details
    product_name = fields.Char(string="Product Name")
    product_code = fields.Char(string="Product Code")
    product_description = fields.Text(string="Description")

    # Header/labels
    name = fields.Char(default="Product Assemble", readonly=True)

    # QR Code
    qr_text = fields.Char(string="QR Text", readonly=True)
    qr_image = fields.Binary(string="QR Code", readonly=True, attachment=True)
    qr_image_name = fields.Char(string="QR Filename", default="qr.png", readonly=True)

    # Instructions
    instruction_text = fields.Text(string="Product Instructions")

    # Inputs on Name Enterer tab
    first_name_input = fields.Char(string="First Name")
    last_name_input = fields.Char(string="Last Name")

    def action_name_enter_submit(self):
        """Simple hook for the Enter button; extend later as needed."""
        self.ensure_one()
        # no-op for now, but could validate or trigger logic
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_create_qr_code(self):
        """Generate a UNIQUE QR and refresh the same view (no extra breadcrumb)."""
        self.ensure_one()
        try:
            import qrcode  # requires: pip install qrcode[pil]
        except Exception as e:
            raise UserError(
                "Missing Python package(s). Install inside the Odoo container:\n\n"
                "pip install qrcode[pil]\n\nDetails: %s" % e
            )

        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        uniq = uuid.uuid4().hex[:8].upper()
        payload = f"PM-{ts}-{uniq}"

        qr = qrcode.QRCode(box_size=10, border=2)
        qr.add_data(payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format='PNG')
        png_b64 = base64.b64encode(buf.getvalue())

        self.sudo().write({
            'qr_text': payload,
            'qr_image': png_b64,
            'qr_image_name': f'{payload}.png',
        })

        return {'type': 'ir.actions.client', 'tag': 'reload'}
