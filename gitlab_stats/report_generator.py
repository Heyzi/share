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
<link href="https://cdn.datatables.net/fixedheader/3.2.2/css/fixedHeader.dataTables.min.css" rel="stylesheet">
<script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
<script src="https://cdn.datatables.net/1.11.5/js/jquery.dataTables.min.js"></script>
<script src="https://cdn.datatables.net/1.11.5/js/dataTables.bootstrap5.min.js"></script>
<script src="https://cdn.datatables.net/fixedheader/3.2.2/js/dataTables.fixedHeader.min.js"></script>
<style>.summary-card{margin:20px 0;padding:20px;background-color:#f8f9fa;border-radius:5px}
.size-cell{white-space:nowrap}.date-cell{white-space:nowrap}
.branch-cell{max-width:100px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.project-url{word-break:break-all}thead{position:sticky;top:0;background:white;z-index:10}
.dataTables_filter{float:right;margin-bottom:20px}.dataTables_filter input{width:300px}
thead input{width:100%;padding:3px;box-sizing:border-box;margin-top:5px}</style></head>
<body class="container-fluid"><div class="summary-card"><h2>Projects Report - {{ summary.scan_timestamp }}</h2>
<div class="row"><div class="col">
<p><strong>Initial/Final Projects:</strong> {{ summary.initial_project_count }}/{{ summary.total_projects }}</p>
<p><strong>Projects with CI:</strong> {{ summary.projects_with_ci }} 
({{ (summary.projects_with_ci / summary.total_projects * 100) | round(1) }}%)</p></div>
<div class="col"><p><strong>Total Repository Size:</strong> {{ format_size(summary.total_repo_size) }}</p>
<p><strong>Total Storage Size:</strong> {{ format_size(summary.total_storage_size) }}</p>
<p><strong>Total Artifacts Size:</strong> {{ format_size(summary.total_artifacts_size) }}</p>
</div></div></div><div class="table-responsive">
<table id="projectsTable" class="table table-striped table-bordered">
<thead><tr><th>#</th><th>Namespace</th><th>Project</th><th>URL</th><th>Branch</th>
<th>Repository Size</th><th>Storage Size</th><th>Artifacts Size</th>
<th>CI Config</th><th>Last Commit</th><th>Last Pipeline</th></tr></thead>
<tbody>{% for namespace, projects in results.items() %}
{% for project in projects %}<tr><td>{{ loop.index }}</td><td>{{ namespace }}</td>
<td>{{ project.name }}</td><td class="project-url"><a href="{{ project.url }}">{{ project.url }}</a></td>
<td class="branch-cell">{{ project.branch }}</td>
<td class="size-cell">{{ format_size(project.sizes.repository_size) }}</td>
<td class="size-cell">{{ format_size(project.sizes.storage_size) }}</td>
<td class="size-cell">{{ format_size(project.sizes.artifacts_size) }}</td>
<td>{{ 'Yes' if project.has_ci else 'No' }}</td>
<td class="date-cell">{{ project.last_commit }}</td>
<td class="date-cell">{{ project.last_pipeline }}</td>
</tr>{% endfor %}{% endfor %}</tbody></table></div>
<script>$(document).ready(function(){$('#projectsTable').DataTable({
paging:false,ordering:true,info:true,searching:true,orderCellsTop:true,
fixedHeader:true,search:{regex:true,smart:false},
columnDefs:[{targets:[5,6,7],type:'num',render:function(data,type){
if(type==='sort')return parseFloat(data.replace(/[^0-9.]/g,''))*(data.includes('GB')?1024:1);
return data;}},{targets:[9,10],type:'date'}],
initComplete:function(){this.api().columns().every(function(){let column=this;
let title=$(column.header()).text();$('<input type="text" placeholder="Filter '+title+'" />')
.appendTo($(column.header())).on('keyup change',function(){
if(column.search()!==this.value)column.search(this.value,true,false).draw();});});}});});</script>
</body></html>"""

def generate_report(projects: Dict[str, List[Dict]], summary: Dict[str, int], output_base: str):
   if 'html' in output_base:
       env = jinja2.Environment()
       env.filters['format_size'] = format_size
       html = env.from_string(template).render(results=projects, summary=summary, format_size=format_size)
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

def main():
   parser = argparse.ArgumentParser(description='Generate GitLab projects report')
   parser.add_argument('--token', required=True, help='GitLab API token')
   parser.add_argument('--group-id', type=int, required=True, help='GitLab group ID')
   parser.add_argument('--gitlab-url', default='https://gitlab.com', help='GitLab URL')
   parser.add_argument('--format', choices=['html', 'csv', 'both'], default='both', help='Output format')
   args = parser.parse_args()

   scanner = GitLabScanner(args.token, args.gitlab_url)
   results, summary = scanner.scan_group(args.group_id)
   generate_report(results, summary, f"report-{args.format}")

if __name__ == '__main__':
   main()
