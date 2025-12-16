# product_module/models/progress_tracking.py - FIXED VERSION
from odoo import models, fields, api
from odoo.exceptions import UserError

class ProductModuleProgress(models.Model):
    _name = 'product_module.progress'
    _description = 'Unit Progress Tracking'
    _order = 'name'

    # Basic fields
    name = fields.Char(string='Unit Name', required=True)

    # Relationships
    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    product_id = fields.Many2one('product_module.product', string='Product', required=True)

    # Progress tracking
    progress_percentage = fields.Integer(string='Progress %', compute='_compute_progress_percentage', store=True)
    total_steps = fields.Integer(string='Total Processes', compute='_compute_total_steps', store=True)
    completed_steps = fields.Integer(string='Completed Steps', default=0)

    # Display fields for better UX
    product_name = fields.Char(string='Product Name', related='product_id.name', store=True)
    product_code = fields.Char(string='Product Code', related='product_id.product_code', store=True)
    product_image = fields.Binary(string='Product Image', related='product_id.image')
    product_description = fields.Text(string='Product Description', related='product_id.description')
    instruction_count = fields.Integer(string='Process Count', related='product_id.instruction_count')
    
    # Current step information
    current_step_number = fields.Integer(string='Current Step Number', compute='_compute_current_step_info', store=False)
    current_step_title = fields.Char(string='Current Step Title', compute='_compute_current_step_info', store=False)
    current_step_description = fields.Text(string='Current Step Description', compute='_compute_current_step_info', store=False)

    @api.depends('completed_steps', 'total_steps')
    def _compute_progress_percentage(self):
        for record in self:
            if record.total_steps > 0:
                record.progress_percentage = min(100, int((record.completed_steps / record.total_steps) * 100))
            else:
                record.progress_percentage = 0

    @api.depends('product_id', 'product_id.instruction_ids')
    def _compute_total_steps(self):
        """Compute total_steps based on product process count - FIXED VERSION"""
        for record in self:
            if record.product_id and record.product_id.instruction_ids:
                # Always get the current process count from the product
                record.total_steps = len(record.product_id.instruction_ids)
            elif record.product_id:
                record.total_steps = 0
            else:
                record.total_steps = 0

    @api.depends('completed_steps', 'product_id', 'product_id.instruction_ids')
    def _compute_current_step_info(self):
        """Get current step information from product processes"""
        for record in self:
            if not record.product_id or not record.product_id.instruction_ids:
                record.current_step_number = 0
                record.current_step_title = 'No processes available'
                record.current_step_description = 'Add processes to the product'
                continue
                
            # Get sorted processes
            instructions = record.product_id.instruction_ids.sorted('sequence')
            
            if record.completed_steps >= len(instructions):
                # All steps completed
                record.current_step_number = len(instructions)
                record.current_step_title = 'All steps completed'
                record.current_step_description = 'Process is finished'
            else:
                # Get next process to complete (current step)
                current_instruction = instructions[record.completed_steps]
                record.current_step_number = record.completed_steps + 1
                record.current_step_title = current_instruction.title or f'Step {record.completed_steps + 1}'
                # Get the process step label
                process_step_label = dict(current_instruction._fields['process_step'].selection).get(current_instruction.process_step, 'No process step selected')
                record.current_step_description = process_step_label

    @api.constrains('name')
    def _check_name(self):
        for record in self:
            if not record.name:
                raise UserError('Unit Name is required!')

    @api.constrains('completed_steps', 'total_steps')
    def _check_completed_steps(self):
        """Ensure completed steps don't exceed total steps"""
        for record in self:
            if record.total_steps > 0 and record.completed_steps > record.total_steps:
                record.completed_steps = record.total_steps
            elif record.completed_steps < 0:
                record.completed_steps = 0

    @api.onchange('product_id')
    def _onchange_product_id(self):
        """When product changes, reset completed steps and update total steps"""
        for record in self:
            record.completed_steps = 0
            # Force recomputation of total_steps
            record._compute_total_steps()

    def action_mark_complete(self):
        """Mark the current step as complete"""
        for record in self:
            # Always refresh total steps from product first
            record._compute_total_steps()

            if record.total_steps == 0:
                raise UserError('This product has no assembly instructions!')
            elif record.completed_steps < record.total_steps:
                record.completed_steps += 1
            else:
                raise UserError('All steps are already completed!')

    def action_reset_progress(self):
        """Reset progress to zero"""
        for record in self:
            record.completed_steps = 0

    def action_open_product(self):
        """Open the associated product form"""
        self.ensure_one()
        if self.product_id:
            return {
                'type': 'ir.actions.act_window',
                'name': self.product_id.name,
                'res_model': 'product_module.product',
                'res_id': self.product_id.id,
                'view_mode': 'form',
                'target': 'current',
            }

    def write(self, vals):
        """Override write to ensure total_steps is always current"""
        result = super().write(vals)
        # If product is being changed, recompute total_steps for affected records
        if 'product_id' in vals:
            self._compute_total_steps()
        return result

    @api.model
    def create(self, vals):
        """Override create to compute total_steps immediately"""
        record = super().create(vals)
        # Compute total_steps after creation
        record._compute_total_steps()
        return record

    @api.model
    def update_progress_from_instruction_change(self, product_id):
        """Update all progress records when product processes change"""
        if product_id:
            progress_records = self.search([('product_id', '=', product_id)])
            progress_records._compute_total_steps()