# Extension Installer Guide

## Overview
Tool for processing and installing VSIX/CARTS extensions from CI artifacts. Supports version tracking, updates, and file integrity verification.

## Usage
```bash
python extension_installer.py \
  --source /path/to/artifacts \
  --target /path/to/extensions \
  [--debug]
```

## Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| --source | Yes | Directory containing extension artifacts (.zip, .vsix, .carts) |
| --target | Yes | Installation directory for extensions |
| --debug | No | Enable debug logging |

## Features

### File Processing
- Handles `.zip`, `.vsix`, and `.carts` files
- Extracts extensions from ZIP archives
- Validates package integrity with SHA256
- Maintains extension list in `extension_list.txt`

### Version Management
- Tracks extension versions
- Detects and reports updates
- Preserves extension history
- Removes old versions automatically

### Extension Information
Example entry in extension_list.txt:
```
<sha256>:<publisher.name>:<version>:<format>:<filename>
```

## Output Example
```
Starting extensions processing
Source directory: /path/to/artifacts
Target directory: /path/to/extensions

Found files by type:
- ZIP: 2 files
- VSIX: 3 files
- CARTS: 1 files

Final state summary:
Total extensions in target: 4

Updated extensions:
- publisher.extension: v1.0.0 -> v1.1.0 [vsix] (pipeline #123, job #456, branch: main)

Newly added extensions:
- publisher.newext v1.0.0 [carts] (pipeline #789, job #012, branch: develop)

Changes summary:
- Updated: 1
- Added: 1
- Unchanged: 2

Extension formats:
- VSIX: 3 extensions
- CARTS: 1 extensions
```

## Common Issues
- Invalid package.json in extension
- Corrupted ZIP archives
- Duplicate extensions
- File permission errors
- Missing package metadata