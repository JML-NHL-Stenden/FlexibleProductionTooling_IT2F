from odoo import models, fields, api


class ProductAssemblePage(models.Model):
    _name = 'product_module.page'
    _description = 'Static backend page for Product Assemble'

    # Header/label
    name = fields.Char(default="Management", readonly=True)

    # Product types on this page
    product_type_ids = fields.One2many(
        comodel_name='product_module.type',
        inverse_name='page_id',
        string='Product Jobs'
    )

    # Registered products on this page
    product_ids = fields.One2many(
        comodel_name='product_module.product',
        inverse_name='page_id',
        string='Products'
    )

    # Materials on this page
    material_ids = fields.One2many(
        comodel_name='product_module.material',
        inverse_name='page_id',
        string='Materials'
    )

    # Progress tracking on this page
    progress_ids = fields.One2many(
        comodel_name='product_module.progress',
        inverse_name='page_id',
        string='Progress Tracking'
    )

    # Computed counts for display
    job_count = fields.Integer(string='Job Count', compute='_compute_counts')
    product_count = fields.Integer(string='Product Count', compute='_compute_counts')
    material_count = fields.Integer(string='Material Count', compute='_compute_counts')
    progress_count = fields.Integer(string='Progress Count', compute='_compute_counts')

    # Selected product for Product Details tab
    selected_product_id = fields.Many2one('product_module.product', string='Selected Product')
    selected_product_name = fields.Char(related='selected_product_id.name', string='Product Name')
    selected_product_code = fields.Char(related='selected_product_id.product_code', string='Product Code')
    selected_product_description = fields.Text(related='selected_product_id.description', string='Product Description')
    selected_product_image = fields.Binary(related='selected_product_id.image', string='Product Image')
    selected_product_type_ids = fields.Many2many(related='selected_product_id.product_type_ids', string='Product Jobs')

    @api.depends('product_type_ids', 'product_ids', 'material_ids', 'progress_ids')
    def _compute_counts(self):
        """Compute job, product, material and progress counts for display"""
        for record in self:
            record.job_count = len(record.product_type_ids)
            record.product_count = len(record.product_ids)
            record.material_count = len(record.material_ids)
            record.progress_count = len(record.progress_ids)

    def action_edit_product(self):
        """Open the selected product for editing"""
        if self.selected_product_id:
            return {
                'type': 'ir.actions.act_window',
                'name': 'Edit Product',
                'res_model': 'product_module.product',
                'res_id': self.selected_product_id.id,
                'view_mode': 'form',
                'target': 'new',
            }
        return False

    def action_select_product(self, product_id):
        """Select a product for the Product Details tab"""
        self.selected_product_id = product_id
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_create_product_type(self):
        """Open form to create a new product type/job"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Product Job',
            'res_model': 'product_module.type',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_page_id': self.id,
            }
        }

    def action_create_product(self):
        """Open form to create a new product"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Product',
            'res_model': 'product_module.product',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_page_id': self.id,
            }
        }

    def action_create_material(self):
        """Open form to create a new material"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Material',
            'res_model': 'product_module.material',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_page_id': self.id,
            }
        }

    def action_create_progress(self):
        """Open form to create a new progress tracking item with better defaults"""
        return {
            'type': 'ir.actions.act_window',
            'name': 'Create Workstation',
            'res_model': 'product_module.progress',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_page_id': self.id,
                # Set default name based on workstation count
                'default_name': f'Workstation {self.progress_count + 1}',
            }
        }

    def write(self, vals):
        """Override write to update progress records when processes change"""
        result = super().write(vals)

        if 'instruction_ids' in vals:
            progress_model = self.env['product_module.progress']
            for product in self:
                progress_model.update_progress_from_instruction_change(product.id)

        return result