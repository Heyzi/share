# Artifact Processing Guide

## Overview
Tool for processing built artifacts, adding metadata, and standardizing filenames based on architecture and platform information.

## Usage
```bash
python artifact_processor.py \
  --package-json path/to/package.json \
  --directory path/to/artifacts \
  --extensions exe,dll,so \
  [--verbose]
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| --package-json | Yes | Path to package.json for version info |
| --directory | Yes | Directory with artifacts |
| --extensions | Yes | Comma-separated file extensions |
| --verbose | No | Enable debug logging |

## File Processing Features

### Naming Convention
Input file pattern:
```
name-[arch]-[os]-[version][-extra]
```
Examples:
- `app-x64-1.0.0`
- `app-arm64-linux-1.0.0`
- `app-x64-darwin-1.0.0-dev`

### Architecture Mapping
- x64 → X86-64
- arm64 → Arm64
- arm → Arm64

### Platform Mapping
- linux → debian
- darwin → darwin
- (none) → windows

## Generated Files

For each processed artifact, creates:

1. **Renamed Artifact**:
```
original-name-YYYYMMDDHHMM.extension
```

2. **Metadata File**:
```json
{
  "version": "1.0.0",
  "commit_id": "<git-commit-hash>",
  "architecture": "X86-64",
  "platform": "windows",
  "component": "<from-env>",
  "timestamp": 1640995200,
  "checksum": "<sha256>",
  "is_server": false
}
```

## Environment Variables
- `subProductName`: Sets component in metadata
