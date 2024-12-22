#!/usr/bin/env python3

import sys
import json
import urllib.request
import urllib.error
import logging
import argparse
import time
import ssl
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

# Configure logging to write to stdout
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s',
                                    datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

def get_ssl_context():
    """Create SSL context for API requests."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = True
    return ctx

class DownloadError(Exception): pass
class ConfigurationError(Exception): pass

@dataclass
class TaskConfig:
    """Configuration for a single artifact download task."""
    extension_name: str
    project_id: int
    job_name: str
    branch: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.tags is None:
            self.tags = []
        if self.project_id <= 0:
            raise ValueError("project_id must be positive")
        if not self.extension_name or not self.extension_name.strip():
            raise ValueError("extension_name cannot be empty")
        self.extension_name = self.extension_name.strip()

@dataclass
class Config:
    """Base configuration container."""
    version: str
    generated_at: datetime
    tasks: List[TaskConfig]

class GitLabClient:
    """Client for interacting with GitLab API."""

    def __init__(self, base_url: str, token: str):
        """Initialize GitLab client with base URL and authentication token."""
        self.base_url = base_url.rstrip('/')
        if not self.base_url.endswith('/api/v4'):
            self.base_url = f"{self.base_url}/api/v4"
        self.headers = {
            'PRIVATE-TOKEN': token,
            'Accept': 'application/json'
        }

    def _get_paginated_results(self, endpoint: str, params: Optional[Dict] = None) -> List[Any]:
        """Get all results using pagination."""
        if params is None:
            params = {}

        page = 1
        results = []

        while True:
            page_params = {**params, 'page': page, 'per_page': 100}
            page_results = self._make_request(endpoint, page_params)

            if not page_results:
                break

            results.extend(page_results)

            if len(page_results) < 100:
                break

            page += 1

        return results

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        """Make authenticated request to GitLab API."""
        url = f"{self.base_url}/{endpoint}"
        if '/api/v4/api/v4' in url:
            url = url.replace('/api/v4/api/v4', '/api/v4')

        if params:
            query_string = '&'.join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query_string}"

        request = urllib.request.Request(url, headers=self.headers)

        try:
            ctx = get_ssl_context()
            with urllib.request.urlopen(request, context=ctx) as response:
                return json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code in [401, 403, 404]:
                errors = {401: "Unauthorized", 403: "Forbidden", 404: "Not found"}
                raise DownloadError(f"{errors[e.code]}: {endpoint}")
            raise DownloadError(f"HTTP error: {e.code}")
        except Exception as e:
            raise DownloadError(f"API error: {str(e)}")

    def check_connection(self) -> bool:
        """Test GitLab API connectivity."""
        try:
            self._make_request('projects', {'per_page': 1})
            return True
        except DownloadError as e:
            if "Unauthorized" in str(e):
                raise DownloadError("Invalid or expired GitLab token")
            raise

    def get_default_branch(self, project_id: int) -> str:
        """Get default branch name for a project."""
        try:
            project = self._make_request(f'projects/{project_id}')
            return project.get('default_branch', 'master')
        except Exception:
            return 'master'

    def get_job_info(self, project_id: int, job_id: Optional[int] = None,
                 job_name: Optional[str] = None, branch: Optional[str] = None) -> Dict[str, Any]:
        """Get information about latest successful job from a pipeline."""
        if job_id:
            job_info = self._make_request(f'projects/{project_id}/jobs/{job_id}')
            return {
                'job_id': job_id,
                'pipeline_id': job_info['pipeline']['id'],
                'branch': job_info['ref'],
                'created_at': job_info['created_at'],
                'web_url': job_info['web_url']
            }

        params = {'order_by': 'id', 'sort': 'desc'}
        if branch:
            params['ref'] = branch

        pipelines = self._get_paginated_results(
            f'projects/{project_id}/pipelines',
            params
        )[:20]  # Limit to last 20 pipelines

        if not pipelines:
            raise DownloadError(f"No pipelines found in branch '{branch}'")

        for pipeline in pipelines:
            jobs = self._get_paginated_results(
                f'projects/{project_id}/pipelines/{pipeline["id"]}/jobs'
            )

            matching_jobs = [j for j in jobs if j['name'] == job_name and j['status'] == 'success']

            if matching_jobs:
                job_info = self._make_request(f'projects/{project_id}/jobs/{matching_jobs[0]["id"]}')
                return {
                    'job_id': matching_jobs[0]['id'],
                    'pipeline_id': pipeline['id'],
                    'branch': branch or pipeline['ref'],
                    'created_at': pipeline['created_at'],
                    'web_url': job_info['web_url']
                }

        raise DownloadError(f"No successful jobs '{job_name}' found")

    def download_artifact(self, project_id: int, job_id: int, output_path: Path) -> None:
        """Download job artifacts to specified path."""
        url = f"{self.base_url}/projects/{project_id}/jobs/{job_id}/artifacts"
        request = urllib.request.Request(url, headers=self.headers)
        ctx = get_ssl_context()

        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, context=ctx) as response:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, 'wb') as f:
                        while True:
                            chunk = response.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
                return
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise DownloadError("Artifacts not found")
                if attempt == 2:
                    raise
                time.sleep(min(4 * (2 ** attempt), 10))

class ArtifactDownloader:
    """High-level interface for downloading GitLab artifacts."""

    def __init__(self, gitlab_url: str, token: str, output_dir: Path):
        """Initialize downloader with GitLab URL, token and output directory."""
        self.client = GitLabClient(gitlab_url, token)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def format_output_path(self, name: str, job_info: Dict[str, Any]) -> Path:
        """Generate output path for artifact file."""
        safe_name = "".join(c for c in name if c.isalnum() or c in ('-', '_'))
        branch = job_info.get('branch', 'unknown')
        pipeline_id = job_info.get('pipeline_id')
        job_id = job_info.get('job_id')
        return self.output_dir / f"{safe_name}_pipeline{pipeline_id}_job{job_id}_branch-{branch}.zip"

    def download_single(self, project_id: int, job_id: int) -> Dict[str, Any]:
        """Download artifacts from a single job."""
        try:
            self.client.check_connection()
            name = f"project_{project_id}"
            job_info = self.client.get_job_info(project_id, job_id=job_id)
            output_path = self.format_output_path(name, job_info)

            self.client.download_artifact(project_id, job_id, output_path)

            result = {
                'success': True,
                'extension_name': name,
                'output_path': str(output_path)
            }
            result.update(job_info)
            return result
        except Exception as e:
            return {
                'success': False,
                'extension_name': f"project_{project_id}",
                'error': str(e)
            }

    def process_task(self, task: TaskConfig) -> Dict[str, Any]:
        """Process single download task configuration."""
        try:
            branch = task.branch or self.client.get_default_branch(task.project_id)
            job_info = self.client.get_job_info(
                task.project_id,
                job_name=task.job_name,
                branch=branch
            )
            output_path = self.format_output_path(task.extension_name, job_info)

            logger.info(f"Downloading artifact for {task.extension_name}\n"
                       f"Job URL: {job_info['web_url']}")

            self.client.download_artifact(task.project_id, job_info['job_id'], output_path)

            result = {
                'success': True,
                'extension_name': task.extension_name,
                'output_path': str(output_path)
            }
            result.update(job_info)
            return result
        except Exception as e:
            return {
                'success': False,
                'extension_name': task.extension_name,
                'error': str(e)
            }

    def download_artifacts(self, config_path: Optional[Path] = None,
                         single_task: Optional[TaskConfig] = None) -> List[Dict[str, Any]]:
        """Download artifacts according to config file or single task."""
        if not (config_path or single_task):
            raise ConfigurationError("Either config_path or single_task required")

        if single_task:
            tasks = [single_task]
        else:
            if not config_path:
                raise ConfigurationError("Config path is required")
            try:
                config_data = json.loads(config_path.read_text())
                if not config_data.get('tasks'):
                    logger.info("No tasks in configuration file, nothing to download")
                    return []

                tasks = []
                for task_data in config_data['tasks']:
                    task_config = {
                        'extension_name': task_data['extension_name'],
                        'project_id': task_data['project_id'],
                        'job_name': task_data['job_name']
                    }
                    if 'branch' in task_data:
                        task_config['branch'] = task_data['branch']
                    if 'tags' in task_data:
                        task_config['tags'] = task_data['tags']

                    tasks.append(TaskConfig(**task_config))

            except Exception as e:
                raise ConfigurationError(f"Failed to load config: {str(e)}")

        self.client.check_connection()
        return [self.process_task(task) for task in tasks]

def main() -> int:
    """Main function that returns exit code."""
    parser = argparse.ArgumentParser(description='GitLab Artifact Downloader')
    parser.add_argument('--url', required=True, help='GitLab URL')
    parser.add_argument('--token', required=True, help='Private token')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--config', type=Path, help='Config JSON file')
    mode.add_argument('--project-id', help='Project ID')
    mode.add_argument('--job-id', help='Job ID')
    parser.add_argument('--job-name', help='Job name')
    parser.add_argument('--branch', help='Branch name')
    parser.add_argument('--output-dir', type=Path, default='./artifacts')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose output')

    args = parser.parse_args()
    logger.setLevel(logging.DEBUG if args.verbose else logging.INFO)

    try:
        downloader = ArtifactDownloader(args.url, args.token, args.output_dir)

        if args.config:
            results = downloader.download_artifacts(config_path=args.config)
        elif args.job_id:
            if not args.project_id:
                parser.error("--project-id required with --job-id")
            results = [downloader.download_single(int(args.project_id), int(args.job_id))]
        else:
            if not args.job_name:
                parser.error("--job-name required with --project-id")
            task = TaskConfig(
                extension_name=f"project_{args.project_id}",
                project_id=int(args.project_id),
                job_name=args.job_name,
                branch=args.branch
            )
            results = downloader.download_artifacts(single_task=task)

        for r in results:
            if r['success']:
                logger.info(f"Success: {r['extension_name']} downloaded to {r['output_path']}")
            else:
                logger.error(f"Failed: {r['extension_name']} - {r['error']}")

        return 1 if any(not r['success'] for r in results) else 0

    except DownloadError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        if args.verbose:
            logger.debug('', exc_info=True)
        return 1

if __name__ == '__main__':
    sys.exit(main())
