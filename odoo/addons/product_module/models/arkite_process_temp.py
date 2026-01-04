# product_module/models/arkite_process_temp.py
from odoo import models, fields, api, _

class ArkiteProcessTemp(models.TransientModel):
    """Temporary model for process selection"""
    _name = 'product_module.arkite.process.temp'
    _description = 'Arkite Process (Temporary)'
    _rec_name = 'name'
    
    wizard_id = fields.Many2one('product_module.arkite.job.step.wizard', string='Wizard', ondelete='cascade')
    job_id = fields.Many2one('product_module.type', string='Job', ondelete='cascade')
    project_id = fields.Many2one('product_module.project', string='Project', ondelete='cascade')
    process_id = fields.Char(string='Process ID', required=True)
    name = fields.Char(string='Name', required=True)
    process_name = fields.Char(string='Process Name', related='name', store=False)
    comment = fields.Text(string='Comment')
    
    def action_select_process(self):
        """Select this process and automatically load its steps"""
        self.ensure_one()
        if self.project_id:
            # Set both selected process fields to keep them in sync
            self.project_id.write({
                'selected_arkite_process_id': self.process_id,
                'selected_process_id_char': self.process_id
            })
            
            # Invalidate cache to force recomputation
            self.project_id.invalidate_recordset(['selected_arkite_process_name', 'arkite_process_ids', 'arkite_process_step_ids'])
            
            # Commit the selection immediately
            self.env.cr.commit()
            
            # Automatically load steps for the selected process
            try:
                # Load steps - this will create the step records
                self.project_id.action_load_process_steps()
                # Return empty - JavaScript will handle the refresh
                return {}
            except Exception as e:
                # If loading fails, still return empty to avoid reload
                return {}
        return False
