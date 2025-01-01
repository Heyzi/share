import gitlab
import argparse
from typing import Dict, List
import jinja2
from datetime import datetime

class GitLabScanner:
   def __init__(self, token: str, url: str):
       """Initialize GitLab connection."""
       self.gl = gitlab.Gitlab(url, private_token=token)
   
   def get_default_branch(self, project_id: int) -> str:
       """Get default branch name for a project."""
       try:
           project = self.gl.projects.get(project_id)
           return project.default_branch or 'master'
       except Exception as e:
           print(f"Error getting default branch for project {project_id}: {str(e)}")
           return 'master'
   
   def get_project_size(self, project_id: int) -> Dict[str, int]:
       """Get project size statistics including repository, storage and artifacts sizes."""
       try:
           project = self.gl.projects.get(project_id, statistics=True)
           stats = project.statistics
           return {
               'repository_size': stats.get('repository_size', 0),
               'storage_size': stats.get('storage_size', 0),
               'artifacts_size': stats.get('job_artifacts_size', 0)
           }
       except Exception as e:
           print(f"Error getting size for project {project_id}: {str(e)}")
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
           project = self.gl.projects.get(project_id)
           most_recent_commit = project.commits.list(per_page=1)
           if most_recent_commit and len(most_recent_commit) > 0:
               return most_recent_commit[0].committed_date.split('.')[0].replace('T', ' ')
           return 'N/A'
       except Exception as e:
           print(f"Error getting last commit for project {project_id}: {str(e)}")
           return 'N/A'

   def get_last_pipeline_date(self, project_id: int) -> str:
       """Get date of the most recent pipeline."""
       try:
           project = self.gl.projects.get(project_id)
           pipelines = project.pipelines.list(per_page=1)
           if pipelines and len(pipelines) > 0:
               return pipelines[0].created_at.split('.')[0].replace('T', ' ')
           return 'N/A'
       except Exception as e:
           print(f"Error getting last pipeline for project {project_id}: {str(e)}")
           return 'N/A'
   
   def scan_group(self, group_id: int) -> Dict[str, List[Dict]]:
       """Recursively scan group and its subgroups for projects information."""
       results = {}
       group = self.gl.groups.get(group_id)
       
       # Scan projects in current group
       for project in group.projects.list(all=True, get_all=True):
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
       for subgroup in group.subgroups.list(all=True, get_all=True):
           sub_results = self.scan_group(subgroup.id)
           results.update(sub_results)
           
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
           .group-header.collapsed::before {
               transform: rotate(-90deg);
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

       // Group toggling functionality
       document.querySelectorAll('.group-header').forEach(header => {
           header.addEventListener('click', function() {
               this.classList.toggle('collapsed');
               const content = this.nextElementSibling;
               content.style.display = content.style.display === 'none' ? 'block' : 'none';
           });
       });
       </script>
   </body>
   </html>
   """
   
   env = jinja2.Environment()
   template = env.from_string(template)
   html = template.render(results=results)
   
   with open(output_file, 'w') as f:
       f.write(html)

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
