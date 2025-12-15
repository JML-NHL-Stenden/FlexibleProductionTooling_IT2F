# product_module/models/instruction_form_wizard.py
from odoo import models, fields, api

class InstructionFormWizard(models.TransientModel):
    _name = 'product_module.instruction.form.wizard'
    _description = 'Instruction Form Wizard'

    product_id = fields.Many2one('product_module.product', string='Product', required=True, readonly=True)
    
    # List of steps
    step_ids = fields.One2many('product_module.instruction.form.step', 'wizard_id', string='Steps')
    
    @api.model
    def default_get(self, fields_list):
        """Load existing steps from the product"""
        res = super().default_get(fields_list)
        
        if 'default_product_id' in self.env.context:
            product_id = self.env.context['default_product_id']
            product = self.env['product_module.product'].browse(product_id)
            
            # Load existing instructions as steps
            steps = []
            for instruction in product.instruction_ids:
                steps.append((0, 0, {
                    'sequence': instruction.sequence,
                    'step_title': instruction.title,
                    'step_type': 'numbered_step',  # Default type
                    'step_image': instruction.image,
                }))
            
            if steps:
                res['step_ids'] = steps
        
        return res
    
    def create(self, vals):
        """Override create to immediately save steps to product"""
        wizard = super().create(vals)
        if wizard.step_ids and wizard.product_id:
            wizard._save_steps_to_product()
        return wizard
    
    def write(self, vals):
        """Override write to immediately save steps to product"""
        res = super().write(vals)
        if 'step_ids' in vals and self.product_id:
            self._save_steps_to_product()
        return res
    
    def _save_steps_to_product(self):
        """Helper method to save steps to product instructions"""
        self.ensure_one()
        
        if not self.step_ids:
            return
        
        # Delete existing instructions for this product
        if self.product_id.instruction_ids:
            self.product_id.instruction_ids.unlink()
        
        # Create new instructions from the wizard steps
        instruction_obj = self.env['product_module.instruction']
        for step in self.step_ids.sorted('sequence'):
            instruction_obj.create({
                'product_id': self.product_id.id,
                'sequence': step.sequence,
                'title': step.step_title,
                'process_step': 'timer',  # Default process step
                'image': step.step_image,
            })
    
    def action_save_steps(self):
        """Close the wizard (steps are auto-saved via write method)"""
        self.ensure_one()
        
        # Ensure the last changes are saved
        self._save_steps_to_product()
        
        # Refresh the product instruction count
        if self.product_id:
            self.product_id._compute_instruction_count()
        
        return {'type': 'ir.actions.act_window_close'}


class InstructionFormStep(models.TransientModel):
    _name = 'product_module.instruction.form.step'
    _description = 'Instruction Form Step'
    _order = 'sequence, id'
    
    wizard_id = fields.Many2one('product_module.instruction.form.wizard', string='Wizard', required=True, ondelete='cascade')
    sequence = fields.Integer(string='Sequence', default=10)
    step_title = fields.Char(string='Step Title', required=True)
    step_type = fields.Selection([
        ('numbered_step', 'Numbered Step'),
        ('detection_take', 'Detection: Take'),
        ('detection_place', 'Detection: Place'),
    ], string='Step Type', default='numbered_step', required=True)
    step_image = fields.Binary(string='Step Image', attachment=True)
    step_image_filename = fields.Char(string='Image Filename')

