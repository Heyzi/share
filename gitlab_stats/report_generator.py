import gitlab
import argparse
from typing import Dict, List
import jinja2
from datetime import datetime
import pytz

class GitLabScanner:
   def __init__(self, token: str, url: str):
       self.gl = gitlab.Gitlab(url, private_token=token)
   
   def get_default_branch(self, project_id: int) -> str:
       try:
           project = self.gl.projects.get(project_id)
           return project.default_branch or 'master'
       except:
           return 'master'
   
   def get_project_size(self, project_id: int) -> Dict[str, int]:
       try:
           project = self.gl.projects.get(project_id)
           return {
               'repository_size': project.statistics['repository_size'],
               'storage_size': project.statistics['storage_size']
           }
       except:
           return {'repository_size': 0, 'storage_size': 0}
   
   def has_ci_file(self, project_id: int, default_branch: str) -> bool:
       try:
           project = self.gl.projects.get(project_id)
           project.files.get('.gitlab-ci.yml', ref=default_branch)
           return True
       except:
           return False

   def get_last_commit_date(self, project_id: int, default_branch: str) -> str:
       try:
           project = self.gl.projects.get(project_id)
           commits = project.commits.list(ref=default_branch, per_page=1)
           if commits:
               date = datetime.strptime(commits[0].committed_date, '%Y-%m-%dT%H:%M:%S.%fZ')
               return date.strftime('%Y-%m-%d %H:%M:%S')
           return 'N/A'
       except:
           return 'N/A'

   def get_last_pipeline_date(self, project_id: int) -> str:
       try:
           project = self.gl.projects.get(project_id)
           pipelines = project.pipelines.list(per_page=1)
           if pipelines:
               date = datetime.strptime(pipelines[0].created_at, '%Y-%m-%dT%H:%M:%S.%fZ')
               return date.strftime('%Y-%m-%d %H:%M:%S')
           return 'N/A'
       except:
           return 'N/A'
   
   def scan_group(self, group_id: int) -> Dict[str, List[Dict]]:
       results = {}
       group = self.gl.groups.get(group_id)
       
       for project in group.projects.list(all=True):
           default_branch = self.get_default_branch(project.id)
           namespace = project.namespace['full_path']
           
           if namespace not in results:
               results[namespace] = []
               
           project_info = {
               'url': project.web_url,
               'name': project.name,
               'default_branch': default_branch,
               'sizes': self.get_project_size(project.id),
               'has_ci': self.has_ci_file(project.id, default_branch),
               'last_commit': self.get_last_commit_date(project.id, default_branch),
               'last_pipeline': self.get_last_pipeline_date(project.id),
               'comments': ''
           }
           results[namespace].append(project_info)
           
       for subgroup in group.subgroups.list(all=True):
           sub_results = self.scan_group(subgroup.id)
           results.update(sub_results)
           
       return results

def generate_html_report(results: Dict[str, List[Dict]], output_file: str = 'report.html'):
   with open('style.html', 'w') as f:
       f.write("""
<!DOCTYPE html>
<html>
<head>
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
       }
       .group-content {
           margin-left: 20px;
           display: none;
       }
       .table-responsive {
           margin: 20px 0;
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
       <div class="group-header" onclick="toggleGroup(this)">
           <i class="fas fa-chevron-right"></i> {{ namespace }}
       </div>
       <div class="group-content">
           <div class="table-responsive">
               <table class="table table-striped table-bordered" data-namespace="{{ namespace }}">
                   <thead>
                       <tr>
                           <th>Project</th>
                           <th>Default Branch</th>
                           <th>Repository Size</th>
                           <th>Storage Size</th>
                           <th>CI Config</th>
                           <th>Last Commit</th>
                           <th>Last Pipeline</th>
                           <th>Comments</th>
                       </tr>
                   </thead>
                   <tbody>
                       {% for project in projects %}
                       <tr>
                           <td><a href="{{ project.url }}">{{ project.name }}</a></td>
                           <td>{{ project.default_branch }}</td>
                           <td class="size-cell">{{ (project.sizes.repository_size / 1024 / 1024) | round(2) }} MB</td>
                           <td class="size-cell">{{ (project.sizes.storage_size / 1024 / 1024) | round(2) }} MB</td>
                           <td>{{ 'Yes' if project.has_ci else 'No' }}</td>
                           <td class="date-cell">{{ project.last_commit }}</td>
                           <td class="date-cell">{{ project.last_pipeline }}</td>
                           <td><textarea class="form-control">{{ project.comments }}</textarea></td>
                       </tr>
                       {% endfor %}
                   </tbody>
               </table>
           </div>
       </div>
   </div>
   {% endfor %}
   
   <script>
   function toggleGroup(header) {
       const content = header.nextElementSibling;
       content.style.display = content.style.display === 'none' ? 'block' : 'none';
       
       if (content.style.display === 'block') {
           const table = content.querySelector('table');
           if (!$.fn.DataTable.isDataTable(table)) {
               $(table).DataTable({
                   "pageLength": 25,
                   "order": [[0, "asc"]]
               });
           }
       }
   }
   
   document.addEventListener('DOMContentLoaded', function() {
       // Open first group by default
       const firstHeader = document.querySelector('.group-header');
       if (firstHeader) {
           toggleGroup(firstHeader);
       }
   });
   </script>
</body>
</html>
       """)
       
   env = jinja2.Environment()
   with open('style.html', 'r') as f:
       template = env.from_string(f.read())
       
   html = template.render(results=results)
   
   with open(output_file, 'w') as f:
       f.write(html)

def main():
   parser = argparse.ArgumentParser()
   parser.add_argument('--token', required=True)
   parser.add_argument('--group-id', type=int, required=True)
   parser.add_argument('--gitlab-url', default='https://gitlab.com')
   args = parser.parse_args()

   scanner = GitLabScanner(args.token, args.gitlab_url)
   results = scanner.scan_group(args.group_id)
   generate_html_report(results)

if __name__ == '__main__':
   main()
