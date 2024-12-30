# Extension Configuration Guide

## Overview
System for configuring multi-platform pipeline extensions with flexible branch management and build specifications. The system filters extensions based on products and platforms, generating task configurations.

## Core Features
- Flexible branch management with priority system 
- Product-based extension filtering
- Platform-specific build configurations
- JSON task generation
- Explicit extension inclusion
- Detailed logging

## Command Line Usage
```bash
# Using product filter
python3 extension_task_generator.py \
  --config config.yml \
  --platforms linux,x64 \
  --product python \
  --output tasks.json

# Using include-extensions
python3 extension_task_generator.py \
  --config config.yml \
  --platforms linux,x64 \
  --include-extensions ext1,ext2 \
  --output tasks.json

# Using both
python3 extension_task_generator.py \
  --config config.yml \
  --platforms linux,x64 \
  --product python \
  --include-extensions ext1,ext2 \
  --output tasks.json
```

### Arguments
- `--config` [Required]: Path to YAML configuration file
- `--platforms` [Required]: Comma-separated list of required platforms for filtering
- `--output` [Required]: Path for generated JSON task file
- `--product` [Optional]: Single product to filter by
- `--include-extensions` [Optional]: Additional extensions to include regardless of product
- `--verbose` [Optional]: Enable verbose logging showing detailed matching process

Note: Either `--product` or `--include-extensions` (or both) must be specified.

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
  extension-name:           # Extension identifier
    id: <number>           # [Required] Unique numeric ID
    repo: <url>            # Repository URL
    description: <text>    # Extension description
    branch: <string>       # [Optional] Branch override
    products: [...]        # [Required] Supported products
    build_configs:         # [Required] Build array
      - job_name: <name>   # [Required] CI job name
        platforms: [...]   # [Required] Platform requirements
```

### Products Configuration
Product list at extension level:
```yaml
products: [java, python, cpp]          # Multiple products supported
products: [cuda, tensorflow, pytorch]   # ML/AI products
```

### Platform Requirements
Platform specifications at build level:
```yaml
platforms: [windows, x64]              # Windows x64 build
platforms: [linux, x64, cuda]          # Linux CUDA build
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
    products: [python, cpp, cuda]
    build_configs:
      - job_name: build-job
        platforms: [windows, x64]
```

### Multi-Platform Extension
```yaml
version: "1"
extensions:
  cross-platform:
    id: 5
    repo: http://gitlab.my/main/universal
    description: "Multi-platform processor"
    products: [cpp, python, cuda]
    build_configs:
      - job_name: build_linux_x64
        platforms: [linux, x64]
      - job_name: build_windows_x64
        platforms: [windows, x64]
```

## Output Format
Generated JSON task configuration:
```json
{
  "version": "1.0",
  "generated_at": "2024-12-30T12:00:00Z",
  "tasks": [
    {
      "extension_name": "test-extension",
      "project_id": 4,
      "job_name": "build-job",
      "branch": "feature/branch"  // Optional
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
- Extension: `id`, `products`
- Build: `job_name`, `platforms`

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
```

## Processing Rules
- When only `--product` is specified:
  - Extension must contain the specified product
  - Build configuration must exactly match all specified platforms
- When both `--product` and `--include-extensions` are specified:
  - First, all extensions containing the product are selected
  - Then, additional extensions from include-extensions are added
  - All selected extensions must have build configurations exactly matching the specified platforms
- When only `--include-extensions` is specified:
  - Only listed extensions are processed
  - Selected extensions must have build configurations exactly matching the specified platforms
```
