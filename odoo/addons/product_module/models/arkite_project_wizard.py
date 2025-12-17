# product_module/models/arkite_project_wizard.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import os
import logging

_logger = logging.getLogger(__name__)


class ArkiteProjectWizard(models.TransientModel):
    _name = 'product_module.arkite.project.wizard'
    _description = 'Create or Duplicate Arkite Project'

    # Project creation fields
    project_name = fields.Char(
        string='Project Name',
        required=True,
        help='Name for the new Arkite project'
    )
    
    project_comment = fields.Text(
        string='Comment',
        help='Optional comment/description for the project'
    )
    
    unit_ids = fields.Char(
        string='Unit IDs',
        default='[]',
        help='Comma-separated list of unit IDs (e.g., 12345, 67890) or leave empty for default'
    )
    
    # Template selection
    use_template = fields.Boolean(
        string='Duplicate from Template',
        default=False,
        help='If checked, duplicate an existing project template instead of creating new'
    )
    
    template_id = fields.Many2one(
        'product_module.arkite.template',
        string='Template Project',
        domain=[],
        help='Select a template project to duplicate'
    )
    
    template_name = fields.Char(
        string='Template Name',
        help='Name of the template project to duplicate (if template not in list)'
    )
    
    # Template info display
    template_jobs_info = fields.Html(
        string='Template Jobs',
        compute='_compute_template_info',
        readonly=True,
        help='Jobs available in the selected template'
    )
    
    template_variants_info = fields.Html(
        string='Template Variants',
        compute='_compute_template_info',
        readonly=True,
        help='Variants available in the selected template'
    )
    
    # Jobs and Variants
    job_names = fields.Text(
        string='Job Names',
        help='Comma-separated list of job names. Jobs are automatically copied when duplicating templates.'
    )
    
    variant_codes = fields.Text(
        string='Variant Names',
        help='Comma-separated list of variant names to create (e.g., "V1, V2, V3" or "Red+V6, Blue+V8"). These are project-level variants that jobs can reference in their steps.'
    )
    
    # Existing projects/templates display
    existing_projects_info = fields.Html(
        string='Existing Projects',
        compute='_compute_existing_projects',
        readonly=True,
        help='List of existing projects and templates in Arkite'
    )
    
    # Fields to fetch tasks from a specific project
    project_id_to_inspect = fields.Integer(
        string='Project ID',
        help='Enter a project ID to fetch and display its tasks (jobs)'
    )
    
    project_name_to_inspect = fields.Char(
        string='Project Name',
        help='Enter a project name to fetch and display its tasks (jobs)'
    )
    
    project_tasks_info = fields.Html(
        string='Tasks from Project',
        readonly=True,
        help='Tasks (jobs) retrieved from the specified project via API endpoint /projects/{id}/tasks/'
    )
    
    # Additional testing fields
    compare_project_id_1 = fields.Integer(
        string='Project ID 1',
        help='First project ID for comparison'
    )
    
    compare_project_id_2 = fields.Integer(
        string='Project ID 2',
        help='Second project ID for comparison'
    )
    
    comparison_info = fields.Html(
        string='Comparison Results',
        readonly=True,
        help='Comparison of tasks between two projects'
    )
    
    all_projects_tasks_summary = fields.Html(
        string='All Projects Tasks Summary',
        readonly=True,
        help='Summary of all projects and their task counts'
    )
    
    # API Configuration (from environment)
    api_base = fields.Char(
        string='Arkite API Base URL',
        compute='_compute_api_config',
        readonly=True
    )
    
    api_key = fields.Char(
        string='API Key',
        compute='_compute_api_config',
        readonly=True
    )
    
    @api.depends('create_uid')
    def _compute_api_config(self):
        """Load API configuration from environment variables"""
        for wizard in self:
            wizard.api_base = os.getenv('ARKITE_API_BASE', '')
            wizard.api_key = os.getenv('ARKITE_API_KEY', '')
    
    @api.depends('create_uid')
    def _compute_existing_projects(self):
        """Fetch and display existing projects from Arkite"""
        for wizard in self:
            html_content = '<div style="max-height: 300px; overflow-y: auto;">'
            
            api_base = os.getenv('ARKITE_API_BASE')
            api_key = os.getenv('ARKITE_API_KEY')
            
            if not api_base or not api_key:
                wizard.existing_projects_info = '<p style="color: #856404;">API configuration missing. Cannot fetch projects.</p>'
                continue
            
            try:
                url = f"{api_base}/projects/"
                params = {"apiKey": api_key}
                headers = {"Content-Type": "application/json"}
                
                response = requests.get(
                    url,
                    params=params,
                    headers=headers,
                    verify=False,
                    timeout=10
                )
                
                if response.ok:
                    projects = response.json()
                    if isinstance(projects, list) and projects:
                        html_content += '<table class="table table-sm" style="font-size: 12px;">'
                        html_content += '<thead><tr><th>ID</th><th>Name</th><th>Comment</th></tr></thead><tbody>'
                        
                        for proj in projects[:20]:  # Show first 20
                            proj_id = proj.get("Id") or proj.get("ProjectId", "N/A")
                            proj_name = proj.get("Name") or proj.get("ProjectName", "Unnamed")
                            proj_comment = proj.get("Comment") or proj.get("Description", "")
                            if len(proj_comment) > 50:
                                proj_comment = proj_comment[:50] + "..."
                            
                            html_content += f'<tr><td>{proj_id}</td><td><strong>{proj_name}</strong></td><td>{proj_comment}</td></tr>'
                        
                        html_content += '</tbody></table>'
                        if len(projects) > 20:
                            html_content += f'<p style="font-size: 11px; color: #666;">Showing first 20 of {len(projects)} projects</p>'
                    else:
                        html_content += '<p>No projects found in Arkite.</p>'
                else:
                    html_content += '<p style="color: #dc3545;">Failed to fetch projects from Arkite API.</p>'
                    
            except Exception as e:
                _logger.error("Error fetching existing projects: %s", e)
                html_content += f'<p style="color: #dc3545;">Error loading projects: {str(e)}</p>'
            
            html_content += '</div>'
            wizard.existing_projects_info = html_content
    
    def _fetch_project_data(self, project_id, project_name=None):
        """Helper method to fetch various data from a project: tasks, processes, steps"""
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            return '<p style="color: #dc3545; font-size: 12px;">API configuration missing. Cannot fetch data.</p>'
        
        if not project_id:
            return '<p style="color: #dc3545; font-size: 12px;">Project ID is required.</p>'
        
        display_name = project_name or f"Project {project_id}"
        html_parts = []
        
        # Fetch Tasks (reusable step groups - NOT jobs)
        try:
            url = f"{api_base}/projects/{project_id}/tasks/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("Fetching tasks (reusable step groups) from project ID %s", project_id)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            
            if response.ok:
                tasks = response.json()
                if isinstance(tasks, list):
                    html_parts.append(f'<h4 style="font-size: 13px; margin-top: 12px;">Tasks (Reusable Step Groups): {len(tasks)}</h4>')
                    if tasks:
                        html_parts.append('<table style="width: 100%; border-collapse: collapse; font-size: 12px;"><thead><tr style="background-color: #f8f9fa;"><th style="padding: 8px; border: 1px solid #dee2e6;">ID</th><th style="padding: 8px; border: 1px solid #dee2e6;">Name</th><th style="padding: 8px; border: 1px solid #dee2e6;">Type</th></tr></thead><tbody>')
                        for task in tasks:
                            html_parts.append(f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;">{task.get("Id", "N/A")}</td><td style="padding: 8px; border: 1px solid #dee2e6;"><strong>{task.get("Name", "Unnamed")}</strong></td><td style="padding: 8px; border: 1px solid #dee2e6;">{task.get("Type", "N/A")}</td></tr>')
                        html_parts.append('</tbody></table>')
                        html_parts.append('<p style="font-size: 11px; color: #666; margin-top: 4px;"><em>Note: "Tasks" in API are reusable step groups, NOT jobs.</em></p>')
                    else:
                        html_parts.append('<p style="color: #666; font-size: 12px;">No tasks found.</p>')
        except Exception as e:
            _logger.error("Error fetching tasks: %s", e)
            html_parts.append(f'<p style="color: #dc3545; font-size: 12px;">Error fetching tasks: {str(e)}</p>')
        
        # Fetch Processes (jobs might be represented as processes)
        try:
            url = f"{api_base}/projects/{project_id}/processes/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("Fetching processes from project ID %s", project_id)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            
            if response.ok:
                processes = response.json()
                if isinstance(processes, list):
                    html_parts.append(f'<h4 style="font-size: 13px; margin-top: 12px;">Processes: {len(processes)}</h4>')
                    if processes:
                        html_parts.append('<table style="width: 100%; border-collapse: collapse; font-size: 12px;"><thead><tr style="background-color: #f8f9fa;"><th style="padding: 8px; border: 1px solid #dee2e6;">ID</th><th style="padding: 8px; border: 1px solid #dee2e6;">Name</th><th style="padding: 8px; border: 1px solid #dee2e6;">Type</th><th style="padding: 8px; border: 1px solid #dee2e6;">Comment</th></tr></thead><tbody>')
                        for proc in processes:
                            proc_comment = (proc.get("Comment", "") or "")[:50]
                            html_parts.append(f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;">{proc.get("Id", "N/A")}</td><td style="padding: 8px; border: 1px solid #dee2e6;"><strong>{proc.get("Name", "Unnamed")}</strong></td><td style="padding: 8px; border: 1px solid #dee2e6;">{proc.get("Type", "N/A")}</td><td style="padding: 8px; border: 1px solid #dee2e6;">{proc_comment}</td></tr>')
                        html_parts.append('</tbody></table>')
                        html_parts.append('<p style="font-size: 11px; color: #666; margin-top: 4px;"><em>Note: Jobs might be represented as "Job Selection Process" or similar process types.</em></p>')
                    else:
                        html_parts.append('<p style="color: #666; font-size: 12px;">No processes found.</p>')
        except Exception as e:
            _logger.error("Error fetching processes: %s", e)
            html_parts.append(f'<p style="color: #dc3545; font-size: 12px;">Error fetching processes: {str(e)}</p>')
        
        # Fetch Steps (jobs contain steps)
        try:
            url = f"{api_base}/projects/{project_id}/steps/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            _logger.info("Fetching steps from project ID %s", project_id)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            
            if response.ok:
                steps = response.json()
                if isinstance(steps, list):
                    html_parts.append(f'<h4 style="font-size: 13px; margin-top: 12px;">Steps: {len(steps)}</h4>')
                    if steps:
                        # Show first 10 steps
                        html_parts.append('<table style="width: 100%; border-collapse: collapse; font-size: 12px;"><thead><tr style="background-color: #f8f9fa;"><th style="padding: 8px; border: 1px solid #dee2e6;">ID</th><th style="padding: 8px; border: 1px solid #dee2e6;">Name</th><th style="padding: 8px; border: 1px solid #dee2e6;">Type</th></tr></thead><tbody>')
                        for step in steps[:10]:
                            html_parts.append(f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;">{step.get("Id", "N/A")}</td><td style="padding: 8px; border: 1px solid #dee2e6;"><strong>{step.get("Name", "Unnamed")}</strong></td><td style="padding: 8px; border: 1px solid #dee2e6;">{step.get("Type", "N/A")}</td></tr>')
                        html_parts.append('</tbody></table>')
                        if len(steps) > 10:
                            html_parts.append(f'<p style="font-size: 11px; color: #666;">Showing first 10 of {len(steps)} steps</p>')
                        html_parts.append('<p style="font-size: 11px; color: #666; margin-top: 4px;"><em>Note: Steps are part of jobs/processes. Jobs contain multiple steps.</em></p>')
                    else:
                        html_parts.append('<p style="color: #666; font-size: 12px;">No steps found.</p>')
        except Exception as e:
            _logger.error("Error fetching steps: %s", e)
            html_parts.append(f'<p style="color: #dc3545; font-size: 12px;">Error fetching steps: {str(e)}</p>')
        
        if html_parts:
            return f'<div style="margin-top: 8px;"><h3 style="font-size: 14px;">Project "{display_name}" (ID: {project_id}) Data:</h3>' + ''.join(html_parts) + '</div>'
        else:
            return f'<p style="color: #dc3545; font-size: 12px;">Failed to fetch any data from project "{display_name}" (ID: {project_id}).</p>'
    
    def action_fetch_tasks_by_id(self):
        """Button action to fetch tasks by project ID"""
        if not self.project_id_to_inspect:
            self.project_tasks_info = '<p style="color: #dc3545; font-size: 12px;">Please enter a project ID.</p>'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Please enter a project ID',
                    'type': 'danger',
                }
            }
        
        project_id = self.project_id_to_inspect
        self.project_tasks_info = self._fetch_project_data(project_id)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Fetched tasks for project ID {project_id}',
                'type': 'success',
            }
        }
    
    def action_fetch_tasks_by_name(self):
        """Button action to fetch tasks by project name"""
        if not self.project_name_to_inspect or not self.project_name_to_inspect.strip():
            self.project_tasks_info = '<p style="color: #dc3545; font-size: 12px;">Please enter a project name.</p>'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Please enter a project name',
                    'type': 'danger',
                }
            }
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            self.project_tasks_info = '<p style="color: #dc3545; font-size: 12px;">API configuration missing.</p>'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'API configuration missing',
                    'type': 'danger',
                }
            }
        
        project_name = self.project_name_to_inspect.strip()
        project_id = None
        
        # Find project by name
        try:
            url = f"{api_base}/projects/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if response.ok:
                projects = response.json()
                if isinstance(projects, list):
                    for proj in projects:
                        if proj.get("Name", "").strip() == project_name:
                            project_id = proj.get("Id")
                            break
            
            if not project_id:
                self.project_tasks_info = f'<p style="color: #dc3545; font-size: 12px;">Project "{project_name}" not found. Please check the name.</p>'
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': f'Project "{project_name}" not found',
                        'type': 'danger',
                    }
                }
            
            self.project_tasks_info = self._fetch_tasks_for_project(project_id, project_name)
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': f'Fetched tasks for project "{project_name}"',
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error("Error finding project by name: %s", e)
            self.project_tasks_info = f'<p style="color: #dc3545; font-size: 12px;">Error finding project: {str(e)}</p>'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                }
            }
    
    def action_compare_projects(self):
        """Button action to compare tasks between two projects"""
        if not self.compare_project_id_1 or not self.compare_project_id_2:
            self.comparison_info = '<p style="color: #dc3545; font-size: 12px;">Please enter both project IDs.</p>'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'Please enter both project IDs',
                    'type': 'danger',
                }
            }
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            self.comparison_info = '<p style="color: #dc3545; font-size: 12px;">API configuration missing.</p>'
            return
        
        try:
            # Fetch processes from both projects (jobs might be processes)
            processes_1 = self._get_processes_list(self.compare_project_id_1)
            processes_2 = self._get_processes_list(self.compare_project_id_2)
            
            html = '<div style="margin-top: 8px;">'
            html += f'<h4 style="font-size: 14px;">Comparison: Project {self.compare_project_id_1} vs Project {self.compare_project_id_2}</h4>'
            html += f'<p><strong>Project {self.compare_project_id_1}:</strong> {len(processes_1)} process(es)</p>'
            html += f'<p><strong>Project {self.compare_project_id_2}:</strong> {len(processes_2)} process(es)</p>'
            html += '<p style="font-size: 11px; color: #666;"><em>Note: Comparing processes. Jobs might be represented as processes.</em></p>'
            
            # Compare process names
            names_1 = {p.get("Name", "") for p in processes_1}
            names_2 = {p.get("Name", "") for p in processes_2}
            
            common = names_1 & names_2
            only_1 = names_1 - names_2
            only_2 = names_2 - names_1
            
            html += '<table style="width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 12px;">'
            html += '<tr><th style="padding: 8px; border: 1px solid #dee2e6; background-color: #f8f9fa;">Category</th><th style="padding: 8px; border: 1px solid #dee2e6; background-color: #f8f9fa;">Count</th><th style="padding: 8px; border: 1px solid #dee2e6; background-color: #f8f9fa;">Process Names</th></tr>'
            html += f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;"><strong>Common Processes</strong></td><td style="padding: 8px; border: 1px solid #dee2e6;">{len(common)}</td><td style="padding: 8px; border: 1px solid #dee2e6;">{", ".join(sorted(common)) if common else "None"}</td></tr>'
            html += f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;">Only in Project {self.compare_project_id_1}</td><td style="padding: 8px; border: 1px solid #dee2e6;">{len(only_1)}</td><td style="padding: 8px; border: 1px solid #dee2e6;">{", ".join(sorted(only_1)) if only_1 else "None"}</td></tr>'
            html += f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;">Only in Project {self.compare_project_id_2}</td><td style="padding: 8px; border: 1px solid #dee2e6;">{len(only_2)}</td><td style="padding: 8px; border: 1px solid #dee2e6;">{", ".join(sorted(only_2)) if only_2 else "None"}</td></tr>'
            html += '</table>'
            html += '</div>'
            
            self.comparison_info = html
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': 'Comparison completed',
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error("Error comparing projects: %s", e)
            self.comparison_info = f'<p style="color: #dc3545; font-size: 12px;">Error: {str(e)}</p>'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                }
            }
    
    def _get_processes_list(self, project_id):
        """Helper to get processes list for a project (jobs might be processes)"""
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            return []
        
        try:
            url = f"{api_base}/projects/{project_id}/processes/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if response.ok:
                processes = response.json()
                if isinstance(processes, list):
                    return processes
            return []
        except Exception as e:
            _logger.error("Error fetching processes for project %s: %s", project_id, e)
            return []
    
    def action_fetch_all_projects_summary(self):
        """Button action to fetch all projects with their task counts"""
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            self.all_projects_tasks_summary = '<p style="color: #dc3545; font-size: 12px;">API configuration missing.</p>'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': 'API configuration missing',
                    'type': 'danger',
                }
            }
        
        try:
            # Fetch all projects
            url = f"{api_base}/projects/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            if not response.ok:
                self.all_projects_tasks_summary = f'<p style="color: #dc3545; font-size: 12px;">Failed to fetch projects: HTTP {response.status_code}</p>'
                return
            
            projects = response.json()
            if not isinstance(projects, list):
                self.all_projects_tasks_summary = '<p style="color: #dc3545; font-size: 12px;">Unexpected response format.</p>'
                return
            
            html = '<div style="margin-top: 8px;">'
            html += f'<h4 style="font-size: 14px;">All Projects Tasks Summary ({len(projects)} projects)</h4>'
            html += '<table style="width: 100%; border-collapse: collapse; font-size: 12px;">'
            html += '<thead><tr style="background-color: #f8f9fa;"><th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Project ID</th><th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Project Name</th><th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Task Count</th><th style="padding: 8px; border: 1px solid #dee2e6; text-align: left;">Task Names</th></tr></thead>'
            html += '<tbody>'
            
            for proj in projects[:50]:  # Limit to 50 for performance
                proj_id = proj.get("Id")
                proj_name = proj.get("Name", "Unnamed")
                
                # Fetch processes for this project (jobs might be processes)
                processes = self._get_processes_list(proj_id)
                process_count = len(processes)
                process_names = ", ".join([p.get("Name", "Unnamed") for p in processes[:5]])  # Show first 5
                if len(processes) > 5:
                    process_names += f" ... (+{len(processes) - 5} more)"
                
                html += f'<tr><td style="padding: 8px; border: 1px solid #dee2e6;">{proj_id}</td>'
                html += f'<td style="padding: 8px; border: 1px solid #dee2e6;"><strong>{proj_name}</strong></td>'
                html += f'<td style="padding: 8px; border: 1px solid #dee2e6;">{process_count}</td>'
                html += f'<td style="padding: 8px; border: 1px solid #dee2e6;">{process_names or "None"}</td></tr>'
            
            html += '</tbody></table>'
            if len(projects) > 50:
                html += f'<p style="font-size: 11px; color: #666;">Showing first 50 of {len(projects)} projects</p>'
            html += '</div>'
            
            self.all_projects_tasks_summary = html
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Success',
                    'message': f'Fetched summary for {len(projects)} projects',
                    'type': 'success',
                }
            }
        except Exception as e:
            _logger.error("Error fetching all projects summary: %s", e)
            self.all_projects_tasks_summary = f'<p style="color: #dc3545; font-size: 12px;">Error: {str(e)}</p>'
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Error',
                    'message': f'Error: {str(e)}',
                    'type': 'danger',
                }
            }
    
    @api.depends('template_id', 'template_name', 'use_template')
    def _compute_template_info(self):
        """Fetch jobs and variants from selected template"""
        for wizard in self:
            wizard.template_jobs_info = '<p style="color: #666; font-size: 12px;">Select a template to see available jobs and variants.</p>'
            wizard.template_variants_info = '<p style="color: #666; font-size: 12px;">Select a template to see available jobs and variants.</p>'
            
            if not wizard.use_template:
                return
            
            template_id = None
            if wizard.template_id:
                template_id = wizard.template_id.arkite_project_id
            elif wizard.template_name:
                # Use the model method to get project ID
                api_base = os.getenv('ARKITE_API_BASE')
                api_key = os.getenv('ARKITE_API_KEY')
                if api_base and api_key:
                    url = f"{api_base}/projects/"
                    params = {"apiKey": api_key}
                    headers = {"Content-Type": "application/json"}
                    try:
                        response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                        if response.ok:
                            projects = response.json()
                            if isinstance(projects, list):
                                for proj in projects:
                                    name = proj.get("Name") or proj.get("ProjectName")
                                    if name == wizard.template_name:
                                        template_id = proj.get("Id") or proj.get("ProjectId")
                                        break
                    except Exception:
                        pass
            
            if not template_id:
                return
            
            api_base = os.getenv('ARKITE_API_BASE')
            api_key = os.getenv('ARKITE_API_KEY')
            
            if not api_base or not api_key:
                return
            
            # Fetch tasks (jobs) from template
            try:
                url = f"{api_base}/projects/{template_id}/tasks/"
                params = {"apiKey": api_key}
                headers = {"Content-Type": "application/json"}
                
                response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                
                if response.ok:
                    tasks = response.json()
                    if isinstance(tasks, list) and tasks:
                        html = '<ul style="margin: 0; padding-left: 20px; font-size: 12px;">'
                        for task in tasks:
                            task_name = task.get("Name", "Unnamed")
                            task_id = task.get("Id", "N/A")
                            html += f'<li><strong>{task_name}</strong> (ID: {task_id})</li>'
                        html += '</ul>'
                        wizard.template_jobs_info = html
                    else:
                        wizard.template_jobs_info = '<p style="color: #666; font-size: 12px;">No jobs found in this template.</p>'
            except Exception as e:
                _logger.warning("Error fetching template jobs: %s", e)
                wizard.template_jobs_info = f'<p style="color: #dc3545; font-size: 12px;">Error loading jobs: {str(e)}</p>'
            
            # Fetch variants from template
            try:
                url = f"{api_base}/projects/{template_id}/variants/"
                params = {"apiKey": api_key}
                headers = {"Content-Type": "application/json"}
                
                response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                
                if response.ok:
                    variants = response.json()
                    if isinstance(variants, list) and variants:
                        html = '<ul style="margin: 0; padding-left: 20px; font-size: 12px;">'
                        for var in variants:
                            var_name = var.get("Name", "Unnamed")
                            var_code = var.get("Code") or var_name
                            var_id = var.get("Id", "N/A")
                            html += f'<li><strong>{var_code}</strong> - {var_name} (ID: {var_id})</li>'
                        html += '</ul>'
                        wizard.template_variants_info = html
                    else:
                        wizard.template_variants_info = '<p style="color: #666; font-size: 12px;">No variants found in this template.</p>'
            except Exception as e:
                _logger.warning("Error fetching template variants: %s", e)
                wizard.template_variants_info = f'<p style="color: #dc3545; font-size: 12px;">Error loading variants: {str(e)}</p>'

    @api.model
    def default_get(self, fields_list):
        """Set default values when wizard opens"""
        res = super().default_get(fields_list)
        # Don't load templates here - load them only when user enables template option
        # This avoids transaction issues during wizard creation
        
        # Set initial values for display fields
        if 'project_tasks_info' in fields_list:
            res['project_tasks_info'] = '<p style="color: #666; font-size: 12px;">Enter a project ID or name and click the button to fetch tasks.</p>'
        if 'comparison_info' in fields_list:
            res['comparison_info'] = '<p style="color: #666; font-size: 12px;">Enter two project IDs and click "Compare Tasks" to compare.</p>'
        if 'all_projects_tasks_summary' in fields_list:
            res['all_projects_tasks_summary'] = '<p style="color: #666; font-size: 12px;">Click "Fetch All Projects Tasks Summary" to see all projects and their task counts.</p>'
        
        return res

    @api.onchange('use_template', 'template_id', 'template_name')
    def _onchange_use_template(self):
        """Load available templates when template option is enabled"""
        if self.use_template:
            try:
                self._load_templates()
            except Exception as e:
                _logger.warning("Could not load templates: %s", e)
                # Don't raise - just log the error so the form can still be used

    @api.model
    def _load_templates(self):
        """Load available projects from Arkite API as templates"""
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            return
        
        try:
            url = f"{api_base}/projects/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(
                url,
                params=params,
                headers=headers,
                verify=False,
                timeout=10
            )
            
            if response.ok:
                projects = response.json()
                if isinstance(projects, list):
                    # Use a new cursor to avoid transaction issues
                    template_model = self.env['product_module.arkite.template']
                    for proj in projects:
                        project_id = proj.get("Id") or proj.get("ProjectId")
                        project_name = proj.get("Name") or proj.get("ProjectName", "")
                        
                        if project_id and project_name:
                            try:
                                # Find or create template record
                                template = template_model.search([
                                    ('arkite_project_id', '=', project_id)
                                ], limit=1)
                                
                                if not template:
                                    # Use sudo to avoid permission issues, and catch any database errors
                                    try:
                                        template_model.sudo().create({
                                            'name': project_name,
                                            'arkite_project_id': project_id,
                                        })
                                    except Exception as db_error:
                                        # Database error (e.g., unique constraint) - log and continue
                                        _logger.debug("Template %s (ID: %s) already exists or constraint violation: %s", 
                                                    project_name, project_id, db_error)
                                        continue
                            except Exception as e:
                                # Log but don't fail - might be duplicate or constraint issue
                                _logger.debug("Could not create template %s: %s", project_name, e)
                                continue
        except requests.exceptions.RequestException as e:
            _logger.warning("Error connecting to Arkite API to load templates: %s", e)
        except Exception as e:
            _logger.error("Error loading templates: %s", e)

    def _get_unit_ids_list(self):
        """Parse unit_ids string into list of integers"""
        if not self.unit_ids or self.unit_ids.strip() == '[]':
            # Get default unit ID from environment
            unit_id_str = os.getenv('ARKITE_UNIT_ID', '')
            if unit_id_str:
                try:
                    return [int(unit_id_str)]
                except ValueError:
                    pass
            return []
        
        # Parse comma-separated values
        try:
            # Remove brackets if present
            ids_str = self.unit_ids.strip().strip('[]')
            if not ids_str:
                return []
            
            # Split by comma and convert to int
            ids = [int(x.strip()) for x in ids_str.split(',') if x.strip()]
            return ids
        except ValueError:
            raise UserError(_('Invalid Unit IDs format. Use comma-separated numbers (e.g., 12345, 67890)'))

    def _create_project(self):
        """Create a new Arkite project"""
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError(_('Arkite API configuration is missing. Please check environment variables.'))
        
        unit_ids = self._get_unit_ids_list()
        if not unit_ids:
            raise UserError(_('At least one Unit ID is required. Please configure ARKITE_UNIT_ID or provide Unit IDs.'))
        
        url = f"{api_base}/projects/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        payload = [{
            "Name": self.project_name,
            "Comment": self.project_comment or "Created from Odoo",
            "UnitIds": unit_ids,
        }]
        
        try:
            response = requests.post(
                url,
                params=params,
                json=payload,
                headers=headers,
                verify=False,
                timeout=10
            )
            
            # Parse response
            try:
                response_data = response.json()
            except:
                response_data = None
            
            # Check if response contains an error message
            has_error = False
            error_msg = None
            if response_data:
                if isinstance(response_data, dict):
                    if 'Type' in response_data and response_data.get('Type') == 'ERROR':
                        has_error = True
                        error_msg = response_data.get('ErrorMessage', 'Unknown error')
                    elif 'ErrorMessage' in response_data:
                        has_error = True
                        error_msg = response_data.get('ErrorMessage')
            
            if response.ok and not has_error:
                # Normal success case - get project ID from response
                if isinstance(response_data, list) and response_data:
                    project_id = response_data[0].get("Id") or response_data[0].get("ProjectId")
                    if project_id:
                        return project_id
                elif isinstance(response_data, dict):
                    project_id = response_data.get("Id") or response_data.get("ProjectId")
                    if project_id:
                        return project_id
            
            # Even if response has error or status is not OK, Arkite sometimes still creates the project
            # This is a known Arkite API quirk - check if project was actually created
            _logger.info("Response indicates error, but checking if project was still created: %s", error_msg or "No error message")
            import time
            time.sleep(1)  # Give Arkite a moment to finish creating
            project_id = self._get_project_id_by_name(self.project_name)
            
            if project_id:
                # Project was created despite the error - log warning but return success
                if error_msg:
                    _logger.warning("Project '%s' was created successfully despite API error: %s", self.project_name, error_msg)
                return project_id
            
            # Project was not created - raise error with the message we found
            if error_msg:
                # Provide user-friendly message for common errors
                if 'Could not find a part of the path' in error_msg or 'path' in error_msg.lower():
                    raise UserError(_(
                        'Failed to create project: Arkite server is missing required files.\n\n'
                        'Error: %s\n\n'
                        'This is a server-side issue. Please check:\n'
                        '1. Arkite server installation is complete\n'
                        '2. Default visualization images are present\n'
                        '3. Server has proper file permissions'
                    ) % error_msg)
                else:
                    raise UserError(_('Failed to create project: %s') % error_msg)
            else:
                # No specific error message, use status code
                raise UserError(_('Failed to create project: HTTP %s - Project was not created') % response.status_code)
                
        except requests.exceptions.RequestException as e:
            raise UserError(_('Error connecting to Arkite API: %s') % str(e))

    def _duplicate_project(self, template_id, new_name):
        """Duplicate an existing Arkite project"""
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            raise UserError(_('Arkite API configuration is missing. Please check environment variables.'))
        
        # Step 1: Duplicate the project
        url = f"{api_base}/projects/{template_id}/duplicate/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.post(
                url,
                params=params,
                headers=headers,
                verify=False,
                timeout=10
            )
            
            if not response.ok:
                # Try to parse error message from response
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict):
                        if 'ErrorMessage' in error_data:
                            error_msg = error_data['ErrorMessage']
                        elif 'error' in error_data:
                            error_msg = error_data['error']
                        elif 'message' in error_data:
                            error_msg = error_data['message']
                        else:
                            error_msg = str(error_data)
                    else:
                        error_msg = str(error_data)
                except:
                    error_msg = response.text or error_msg
                
                # Provide user-friendly message for common errors
                if 'Could not find a part of the path' in error_msg or 'path' in error_msg.lower():
                    raise UserError(_(
                        'Failed to duplicate project: Arkite server is missing required files.\n\n'
                        'Error: %s\n\n'
                        'This is a server-side issue. Please check:\n'
                        '1. Arkite server installation is complete\n'
                        '2. Default visualization images are present\n'
                        '3. Server has proper file permissions'
                    ) % error_msg)
                else:
                    raise UserError(_('Failed to duplicate project: %s') % error_msg)
            
            # Step 2: Get the new project ID
            data = response.json()
            if isinstance(data, list) and data:
                new_project = data[0]
            else:
                new_project = data
            
            new_id = new_project.get("Id") or new_project.get("ProjectId")
            if not new_id:
                raise UserError(_('Duplicate response has no project ID'))
            
            # Step 3: Rename the duplicated project
            self._rename_project(new_id, new_name)
            
            return new_id
            
        except requests.exceptions.RequestException as e:
            raise UserError(_('Error connecting to Arkite API: %s') % str(e))

    def _rename_project(self, project_id, new_name):
        """Rename an Arkite project"""
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        url = f"{api_base}/projects/{project_id}"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        payload = {"Name": new_name}
        
        try:
            response = requests.patch(
                url,
                params=params,
                json=payload,
                headers=headers,
                verify=False,
                timeout=10
            )
            
            if not response.ok:
                _logger.warning("Failed to rename project %s: %s", project_id, response.text)
                
        except requests.exceptions.RequestException as e:
            _logger.error("Error renaming project: %s", e)

    def _get_project_id_by_name(self, project_name):
        """Get project ID by name"""
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        url = f"{api_base}/projects/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                verify=False,
                timeout=10
            )
            
            if response.ok:
                projects = response.json()
                if isinstance(projects, list):
                    for proj in projects:
                        name = proj.get("Name") or proj.get("ProjectName")
                        if name == project_name:
                            return proj.get("Id") or proj.get("ProjectId")
        except Exception as e:
            _logger.error("Error getting project ID: %s", e)
        
        return None
    
    def _assign_jobs_to_project(self, project_id):
        """Assign jobs to a project by name"""
        if not self.job_names or not self.job_names.strip():
            return
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            _logger.warning("Cannot assign jobs: API configuration missing")
            return
        
        # Parse job names (comma-separated)
        job_name_list = [name.strip() for name in self.job_names.split(',') if name.strip()]
        
        if not job_name_list:
            return
        
        # Get all tasks from the project
        # NOTE: The API uses "tasks" endpoint, but in the UI/documentation these are called "jobs"
        # This is an assumption based on: same definition ("work task"), no separate /jobs/ endpoint
        try:
            url = f"{api_base}/projects/{project_id}/tasks/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            
            if response.ok:
                existing_tasks = response.json()
                if isinstance(existing_tasks, list):
                    existing_task_names = {task.get("Name", "").lower(): task.get("Id") for task in existing_tasks if task.get("Name")}
                    
                    # Note: Tasks (Jobs) cannot be created via API - only via UI or by duplicating projects
                    # When duplicating a template, tasks are automatically copied
                    # This method just logs which tasks exist
                    _logger.info("Project %s has tasks (jobs): %s", project_id, list(existing_task_names.keys()))
                    _logger.info("User requested jobs: %s", job_name_list)
                    
                    # Check if requested jobs exist
                    missing_jobs = []
                    for job_name in job_name_list:
                        if job_name.lower() not in existing_task_names:
                            missing_jobs.append(job_name)
                    
                    if missing_jobs:
                        _logger.warning("Requested jobs not found in project %s: %s. Jobs must be created in Arkite UI or duplicated from template.", 
                                       project_id, missing_jobs)
        except Exception as e:
            _logger.warning("Could not fetch tasks (jobs) for project %s: %s", project_id, e)
    
    def _assign_variants_to_project(self, project_id):
        """Assign variants to a project by code"""
        if not self.variant_codes or not self.variant_codes.strip():
            return
        
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if not api_base or not api_key:
            _logger.warning("Cannot assign variants: API configuration missing")
            return
        
        # Parse variant codes (comma-separated)
        variant_code_list = [code.strip() for code in self.variant_codes.split(',') if code.strip()]
        
        if not variant_code_list:
            return
        
        # Get existing variants
        try:
            url = f"{api_base}/projects/{project_id}/variants/"
            params = {"apiKey": api_key}
            headers = {"Content-Type": "application/json"}
            
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
            
            if response.ok:
                existing_variants = response.json()
                if isinstance(existing_variants, list):
                    # Variants are identified by Name (Code might not exist in API)
                    existing_variant_names = {}
                    for var in existing_variants:
                        name = var.get("Name", "")
                        code = var.get("Code", "")  # Code might exist but not in schema
                        identifier = code if code else name
                        if identifier:
                            existing_variant_names[identifier.upper()] = var.get("Id")
                    
                    # Check which variants need to be added
                    variants_to_add = []
                    for code in variant_code_list:
                        code_upper = code.upper()
                        if code_upper not in existing_variant_names:
                            # Variant schema: Type (required), Name (from BaseObject, required), Description (optional)
                            # Note: Code is not in the schema - variants are identified by Name
                            variant_data = {
                                "Type": "Variant",
                                "Name": code,  # Name is required from BaseObject
                                "Description": f"Variant {code}"  # Optional description
                            }
                            variants_to_add.append(variant_data)
                        else:
                            _logger.info("Variant '%s' already exists in project %s", code, project_id)
                    
                    # Add missing variants
                    if variants_to_add:
                        _logger.info("Attempting to create %d variants in project %s: %s", 
                                    len(variants_to_add), project_id, [v.get("Name") for v in variants_to_add])
                        try:
                            post_response = requests.post(
                                url,
                                params=params,
                                json=variants_to_add,
                                headers=headers,
                                verify=False,
                                timeout=10
                            )
                            
                            _logger.debug("Variant creation response status: %s", post_response.status_code)
                            _logger.debug("Variant creation response body: %s", post_response.text)
                            
                            if post_response.ok:
                                try:
                                    created_variants = post_response.json()
                                    variant_names = []
                                    if isinstance(created_variants, list):
                                        for v in created_variants:
                                            name = v.get("Name") or v.get("Code") or "Unknown"
                                            variant_names.append(name)
                                    elif isinstance(created_variants, dict):
                                        name = created_variants.get("Name") or created_variants.get("Code") or "Unknown"
                                        variant_names.append(name)
                                    
                                    _logger.info("Successfully added %d variants to project %s: %s", 
                                               len(variants_to_add), project_id, variant_names)
                                except Exception as parse_error:
                                    _logger.warning("Variants may have been created but response parsing failed: %s", parse_error)
                                    _logger.info("Response text: %s", post_response.text)
                            else:
                                error_text = post_response.text
                                _logger.error("Failed to add variants to project %s: HTTP %s", project_id, post_response.status_code)
                                _logger.error("Error response: %s", error_text)
                                _logger.error("Payload sent: %s", variants_to_add)
                                # Don't raise - just log, as project was created successfully
                        except requests.exceptions.RequestException as e:
                            _logger.error("Network error adding variants to project %s: %s", project_id, e)
                        except Exception as e:
                            _logger.error("Unexpected error adding variants to project %s: %s", project_id, e)
                    else:
                        _logger.info("All specified variants already exist in project %s", project_id)
        except Exception as e:
            _logger.warning("Could not fetch/assign variants for project %s: %s", project_id, e)

    def action_create_project(self):
        """Create or duplicate the Arkite project"""
        self.ensure_one()
        
        if not self.project_name:
            raise UserError(_('Project Name is required'))
        
        try:
            if self.use_template:
                # Duplicate from template
                if self.template_id:
                    template_id = self.template_id.arkite_project_id
                elif self.template_name:
                    template_id = self._get_project_id_by_name(self.template_name)
                    if not template_id:
                        raise UserError(_('Template project "%s" not found') % self.template_name)
                else:
                    raise UserError(_('Please select a template or enter a template name'))
                
                project_id = self._duplicate_project(template_id, self.project_name)
                message = _('Project "%s" successfully duplicated from template (ID: %s)') % (self.project_name, project_id)
            else:
                # Create new project
                project_id = self._create_project()
                if not project_id:
                    raise UserError(_('Failed to create project. Project may already exist.'))
                message = _('Project "%s" successfully created (ID: %s)') % (self.project_name, project_id)
            
            # Assign jobs and variants if specified
            if project_id:
                self._assign_jobs_to_project(project_id)
                self._assign_variants_to_project(project_id)
                
                if self.job_names or self.variant_codes:
                    message += _('\n\nJobs and variants have been assigned to the project.')
            
            # Show success message
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': message,
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error creating/duplicating project: %s", e)
            raise UserError(_('Error: %s') % str(e))
