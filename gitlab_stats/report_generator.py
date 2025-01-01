import gitlab
import argparse
from typing import Dict, List
import jinja2
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
   level=logging.INFO,
   format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class GitLabScanner:
   def __init__(self, token: str, url: str):
       """Initialize GitLab connection."""
       logger.info(f"Connecting to GitLab instance: {url}")
       self.gl = gitlab.Gitlab(url, private_token=token)
   
   def get_default_branch(self, project_id: int) -> str:
       """Get default branch name for a project."""
       try:
           project = self.gl.projects.get(project_id)
           return project.default_branch or 'master'
       except Exception as e:
           logger.error(f"Error getting default branch for project {project_id}: {str(e)}")
           return 'master'
   
   def get_project_size(self, project_id: int) -> Dict[str, int]:
       """Get project size statistics including repository, storage and artifacts sizes."""
       try:
           logger.debug(f"Getting size statistics for project {project_id}")
           project = self.gl.projects.get(project_id, statistics=True)
           stats = project.statistics
           return {
               'repository_size': stats.get('repository_size', 0),
               'storage_size': stats.get('storage_size', 0),
               'artifacts_size': stats.get('job_artifacts_size', 0)
           }
       except Exception as e:
           logger.error(f"Error getting size for project {project_id}: {str(e)}")
           return {
               'repository_size': 0,
               'storage_size': 0,
               'artifacts_size': 0
           }
   
   def has_ci_file(self, project_id: int, default_branch: str) -> bool:
       """Check if project has gitlab-ci.yml file in default branch."""
       try:
           project = self.gl.projects.get(project_id)
           project.files.get('.gitlab-ci.yml', ref=default_branch)
           return True
       except Exception:
           return False

   def get_last_commit_date(self, project_id: int, default_branch: str) -> str:
       """Get date of the most recent commit."""
       try:
           logger.debug(f"Getting last commit for project {project_id}")
           project = self.gl.projects.get(project_id)
           commits = project.commits.list(per_page=1)
           if commits and len(commits) > 0:
               return commits[0].committed_date.split('.')[0].replace('T', ' ')
           return 'N/A'
       except Exception as e:
           logger.error(f"Error getting last commit for project {project_id}: {str(e)}")
           return 'N/A'

   def get_last_pipeline_date(self, project_id: int) -> str:
       """Get date of the most recent pipeline."""
       try:
           logger.debug(f"Getting last pipeline for project {project_id}")
           project = self.gl.projects.get(project_id)
           pipelines = project.pipelines.list(per_page=1)
           if pipelines and len(pipelines) > 0:
               return pipelines[0].created_at.split('.')[0].replace('T', ' ')
           return 'N/A'
       except Exception as e:
           logger.error(f"Error getting last pipeline for project {project_id}: {str(e)}")
           return 'N/A'
   
   def scan_group(self, group_id: int) -> Dict[str, List[Dict]]:
       """Recursively scan group and its subgroups for projects information."""
       logger.info(f"Scanning group {group_id}")
       results = {}
       try:
           group = self.gl.groups.get(group_id)
           
           # Scan projects in current group
           logger.info(f"Getting projects for group {group_id}")
           for project in group.projects.list(get_all=True):
               logger.info(f"Processing project: {project.name}")
               namespace = project.namespace['full_path']
               if namespace not in results:
                   results[namespace] = []
                   
               default_branch = self.get_default_branch(project.id)
               project_info = {
                   'url': project.web_url,
                   'name': project.name,
                   'default_branch': default_branch,
                   'sizes': self.get_project_size(project.id),
                   'has_ci': self.has_ci_file(project.id, default_branch),
                   'last_commit': self.get_last_commit_date(project.id, default_branch),
                   'last_pipeline': self.get_last_pipeline_date(project.id)
               }
               results[namespace].append(project_info)
               
           # Recursively scan subgroups
           logger.info(f"Getting subgroups for group {group_id}")
           for subgroup in group.subgroups.list(get_all=True):
               logger.info(f"Scanning subgroup: {subgroup.name}")
               sub_results = self.scan_group(subgroup.id)
               results.update(sub_results)
               
       except Exception as e:
           logger.error(f"Error scanning group {group_id}: {str(e)}")
           
       return results

def generate_html_report(results: Dict[str, List[Dict]], output_file: str = 'report.html'):
   """Generate HTML report with project statistics."""
   template = """
   <!DOCTYPE html>
   <html>
   <head>
       <title>GitLab Projects Report</title>
       <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
       <link href="https://cdn.datatables.net/1.11.5/css/dataTables.bootstrap5.min.css" rel="stylesheet">
       <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
       <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
       <script src="https://cdn.datatables.net/1.11.5/js/dataTables.bootstrap5.min.js"></script>
       <style>
           .group-header {
               background-color: #f8f9fa;
               padding: 10px;
               margin: 10px 0;
               border-radius: 5px;
               cursor: pointer;
               display: flex;
               align-items: center;
           }
           .group-header::before {
               content: '▼';
               margin-right: 10px;
               transition: transform 0.3s;
           }
           .group-content {
               margin-left: 20px;
               display: block;
           }
           .size-cell {
               white-space: nowrap;
           }
           .date-cell {
               white-space: nowrap;
           }
       </style>
   </head>
   <body class="container-fluid">
       {% for namespace, projects in results.items() %}
       <div class="group">
           <div class="group-header">{{ namespace }}</div>
           <div class="group-content">
               <div class="table-responsive">
                   <table class="table table-striped table-bordered" data-namespace="{{ namespace }}">
                       <thead>
                           <tr>
                               <th>Project</th>
                               <th>Default Branch</th>
                               <th>Repository Size</th>
                               <th>Storage Size</th>
                               <th>Artifacts Size</th>
                               <th>CI Config</th>
                               <th>Last Commit</th>
                               <th>Last Pipeline</th>
                           </tr>
                       </thead>
                       <tbody>
                           {% for project in projects %}
                           <tr>
                               <td><a href="{{ project.url }}">{{ project.name }}</a></td>
                               <td>{{ project.default_branch }}</td>
                               <td class="size-cell">{{ (project.sizes.repository_size / 1024 / 1024) | round(2) }} MB</td>
                               <td class="size-cell">{{ (project.sizes.storage_size / 1024 / 1024) | round(2) }} MB</td>
                               <td class="size-cell">{{ (project.sizes.artifacts_size / 1024 / 1024) | round(2) }} MB</td>
                               <td>{{ 'Yes' if project.has_ci else 'No' }}</td>
                               <td class="date-cell">{{ project.last_commit }}</td>
                               <td class="date-cell">{{ project.last_pipeline }}</td>
                           </tr>
                           {% endfor %}
                       </tbody>
                   </table>
               </div>
           </div>
       </div>
       {% endfor %}
       
       <script>
       document.addEventListener('DOMContentLoaded', function() {
           // Initialize all tables with DataTables
           document.querySelectorAll('table').forEach(table => {
               if (!$.fn.DataTable.isDataTable(table)) {
                   $(table).DataTable({
                       "pageLength": 25,
                       "order": [[0, "asc"]]
                   });
               }
           });
       });
       </script>
   </body>
   </html>
   """
   
   logger.info("Generating HTML report")
   env = jinja2.Environment()
   template = env.from_string(template)
   html = template.render(results=results)
   
   with open(output_file, 'w', encoding='utf-8') as f:
       f.write(html)
   logger.info(f"Report saved to {output_file}")

def main():
   """Main function to run the GitLab scanner."""
   parser = argparse.ArgumentParser(description='Generate GitLab projects report')
   parser.add_argument('--token', required=True, help='GitLab API token')
   parser.add_argument('--group-id', type=int, required=True, help='GitLab group ID to scan')
   parser.add_argument('--gitlab-url', default='https://gitlab.com', help='GitLab instance URL')
   args = parser.parse_args()

   scanner = GitLabScanner(args.token, args.gitlab_url)
   results = scanner.scan_group(args.group_id)
   generate_html_report(results)

if __name__ == '__main__':
   main()
