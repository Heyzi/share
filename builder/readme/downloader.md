# GitLab Artifact Downloader

A tool for downloading build artifacts from GitLab CI pipelines with support for multiple download modes and error handling.

## Features

- Downloads artifacts from GitLab CI jobs
- Supports multiple download modes:
 - Single job by ID
 - Job by name and branch
 - Batch downloads via config file
- Automatic branch fallback
- Retries on download failures
- Normalizes output filenames
- Supports both single tasks and batch operations
- Configurable output directory
- Verbose logging option

## Requirements

- Python 3.x
- GitLab access token with appropriate permissions
- Internet access to GitLab instance

## Usage

Basic command:
```
python3 artifact_downloader.py --url https://gitlab.com --token YOUR_TOKEN [OPTIONS]
```

Download modes:

1. Using config file:
```
python3 artifact_downloader.py --url GITLAB_URL --token TOKEN --config tasks.json
```

2. Single job by ID:
```
python3 artifact_downloader.py --url GITLAB_URL --token TOKEN --project-id 123 --job-id 456
```

3. Job by name and branch:
```
python3 artifact_downloader.py --url GITLAB_URL --token TOKEN --project-id 123 --job-name build --branch main
```

Arguments:
- --url: GitLab instance URL
- --token: Private token for authentication
- --config: Path to JSON configuration file
- --project-id: GitLab project ID
- --job-id: Specific job ID to download
- --job-name: Name of job to download
- --branch: Branch name (optional)
- --fallback-to-default: Fallback to default branch if specified branch not found
- --output-dir: Directory for downloaded artifacts (default: ./artifacts)
- --verbose: Enable verbose logging

## Configuration Format

JSON configuration structure:
```
{
 "version": "1.0",
 "tasks": [
   {
     "extension_name": "extension1",
     "project_id": 123,
     "job_name": "build",
     "branch": "main",
     "tags": ["tag1", "tag2"],
     "fallback_to_default_branch": false
   }
 ]
}
```

## Output Format

Downloaded artifacts are named using the pattern:
```
{name}_pipeline{pipeline_id}_job{job_id}_branch-{branch}.zip
```

## Maintenance Guide

### Adding New Task Parameters

1. Update TaskConfig dataclass:
```
@dataclass
class TaskConfig:
   # ... existing fields ...
   new_parameter: str
```

2. Update config loading in _load_tasks:
```
return [TaskConfig(**{
   **task_data,
   'new_parameter': task_data.get('new_parameter', default_value)
}) for task_data in config_data['tasks']]
```

### Modifying Download Behavior

Update download_artifact method in GitLabClient:
```
def download_artifact(self, project_id: int, job_id: int, output_path: Path) -> None:
   # Add new download parameters
   # Modify retry logic
   # Add new error handling
```

### Adding New Output Formats

Modify format_output_path in ArtifactDownloader:
```
def format_output_path(self, name: str, job_info: Dict[str, Any]) -> Path:
   # Add new naming patterns
   # Add new metadata to filename
   return path
```

### Modifying Branch Handling

Update _normalize_branch_name in ArtifactDownloader:
```
def _normalize_branch_name(self, branch: str) -> str:
   # Add new normalization rules
   # Modify character replacements
   return normalized_branch
```

### Adding New API Features

1. Add new method to GitLabClient:
```
def new_api_call(self, params: Dict[str, Any]) -> Any:
   return self._make_request('new/endpoint', params)
```

2. Use in ArtifactDownloader:
```
def new_feature(self, params: Dict[str, Any]) -> Any:
   return self.client.new_api_call(params)
```