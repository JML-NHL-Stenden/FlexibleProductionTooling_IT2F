from odoo import models, _
from odoo.exceptions import UserError


class ProductModuleProjectHierarchySave(models.Model):
    _inherit = 'product_module.project'

    def _arkite_sync_all_staged_hierarchies(self):
        """Push any staged hierarchy changes (job + process steps) to Arkite."""
        self.ensure_one()
        if not self.arkite_project_id:
            return

        # Only sync what the user actually loaded/edited.
        if getattr(self, 'arkite_job_steps_loaded', False) and getattr(self, 'arkite_job_steps_dirty', False):
            try:
                self.env['product_module.arkite.job.step'].with_context(default_project_id=self.id).pm_action_save_all()
            except Exception as e:
                raise UserError(_("Failed to sync Job Steps to Arkite:\n%s") % str(e))

        if getattr(self, 'arkite_process_steps_loaded', False) and getattr(self, 'arkite_process_steps_dirty', False):
            process_ids = self.env['product_module.arkite.process.step'].search([
                ('project_id', '=', self.id),
                ('process_id', '!=', False),
            ]).mapped('process_id')

            for pid in sorted(set(process_ids)):
                try:
                    self.env['product_module.arkite.process.step'].with_context(
                        default_project_id=self.id,
                        default_process_id=pid,
                    ).pm_action_save_all()
                except Exception as e:
                    raise UserError(_("Failed to sync Process Steps to Arkite (Process %s):\n%s") % (pid, str(e)))

    def write(self, vals):
        """Optionally push staged hierarchy changes on Project save."""
        res = super().write(vals)

        # Avoid recursion / side effects
        if self.env.context.get('skip_arkite_hierarchy_autosync'):
            return res

        for project in self:
            if project.arkite_project_id and project.arkite_hierarchy_dirty:
                project._arkite_sync_all_staged_hierarchies()
                # Clear dirty flags directly (avoid calling write() again and triggering other sync logic).
                self.env.cr.execute(
                    "UPDATE product_module_project "
                    "SET arkite_hierarchy_dirty = FALSE, arkite_job_steps_dirty = FALSE, arkite_process_steps_dirty = FALSE "
                    "WHERE id = %s",
                    [project.id],
                )

        if self:
            self.invalidate_recordset(['arkite_hierarchy_dirty', 'arkite_job_steps_dirty', 'arkite_process_steps_dirty'])
        return res
