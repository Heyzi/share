import gitlab, argparse, logging, sys, csv, jinja2
from typing import Dict, List, Tuple
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GitLabScanner:
    def __init__(self, token: str, url: str):
        self.gl = gitlab.Gitlab(url, private_token=token, per_page=100)
    
    def get_project_info(self, project_id: int, project, namespace: str) -> Dict:
        try:
            stats = self.gl.projects.get(project_id, statistics=True).statistics
            default_branch = project.default_branch or 'master'
            has_ci = bool(project.files.get('.gitlab-ci.yml', ref=default_branch))
            commits = project.commits.list(page=1, per_page=1)
            pipelines = project.pipelines.list(page=1, per_page=1)
            
            return {
                'namespace': namespace,
                'name': project.name,
                'url': project.web_url,
                'branch': default_branch,
                'repository_size': stats.get('repository_size', 0),
                'storage_size': stats.get('storage_size', 0),
                'artifacts_size': stats.get('job_artifacts_size', 0),
                'has_ci': has_ci,
                'last_commit': commits[0].committed_date.split('.')[0].replace('T', ' ') if commits else 'N/A',
                'last_pipeline': pipelines[0].created_at.split('.')[0].replace('T', ' ') if pipelines else 'N/A'
            }
        except Exception as e:
            logger.error(f"Error getting info for project {project_id}: {str(e)}")
            return None
            
    def scan_group(self, group_id: int) -> Tuple[List[Dict], Dict[str, int]]:
        initial_count = 0
        projects_info = []
        summary = {
            'total_projects': 0, 'total_repo_size': 0, 'total_storage_size': 0,
            'total_artifacts_size': 0, 'projects_with_ci': 0,
            'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            def scan_recursive(group_id):
                group = self.gl.groups.get(group_id)
                nonlocal initial_count
                
                for project in group.projects.list(all=True):
                    initial_count += 1
                    project_info = self.get_project_info(project.id, project, project.namespace['full_path'])
                    if project_info:
                        projects_info.append(project_info)
                        summary['total_projects'] += 1
                        summary['total_repo_size'] += project_info['repository_size']
                        summary['total_storage_size'] += project_info['storage_size']
                        summary['total_artifacts_size'] += project_info['artifacts_size']
                        if project_info['has_ci']:
                            summary['projects_with_ci'] += 1

                for subgroup in group.subgroups.list(all=True):
                    scan_recursive(subgroup.id)

            scan_recursive(group_id)
            summary['initial_project_count'] = initial_count
            
        except Exception as e:
            logger.error(f"Error scanning group {group_id}: {str(e)}")
            
        return projects_info, summary

def format_size(size_bytes: int) -> str:
    gb = size_bytes / (1024 * 1024 * 1024)
    return f"{gb:.2f} GB" if gb >= 1 else f"{(size_bytes / 1024 / 1024):.2f} MB"
template = """
<!DOCTYPE html>
<html>
<head>
   <meta charset="utf-8">
   <title>GitLab Projects Report</title>
   <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
   <link href="https://cdn.datatables.net/1.11.5/css/dataTables.bootstrap5.min.css" rel="stylesheet">
   <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
   <script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
   <script src="https://cdn.datatables.net/1.11.5/js/dataTables.bootstrap5.min.js"></script>
   <style>
       .summary-card {margin: 20px 0; padding: 20px; background-color: #f8f9fa; border-radius: 5px;}
       .size-cell {white-space: nowrap;}
       .date-cell {white-space: nowrap;}
       .branch-cell {max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;}
       .project-url {word-break: break-all;}
       thead {position: sticky; top: 0; background: white;}
   </style>
</head>
<body class="container-fluid">
   <div class="summary-card">
       <h2>Projects Report - {{ summary.scan_timestamp }}</h2>
       <div class="row">
           <div class="col">
               <p><strong>Initial/Final Projects:</strong> {{ summary.initial_project_count }}/{{ summary.total_projects }}</p>
               <p><strong>Projects with CI:</strong> {{ summary.projects_with_ci }} 
                   ({{ (summary.projects_with_ci / summary.total_projects * 100) | round(1) }}%)</p>
           </div>
           <div class="col">
               <p><strong>Total Repository Size:</strong> {{ format_size(summary.total_repo_size) }}</p>
               <p><strong>Total Storage Size:</strong> {{ format_size(summary.total_storage_size) }}</p>
               <p><strong>Total Artifacts Size:</strong> {{ format_size(summary.total_artifacts_size) }}</p>
           </div>
       </div>
   </div>

   <div class="table-responsive">
       <table class="table table-striped table-bordered" id="projectsTable">
           <thead>
               <tr>
                   <th>#</th>
                   <th>Namespace</th>
                   <th>Project</th>
                   <th>URL</th>
                   <th>Branch</th>
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
                   <td>{{ loop.index }}</td>
                   <td>{{ project.namespace }}</td>
                   <td>{{ project.name }}</td>
                   <td class="project-url"><a href="{{ project.url }}">{{ project.url }}</a></td>
                   <td class="branch-cell">{{ project.branch }}</td>
                   <td class="size-cell">{{ format_size(project.repository_size) }}</td>
                   <td class="size-cell">{{ format_size(project.storage_size) }}</td>
                   <td class="size-cell">{{ format_size(project.artifacts_size) }}</td>
                   <td>{{ 'Yes' if project.has_ci else 'No' }}</td>
                   <td class="date-cell">{{ project.last_commit }}</td>
                   <td class="date-cell">{{ project.last_pipeline }}</td>
               </tr>
               {% endfor %}
           </tbody>
       </table>
   </div>
   
   <script>
   $(document).ready(function() {
       $('#projectsTable').DataTable({
           paging: false,
           ordering: true,
           info: true,
           searching: true,
           columnDefs: [{
               targets: [5, 6, 7],
               render: function(data, type) {
                   if (type === 'sort') {
                       return parseFloat(data.replace(/[^0-9.]/g, '')) * (data.includes('GB') ? 1024 : 1);
                   }
                   return data;
               }
           }]
       });
   });
   </script>
</body>
</html>
"""

def generate_report(projects: List[Dict], summary: Dict[str, int], output_base: str):
   if 'html' in output_base:
       env = jinja2.Environment()
       env.filters['format_size'] = format_size
       html = env.from_string(template).render(projects=projects, summary=summary, format_size=format_size)
       with open(f"{output_base}.html", 'w', encoding='utf-8-sig' if sys.platform == 'win32' else 'utf-8') as f:
           f.write(html)

   if 'csv' in output_base:
       with open(f"{output_base}.csv", 'w', newline='', encoding='utf-8-sig') as f:
           writer = csv.writer(f)
           writer.writerow(['Scan Time', summary['scan_timestamp']])
           writer.writerow(['Initial/Final Projects', f"{summary['initial_project_count']}/{summary['total_projects']}"])
           for k in ['total_repo_size', 'total_storage_size', 'total_artifacts_size']:
               writer.writerow([k.replace('_', ' ').title(), format_size(summary[k])])
           writer.writerow([])
           writer.writerow(['#', 'Namespace', 'Project', 'URL', 'Branch', 'Repository Size', 
                          'Storage Size', 'Artifacts Size', 'CI Config', 'Last Commit', 'Last Pipeline'])
           for i, p in enumerate(projects, 1):
               writer.writerow([i, p['namespace'], p['name'], p['url'], p['branch'],
                              format_size(p['repository_size']), format_size(p['storage_size']),
                              format_size(p['artifacts_size']), 'Yes' if p['has_ci'] else 'No',
                              p['last_commit'], p['last_pipeline']])

def main():
   parser = argparse.ArgumentParser(description='Generate GitLab projects report')
   parser.add_argument('--token', required=True, help='GitLab API token')
   parser.add_argument('--group-id', type=int, required=True, help='GitLab group ID')
   parser.add_argument('--gitlab-url', default='https://gitlab.com', help='GitLab URL')
   parser.add_argument('--format', choices=['html', 'csv', 'both'], default='both', help='Output format')
   args = parser.parse_args()

   scanner = GitLabScanner(args.token, args.gitlab_url)
   projects, summary = scanner.scan_group(args.group_id)
   generate_report(projects, summary, f"report-{args.format}")

if __name__ == '__main__':
   main()   
