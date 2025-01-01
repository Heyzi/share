import gitlab, argparse, logging, sys, csv, jinja2
from typing import Dict, List, Tuple
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class GitLabScanner:
   def __init__(self, token: str, url: str):
       logger.info(f"Connecting to GitLab instance: {url}")
       self.gl = gitlab.Gitlab(url, private_token=token, per_page=100)
   
   def get_default_branch(self, project_id: int) -> str:
       try:
           project = self.gl.projects.get(project_id)
           return project.default_branch or 'master'
       except Exception as e:
           logger.error(f"Error getting default branch for project {project_id}: {str(e)}")
           return 'master'
   
   def get_project_size(self, project_id: int) -> Dict[str, int]:
       try:
           project = self.gl.projects.get(project_id, statistics=True)
           stats = project.statistics
           return {
               'repository_size': stats.get('repository_size', 0),
               'storage_size': stats.get('storage_size', 0),
               'artifacts_size': stats.get('job_artifacts_size', 0)
           }
       except Exception as e:
           logger.error(f"Error getting size for project {project_id}: {str(e)}")
           return {'repository_size': 0, 'storage_size': 0, 'artifacts_size': 0}

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
           commits = project.commits.list(page=1, per_page=1)
           return commits[0].committed_date.split('.')[0].replace('T', ' ') if commits else 'N/A'
       except Exception as e:
           logger.error(f"Error getting last commit for project {project_id}: {str(e)}")
           return 'N/A'

   def get_last_pipeline_date(self, project_id: int) -> str:
       try:
           project = self.gl.projects.get(project_id)
           pipelines = project.pipelines.list(page=1, per_page=1)
           return pipelines[0].created_at.split('.')[0].replace('T', ' ') if pipelines else 'N/A'
       except:
           return 'N/A'
           
   def scan_group(self, group_id: int) -> Tuple[Dict[str, List[Dict]], Dict[str, int]]:
       initial_count = 0
       results = {}
       summary = {
           'total_projects': 0, 'total_repo_size': 0, 'total_storage_size': 0,
           'total_artifacts_size': 0, 'projects_with_ci': 0,
           'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
       }
       
       try:
           group = self.gl.groups.get(group_id)
           page = 1
           while True:
               projects = group.projects.list(page=page, per_page=100, get_all=True)
               if not projects:
                   break
               initial_count += len(projects)
                   
               for project in projects:
                   logger.info(f"Processing project: {project.name}")
                   namespace = project.namespace['full_path']
                   if namespace not in results:
                       results[namespace] = []
                       
                   default_branch = self.get_default_branch(project.id)
                   sizes = self.get_project_size(project.id)
                   has_ci = self.has_ci_file(project.id, default_branch)
                   
                   project_info = {
                       'url': project.web_url,
                       'name': project.name,
                       'branch': default_branch,
                       'sizes': sizes,
                       'has_ci': has_ci,
                       'last_commit': self.get_last_commit_date(project.id, default_branch),
                       'last_pipeline': self.get_last_pipeline_date(project.id)
                   }
                   results[namespace].append(project_info)
                   
                   summary['total_projects'] += 1
                   summary['total_repo_size'] += sizes['repository_size']
                   summary['total_storage_size'] += sizes['storage_size']
                   summary['total_artifacts_size'] += sizes['artifacts_size']
                   if has_ci:
                       summary['projects_with_ci'] += 1
                       
               page += 1
           
           page = 1
           while True:
               subgroups = group.subgroups.list(page=page, per_page=100, get_all=True)
               if not subgroups:
                   break
                   
               for subgroup in subgroups:
                   logger.info(f"Scanning subgroup: {subgroup.name}")
                   sub_results, sub_summary = self.scan_group(subgroup.id)
                   results.update(sub_results)
                   
                   for key in ['total_projects', 'total_repo_size', 'total_storage_size', 
                              'total_artifacts_size', 'projects_with_ci']:
                       summary[key] += sub_summary[key]
                   initial_count += sub_summary.get('initial_project_count', 0)
                       
               page += 1

           summary['initial_project_count'] = initial_count
               
       except Exception as e:
           logger.error(f"Error scanning group {group_id}: {str(e)}")
           
       return results, summary

def format_size(size_bytes: int) -> str:
   gb = size_bytes / (1024 * 1024 * 1024)
   return f"{gb:.2f} GB" if gb >= 1 else f"{(size_bytes / 1024 / 1024):.2f} MB"

template = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>GitLab Projects Report</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.datatables.net/1.11.5/css/dataTables.bootstrap5.min.css" rel="stylesheet">
<script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
<script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
<style>
body{background:#f3f4f6;color:#1f2937;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.s{margin:20px 0;padding:30px;background:#fff;border-radius:15px;box-shadow:0 1px 3px rgba(0,0,0,0.1)}
.s h2{color:#111827;font-weight:600;font-size:24px;margin-bottom:25px}
.s p{margin-bottom:12px;color:#4b5563}
.s b{color:#111827}
.table{background:#fff;border-radius:8px;box-shadow:0 1px 3px rgba(0,0,0,0.1)}
.table thead th{background:#f9fafb;color:#374151;font-weight:600;text-transform:uppercase;font-size:12px;letter-spacing:0.05em;border-bottom:2px solid #e5e7eb;position:sticky;top:0;z-index:1}
.table tbody tr:hover{background-color:#f9fafb}
.sz{white-space:nowrap;font-family:monospace;color:#4b5563}
.d{max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-family:monospace;color:#4b5563}
.p{font-family:monospace;color:#111827}
.p a{text-decoration:none;color:#059669}
.p a:hover{color:#047857}
td{vertical-align:middle !important;padding:12px !important}
.dtf{margin-bottom:20px}
.dataTables_filter input{border:1px solid #e5e7eb;border-radius:6px;padding:8px 12px;width:300px;outline:none}
.dataTables_filter input:focus{border-color:#059669;box-shadow:0 0 0 3px rgba(5,150,105,0.1)}
tr:hover .p a{opacity:1}
</style>
</head><body class="container-fluid py-4"><div class="s"><h2>Projects Report - {{summary.scan_timestamp}}</h2><div class="row">
<div class="col"><p><b>Projects:</b> {{summary.initial_project_count}}/{{summary.total_projects}}</p>
<p><b>With CI:</b> {{summary.projects_with_ci}} ({{(summary.projects_with_ci/summary.total_projects*100)|round(1)}}%)</p></div>
<div class="col"><p><b>Repo Size:</b> {{format_size(summary.total_repo_size)}}</p>
<p><b>Storage Size:</b> {{format_size(summary.total_storage_size)}}</p>
<p><b>Artifacts Size:</b> {{format_size(summary.total_artifacts_size)}}</p></div></div></div>
<div class="table-responsive"><table id="pt" class="table table-striped">
<thead><tr><th>#</th><th>Project</th><th>Branch</th><th>Repo Size</th><th>Storage</th>
<th>Artifacts</th><th>CI</th><th>Last Commit</th><th>Last Pipeline</th></tr></thead><tbody>
{% for namespace, projects in results.items() %}{% for project in projects %}<tr><td>{{loop.index}}</td>
<td class="p"><a href="{{project.url}}">{{namespace}}/{{project.name}}</a></td>
<td class="d">{{project.branch}}</td><td class="sz">{{format_size(project.sizes.repository_size)}}</td>
<td class="sz">{{format_size(project.sizes.storage_size)}}</td>
<td class="sz">{{format_size(project.sizes.artifacts_size)}}</td>
<td>{{ 'Yes' if project.has_ci else 'No' }}</td><td class="sz">{{project.last_commit}}</td>
<td class="sz">{{project.last_pipeline}}</td></tr>{% endfor %}{% endfor %}</tbody></table></div>
<script>$(document).ready(function(){var t=$('#pt').DataTable({paging:false,ordering:true,info:true,search:{return:true,smart:false},
columnDefs:[{targets:[3,4,5],type:'num',render:function(d,t){if(t==='sort')return parseFloat(d.replace(/[^0-9.]/g,''))*(d.includes('GB')?1024:1);return d;}},
{targets:[7,8],type:'date'}]});$('.dtf input').attr('placeholder','Global Search...').addClass('form-control');});</script></body></html>"""

def generate_report(projects: Dict[str, List[Dict]], summary: Dict[str, int], output_base: str):
   try:
       env = jinja2.Environment()
       env.filters['format_size'] = format_size
       html = env.from_string(template).render(results=projects, summary=summary, format_size=format_size)
       with open(f"{output_base}.html", 'w', encoding='utf-8-sig' if sys.platform == 'win32' else 'utf-8') as f:
           f.write(html)
           
       with open(f"{output_base}.csv", 'w', newline='', encoding='utf-8-sig' if sys.platform == 'win32' else 'utf-8') as f:
           writer = csv.writer(f)
           writer.writerow(['Scan Time', summary['scan_timestamp']])
           writer.writerow(['Initial/Final Projects', f"{summary['initial_project_count']}/{summary['total_projects']}"])
           writer.writerow(['Total Repository Size', format_size(summary['total_repo_size'])])
           writer.writerow(['Total Storage Size', format_size(summary['total_storage_size'])])
           writer.writerow(['Total Artifacts Size', format_size(summary['total_artifacts_size'])])
           writer.writerow([])
           writer.writerow(['#', 'Namespace', 'Project', 'URL', 'Branch', 'Repository Size', 
                          'Storage Size', 'Artifacts Size', 'CI Config', 'Last Commit', 'Last Pipeline'])
           index = 1
           for namespace, projects in projects.items():
               for project in projects:
                   writer.writerow([index, namespace, project['name'], project['url'], project['branch'],
                                  format_size(project['sizes']['repository_size']),
                                  format_size(project['sizes']['storage_size']),
                                  format_size(project['sizes']['artifacts_size']),
                                  'Yes' if project['has_ci'] else 'No',
                                  project['last_commit'], project['last_pipeline']])
                   index += 1
   except Exception as e:
       logger.error(f"Error generating reports: {str(e)}")

def main():
   parser = argparse.ArgumentParser(description='Generate GitLab projects report')
   parser.add_argument('--token', required=True, help='GitLab API token')
   parser.add_argument('--group-id', type=int, required=True, help='GitLab group ID')
   parser.add_argument('--gitlab-url', default='https://gitlab.com', help='GitLab URL')
   args = parser.parse_args()

   scanner = GitLabScanner(args.token, args.gitlab_url)
   results, summary = scanner.scan_group(args.group_id)
   generate_report(results, summary, "report")

if __name__ == '__main__':
   main()
