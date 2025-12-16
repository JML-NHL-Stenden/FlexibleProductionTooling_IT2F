# product_module/models/product.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError

import base64
import io
import csv
import os
import json
from datetime import datetime, timezone
from io import StringIO, BytesIO


class ProductModuleProduct(models.Model):
    _name = 'product_module.product'
    _description = 'Registered Product for Assembly'
    _order = 'sequence, id'

    sequence = fields.Integer(string='Sequence', default=10)
    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    product_type_ids = fields.Many2many(
        'product_module.type',
        string='Product Jobs',
        help='Select multiple jobs for this product'
    )

    # Product Information
    name = fields.Char(string='Product Name', required=True, size=12)
    product_code = fields.Char(string='Product Code', required=True, size=16)
    description = fields.Text(string='Product Description', size=250)
    image = fields.Binary(string='Image', attachment=True)

    # QR Code fields
    qr_text = fields.Char(string='QR Text', compute='_compute_qr', store=False)
    qr_image = fields.Binary(string='QR Code', compute='_compute_qr', attachment=True, store=False)
    qr_image_name = fields.Char(string='QR Filename', compute='_compute_qr_filename', store=False)

    # Materials relationship
    material_ids = fields.Many2many(
        'product_module.material',
        string='Materials',
        help='Materials used in this product'
    )

    # Processes
    instruction_ids = fields.One2many('product_module.instruction', 'product_id', string='Processes')
    instruction_count = fields.Integer(string='Process Count', compute='_compute_instruction_count')

    # -------------------------
    # Input constraints
    # -------------------------
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

    # -------------------------
    # QR generation
    # -------------------------
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
                record.qr_image = False
                continue

            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=2,
            )
            qr.add_data(code)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")

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
        """Count number of processes for this product"""
        for record in self:
            record.instruction_count = len(record.instruction_ids)

    # -------------------------
    # Helpers: MQTT publishing
    # -------------------------
    def _get_mqtt_config(self):
        """
        Pull config from environment first (works great in Docker),
        fallback to Odoo system params if you want to configure via UI later.
        """
        ICP = self.env['ir.config_parameter'].sudo()

        host = os.getenv("MQTT_HOST") or ICP.get_param("product_module.mqtt_host") or "mqtt"
        port = os.getenv("MQTT_PORT") or ICP.get_param("product_module.mqtt_port") or "1883"
        topic = os.getenv("MQTT_TOPIC_QR") or ICP.get_param("product_module.mqtt_topic_qr") or "arkite/trigger/QR"

        try:
            port = int(port)
        except Exception:
            port = 1883

        return host, port, topic

    def _publish_qr_trigger_to_mqtt(self):
        """
        Publish the same payload shape your existing Windows Arkite Agent expects:
        {
          "timestamp": "...",
          "count": 1,
          "items": [{"product_name": "...", "product_code": "...", "qr_text": "..."}],
          "source": {...}
        }
        """
        self.ensure_one()

        try:
            import paho.mqtt.client as mqtt
        except Exception as e:
            raise UserError(_(
                "Missing Python dependency for MQTT in Odoo (paho-mqtt).\n"
                "Install it in your Odoo container, e.g.:\n"
                "  pip3 install paho-mqtt\n\n"
                "Original error: %s"
            ) % (str(e),))

        mqtt_host, mqtt_port, mqtt_topic = self._get_mqtt_config()

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": 1,
            "items": [
                {
                    "product_name": self.name,
                    "product_code": self.product_code,
                    # IMPORTANT: your agent only needs qr_text to exist to trigger
                    # (and your trigger script uses the scanned code as qr_text)
                    "qr_text": (self.product_code or "").strip(),
                }
            ],
            "source": {
                "origin": "odoo-product-module",
                "action": "action_start_project",
                "model": self._name,
                "res_id": self.id,
            },
        }

        client = mqtt.Client(client_id=f"odoo-start-project-{self.id}", protocol=mqtt.MQTTv5)
        try:
            client.connect(mqtt_host, mqtt_port, keepalive=30)
            client.publish(mqtt_topic, json.dumps(payload), qos=0, retain=False)
            client.disconnect()
        except Exception as e:
            raise UserError(_(
                "MQTT publish failed.\n"
                "Host: %s\nPort: %s\nTopic: %s\n\nError: %s"
            ) % (mqtt_host, mqtt_port, mqtt_topic, str(e)))

        return payload, mqtt_host, mqtt_port, mqtt_topic

    # -------------------------
    # Existing actions
    # -------------------------
    def action_create_variant(self):
        """Open instruction form with two windows side by side"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Instruction Form',
            'res_model': 'product_module.instruction.form.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_product_id': self.id,
            }
        }

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
        """Open wizard to import processes from CSV"""
        self.ensure_one()
        if not self.id:
            raise UserError(_('Please save the product first before importing processes.'))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Import Processes',
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

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(self.product_code)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")

        qr_width, qr_height = qr_img.size
        text_height = 80
        total_height = qr_height + text_height

        final_img = Image.new('RGB', (qr_width, total_height), 'white')
        final_img.paste(qr_img, (0, 0))

        draw = ImageDraw.Draw(final_img)
        text = self.name or 'Product'

        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        except Exception:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_x = (qr_width - text_width) // 2
        text_y = qr_height + 20

        draw.text((text_x, text_y), text, fill='black', font=font)

        img_buffer = BytesIO()
        final_img.save(img_buffer, format='PNG')
        img_bytes = img_buffer.getvalue()
        img_base64 = base64.b64encode(img_bytes)

        filename = f"{self.product_code}_qr_code.png"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': img_base64,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'image/png'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_start_project(self):
        """
        Start Arkite project for this product by publishing a QR-trigger payload to MQTT.

        This is the “same trigger” your Windows scripts already use:
        - arkite_agent.py opens/logs into Arkite when it receives a message
        - bridge.py can also act on it (duplicate/load template)
        """
        self.ensure_one()

        if not self.name:
            raise UserError(_('Please set a product name first.'))
        if not self.product_code:
            raise UserError(_('Please set a product code first.'))

        payload, host, port, topic = self._publish_qr_trigger_to_mqtt()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Run in Arkite'),
                'message': _(
                    'Published QR trigger to MQTT.\nHost=%s Port=%s Topic=%s\n\nProduct: %s (%s)'
                ) % (host, port, topic, self.name, self.product_code),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_export_instructions(self):
        """Export product info and processes to CSV file"""
        output = StringIO()
        writer = csv.writer(output)

        writer.writerow(['Product Name', 'Product Code', 'Step #', 'Process Title', 'Process Steps'])

        for instruction in self.instruction_ids.sorted(key=lambda r: r.sequence):
            writer.writerow([
                self.name or '',
                self.product_code or '',
                instruction.sequence,
                instruction.title or '',
                dict(instruction._fields['process_step'].selection).get(instruction.process_step, '') or ''
            ])

        csv_data = output.getvalue()
        output.close()

        csv_bytes = csv_data.encode('utf-8')
        csv_base64 = base64.b64encode(csv_bytes)

        filename = f"{self.name or 'product'}_processes.csv"
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': csv_base64,
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'text/csv'
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
