# Extension Configuration Guide

## Overview
System for configuring multi-platform pipeline extensions with flexible branch management and build specifications.

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
    repo: <url>           # [Required] Git repository URL
    description: <text>   # [Required] Description
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

## System Constraints

### Uniqueness
- Extension IDs must be unique
- Job names must be unique per extension
- Extension names must be unique

### Required Fields
- `version`
- Extension: `id`, `repo`, `description`, `tags`
- Build: `job_name`, `tags`

### Optional Fields
- `global_branch`
- Extension: `branch`

## Environment Variables

```bash
# Global branch setting
EXTENSIONS_GLOBAL_BRANCH=main

# Extension specific branch
EXTENSIONS_TEST_EXTENSION_BRANCH=develop

# Build control
DOWNLOAD_INTERNAL_EXTENSIONS=true  # Enable/disable builds
```
