# GitLab Artifact Downloader Guide

## Overview
Tool for downloading artifacts from GitLab CI jobs. Supports both single job downloads and batch processing via configuration file.

## Command Line Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| --url | Yes | GitLab instance URL |
| --token | Yes | GitLab private token |
| --config | One of these three | Path to JSON config file |
| --project-id | One of these three | Project ID for direct download |
| --job-id | One of these three | Specific job ID to download |
| --job-name | With --project-id | Job name for latest artifact |
| --branch | No | Branch name (default: project default) |
| --output-dir | No | Output directory (default: ./artifacts) |
| --verbose | No | Enable debug logging |

**Notes**:
- One of these must be specified: `--config`, `--project-id`, or `--job-id`
- When using `--project-id`, `--job-name` is required
- When using `--job-id`, `--project-id` is required

## Usage Examples

### 1. Configuration File Mode
Download artifacts using JSON configuration:

```bash
python artifact_downloader.py \
  --url https://gitlab.example.com \
  --token <your_token> \
  --config path/to/config.json \
  --output-dir ./artifacts
```

### 2. Single Job Mode
Download artifacts by specific job ID:

```bash
python artifact_downloader.py \
  --url https://gitlab.example.com \
  --token <your_token> \
  --project-id 123 \
  --job-id 456
```

### 3. Latest Job Mode
Download latest successful job artifacts:

```bash
python artifact_downloader.py \
  --url https://gitlab.example.com \
  --token <your_token> \
  --project-id 123 \
  --job-name "build" \
  --branch "main"
```

## Configuration Format

Example JSON configuration:
```json
{
  "version": "1.0",
  "generated_at": "2024-12-22T12:00:00Z",
  "tasks": [
    {
      "extension_name": "test-extension",
      "project_id": 4,
      "job_name": "build-job",
      "branch": "main",
      "tags": ["windows", "x64"]
    }
  ]
}
```

## Output Structure
Artifacts are saved as:
```
{output_dir}/{extension_name}_pipeline{pipeline_id}_job{job_id}_branch-{branch}.zip
```

