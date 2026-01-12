import logging

from odoo import models, _
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class ProductModuleProjectAutoLoadEverything(models.Model):
    _inherit = 'product_module.project'

    def action_load_arkite_project(self):
        """Load Arkite project and auto-load EVERYTHING (process list + all process steps + job steps).

        We intentionally do this here (the explicit "Load Arkite Project" action) instead of on every form open,
        to avoid heavy API calls on each navigation.
        """
        self.ensure_one()
        res = super().action_load_arkite_project()

        # Auto-load process list + all process steps
        try:
            self.action_load_process_list()
            self._action_load_all_process_steps()
        except UserError:
            raise
        except Exception as e:
            _logger.warning("[ARKITE] Auto-load all process steps failed: %s", e, exc_info=True)

        # Job steps are already loaded by super() via action_load_arkite_steps -> action_load_job_steps
        return res

    def _action_load_all_process_steps(self):
        """Load steps for ALL processes into arkite_process_step_ids in one shot."""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_("Please link to an Arkite project first."))

        # Ensure we have a process list
        if not self.arkite_process_ids:
            self.action_load_process_list()

        # Clear existing process steps for this project (local transient only; unlink is SAFE now)
        self.env['product_module.arkite.process.step'].search([('project_id', '=', self.id)]).sudo().unlink()

        # Fetch all steps once
        creds = self._get_arkite_credentials()
        api_base = creds['api_base']
        api_key = creds['api_key']

        import requests
        url_steps = f"{api_base}/projects/{self.arkite_project_id}/steps/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        resp = requests.get(url_steps, params=params, headers=headers, verify=False, timeout=20)
        if not resp.ok:
            raise UserError(_("Failed to fetch steps: HTTP %s") % resp.status_code)

        all_steps = resp.json()
        if not isinstance(all_steps, list):
            raise UserError(_("Unexpected response format for steps"))

        # Only process steps: ProcessId != 0
        process_step_rows = [s for s in all_steps if str(s.get("ProcessId", "")) not in ("", "0")]

        # Group by process id
        steps_by_process = {}
        for s in process_step_rows:
            pid = str(s.get("ProcessId", ""))
            steps_by_process.setdefault(pid, []).append(s)

        # Create all processes' steps (roots first, then children) using the same logic as action_load_process_steps
        Step = self.env['product_module.arkite.process.step']
        for pid, steps in steps_by_process.items():
            steps.sort(key=lambda x: x.get("Index", 0))
            root_steps = [s for s in steps if not s.get("ParentStepId") or str(s.get("ParentStepId", "")) in ("0", "")]
            child_steps = [s for s in steps if s.get("ParentStepId") and str(s.get("ParentStepId", "")) not in ("0", "")]
            root_steps.sort(key=lambda x: x.get("Index", 0))
            child_steps.sort(key=lambda x: x.get("Index", 0))

            step_id_to_record = {}
            for s in root_steps:
                sid = str(s.get("Id", ""))
                name = (s.get("Name") or "").strip() or (f"Step {s.get('Index')}" if s.get("Index") is not None else (f"Step {sid}" if sid else "Unnamed Step"))
                stype = s.get("StepType", "WORK_INSTRUCTION")
                idx = s.get("Index", 0) or 0
                rec = Step.create({
                    'project_id': self.id,
                    'process_id': pid,
                    'step_id': sid,
                    'step_name': name,
                    'step_type': stype,
                    'sequence': idx * 10,
                    'index': idx,
                    'parent_step_id': "",
                    'parent_id': False,
                })
                step_id_to_record[sid] = rec

            remaining = list(child_steps)
            for _ in range(15):
                if not remaining:
                    break
                processed = []
                for s in remaining:
                    sid = str(s.get("Id", ""))
                    psid = str(s.get("ParentStepId", ""))
                    if psid in step_id_to_record:
                        name = (s.get("Name") or "").strip() or (f"Step {s.get('Index')}" if s.get("Index") is not None else (f"Step {sid}" if sid else "Unnamed Step"))
                        stype = s.get("StepType", "WORK_INSTRUCTION")
                        idx = s.get("Index", 0) or 0
                        parent_rec = step_id_to_record[psid]
                        rec = Step.create({
                            'project_id': self.id,
                            'process_id': pid,
                            'step_id': sid,
                            'step_name': name,
                            'step_type': stype,
                            'sequence': idx * 10,
                            'index': idx,
                            'parent_step_id': psid,
                            'parent_id': parent_rec.id,
                        })
                        step_id_to_record[sid] = rec
                        processed.append(s)
                for s in processed:
                    remaining.remove(s)

        # Mark loaded flags (avoid triggering autosync)
        self.with_context(skip_arkite_hierarchy_autosync=True).write({
            'arkite_process_steps_loaded': True,
            'arkite_process_steps_dirty': False,
        })

        # Set selected process if none
        if not self.selected_process_id_char and self.arkite_process_ids:
            first_pid = self.arkite_process_ids.sorted(lambda p: (p.sequence or 0, p.id))[0].process_id
            self.selected_process_id_char = first_pid
            self.selected_arkite_process_id = first_pid

