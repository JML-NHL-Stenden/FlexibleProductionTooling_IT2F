from odoo import models, _
from odoo.exceptions import UserError


class ProductModuleProjectHierarchySave(models.Model):
    _inherit = "product_module.project"

    def action_sync_staged_hierarchy_to_arkite(self):
        """Explicit UI action: sync staged hierarchy changes to Arkite and show a toast."""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_("Please link to an Arkite project first."))

        # Refresh dirty flags (they can be set via SQL in step.write()).
        self.invalidate_recordset(
            ["arkite_hierarchy_dirty", "arkite_job_steps_dirty", "arkite_process_steps_dirty"]
        )
        self.read(["arkite_hierarchy_dirty", "arkite_job_steps_dirty", "arkite_process_steps_dirty"])

        if not getattr(self, "arkite_hierarchy_dirty", False):
            return {
                "type": "ir.actions.client",
                "tag": "display_notification",
                "params": {
                    "title": _("No changes"),
                    "message": _("No staged hierarchy changes to sync."),
                    "type": "info",
                    "sticky": False,
                },
            }

        self._arkite_sync_all_staged_hierarchies()

        # Clear dirty flags directly (avoid calling write() again and triggering other sync logic).
        self.env.cr.execute(
            "UPDATE product_module_project "
            "SET arkite_hierarchy_dirty = FALSE, arkite_job_steps_dirty = FALSE, arkite_process_steps_dirty = FALSE "
            "WHERE id = %s",
            [self.id],
        )
        self.invalidate_recordset(
            ["arkite_hierarchy_dirty", "arkite_job_steps_dirty", "arkite_process_steps_dirty"]
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Saved"),
                "message": _("Synced staged hierarchy changes to Arkite."),
                "type": "success",
                "sticky": False,
            },
        }

    def _arkite_sync_all_staged_hierarchies(self):
        """Push any staged hierarchy changes (job + process steps) to Arkite.

        IMPORTANT: Do not gate on "*_loaded" flags here. If the user managed to stage
        changes (dirty flags), we should attempt to sync them.
        """
        self.ensure_one()
        if not self.arkite_project_id:
            return

        # Job steps: sync all for project (only if staged)
        if getattr(self, "arkite_job_steps_dirty", False):
            try:
                self.env["product_module.arkite.job.step"].with_context(
                    default_project_id=self.id
                ).pm_action_save_all()
            except Exception as e:
                raise UserError(_("Failed to sync Job Steps to Arkite:\n%s") % str(e))

        # Process steps: sync per process_id (only if staged)
        if getattr(self, "arkite_process_steps_dirty", False):
            process_ids = (
                self.env["product_module.arkite.process.step"]
                .search([("project_id", "=", self.id), ("process_id", "!=", False)])
                .mapped("process_id")
            )
            for pid in sorted(set(process_ids)):
                try:
                    self.env["product_module.arkite.process.step"].with_context(
                        default_project_id=self.id,
                        default_process_id=pid,
                    ).pm_action_save_all()
                except Exception as e:
                    raise UserError(
                        _("Failed to sync Process Steps to Arkite (Process %s):\n%s")
                        % (pid, str(e))
                    )

    def write(self, vals):
        """Autosync staged hierarchy changes when the Project itself is saved."""
        res = super().write(vals)

        # Avoid recursion / side effects
        if self.env.context.get("skip_arkite_hierarchy_autosync"):
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
            self.invalidate_recordset(
                ["arkite_hierarchy_dirty", "arkite_job_steps_dirty", "arkite_process_steps_dirty"]
            )
        return res
