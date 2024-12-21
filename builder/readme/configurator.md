# Extension Task Generator

Utility for generating download tasks configuration for extensions based on tags and configuration files.

## Features

- Generates download tasks for extensions based on YAML configuration
- Filters extensions by tags
- Supports branch name validation and normalization
- Handles environment variable overrides
- Generates JSON output with download tasks
- Provides fallback to default branch options
- Validates configuration format and required fields

## Requirements

- Python 3.x
- Required packages: PyYAML

## Usage

Basic command:
```
python3 extension_task_generator.py --config path/to/config.yml --tags tag1,tag2 --output tasks.json
```

Arguments:
- --config: Path to YAML configuration file
- --tags: Comma-separated list of required tags (can be set via GITLAB_TAGS env var)
- --output: Path for generated JSON output file
- --verbose: Enable debug logging (optional)

## Configuration Format

YAML configuration structure:
```
version: "1.0"
fallback_to_default_branch: false  # global setting
extensions:
 extension1:
   id: 123
   branch: main
   tags: [tag1, tag2]
   build_configs:
     - job_name: build
       tags: [tag3]
 extension2:
   id: 456
   tags: [tag1]
   build_configs:
     - job_name: build
       tags: [tag2]
```

## Environment Variables

- EXTENSIONS_{NAME}_BRANCH: Override branch for specific extension
- GITLAB_TAGS: Default tags if not specified in command line
- GITLAB_FALLBACK_TO_DEFAULT: Override global fallback setting
- DOWNLOAD_INTERNAL_EXTENSIONS: Enable/disable downloads ('true'/'false')

## Output Format

Generated JSON structure:
```
{
 "version": "1.0",
 "generated_at": "2024-11-22T12:00:00Z",
 "tasks": [
   {
     "extension_name": "extension1",
     "project_id": 123,
     "job_name": "build",
     "branch": "main",
     "tags": ["tag1", "tag2", "tag3"],
     "fallback_to_default_branch": false
   }
 ]
}
```

## Maintenance Guide

### Adding New Configuration Fields

1. Add field to DownloadTask dataclass:
```
@dataclass
class DownloadTask:
   # ... existing fields ...
   new_field: str
```

2. Update to_dict method:
```
def to_dict(self) -> Dict[str, Any]:
   data = {
       # ... existing fields ...
       'new_field': self.new_field
   }
   return data
```

3. Update generate_tasks function:
```
tasks.append(DownloadTask(
   # ... existing fields ...
   new_field=ext.get('new_field', default_value)
))
```

### Modifying Tag Processing

Update filter_extensions method in ExtensionConfig class:
```
def filter_extensions(self, required_tags: Set[str]) -> List[Dict[str, Any]]:
   # Modify tag filtering logic
   all_tags = ext_tags | set(build.get('tags', []))
   if your_new_condition(all_tags, required_tags):
       # ... process extension
```

### Branch Name Validation

Modify validate_branch method in ExtensionConfig class:
```
def validate_branch(self, branch: str, ext_name: str) -> None:
   # Add new validation rules
   if new_condition(branch):
       logger.error(f"New validation error for {ext_name}")
       sys.exit(1)
```

### Configuration Validation

Update _validate_config method in ExtensionConfig class:
```
def _validate_config(self, config: Dict) -> None:
   # Add new required fields
   required = {'extensions', 'version', 'new_field'}
   # Add new validation rules
```
