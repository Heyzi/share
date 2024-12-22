# Extension Configuration Guide

## Overview
System for configuring multi-platform pipeline extensions with flexible branch management and build specifications. The system filters extensions based on required tags and generates task configurations.

## Core Features
- Flexible branch management with priority system
- Tag-based extension filtering
- Multi-platform build configurations
- JSON task generation
- Explicit extension inclusion
- Detailed logging

## Command Line Usage
```bash
python3 extension_task_generator.py --config path/to/config.yml --tags tag1,tag2 --output tasks.json [options]
```

### Arguments
- `--config` [Required]: Path to YAML configuration file
- `--tags` [Required]: Comma-separated list of required tags for filtering
- `--output` [Required]: Path for generated JSON task file
- `--include-extensions` [Optional]: Comma-separated list of extensions to include if they have at least one matching tag
- `--verbose` [Optional]: Enable debug logging

## Branch Management
### Priority Order
1. `EXTENSIONS_GLOBAL_BRANCH` environment variable
2. `global_branch` from configuration file  
3. `EXTENSIONS_{NAME}_BRANCH` environment variable
4. Extension's `branch` field in configuration

### Branch Name Constraints
- Maximum length: 255 characters
- Pattern: `^[a-zA-Z0-9\-_./]+$`
- Cannot:
  - Start with '-'
  - End with '.lock'
  - Contain: `\ * ? [ ] ^ ~ : <space> \t ( ) # @`

## Configuration Format
### Basic Structure
```yaml
version: "1"                # [Required] Must be "1"
global_branch: master       # [Optional] Default branch
extensions:                 # [Required] Container
  extension-name:          # Extension identifier
    id: <number>          # [Required] Unique numeric ID
    repo: <url>           # Repository URL
    description: <text>   # Extension description
    branch: <string>      # [Optional] Branch override
    tags: [...]          # [Required] Feature tags
    build_configs:        # [Required] Build array
      - job_name: <name> # [Required] CI job name
        tags: [...]      # [Required] Platform tags
```

### Extension Tags
Product/feature identification at extension level:
```yaml
tags: [java, python]          # Technology stack
tags: [test_tag1, test_tag2]  # Feature set
```

### Build Tags
Platform requirements at build level:
```yaml
tags: [windows, x64]                    # Single platform
tags: [linux, arm64, windows, x86]      # Multi-platform
```

## Examples
### Basic Extension
```yaml
version: "1"
extensions:
  test-extension:
    id: 4
    repo: http://gitlab.my/main/pipeline_tester
    description: "Processing extension"
    tags: [java, python]
    build_configs:
      - job_name: build-job
        tags: [windows, x64]
```

### Multi-Platform Extension
```yaml
version: "1"
extensions:
  cross-platform:
    id: 5
    repo: http://gitlab.my/main/universal
    description: "Multi-platform processor"
    tags: [java, python]
    build_configs:
      - job_name: build_multi
        tags: [linux, arm64, windows, x86]
      - job_name: build_x64
        tags: [windows, x64, linux, x64]
```

## Output Format
Generated JSON task configuration:
```json
{
  "version": "1.0",
  "generated_at": "2024-11-22T12:00:00Z",
  "tasks": [
    {
      "extension_name": "test-extension",
      "project_id": 4,
      "job_name": "build-job",
      "branch": "feature/branch",  // Optional
      "tags": ["windows", "x64"]   // Optional
    }
  ]
}
```

## System Constraints
### Uniqueness
- Extension IDs must be unique
- Extension names must be unique
- Combination of project ID and job name must be unique across all tasks

### Required Fields
- `version`
- Extension: `id`, `tags`
- Build: `job_name`, `tags`

### Optional Fields
- `global_branch`
- Extension: `branch`, `repo`, `description`

## Environment Variables
```bash
# Global branch setting
EXTENSIONS_GLOBAL_BRANCH=main

# Extension specific branch
EXTENSIONS_TEST_EXTENSION_BRANCH=develop

# Build control
DOWNLOAD_INTERNAL_EXTENSIONS=true  # Enable/disable builds

# Alternative way to specify required tags
GITLAB_TAGS=tag1,tag2
```

## Tag Processing Rules
- Extensions are included if they have ALL the required tags (unless specified in --include-extensions)
- Extensions listed in --include-extensions are included if they have AT LEAST ONE matching tag
- Tags are combined from both extension level and build configuration level
