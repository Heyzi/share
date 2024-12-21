# Artifact Metadata Generator

This tool processes build artifacts and generates metadata files for them. It handles artifact naming conventions, extracts relevant information, and creates JSON metadata files.

## Features

- Processes artifacts with specific naming conventions
- Generates JSON metadata for each artifact
- Adds timestamps to files
- Calculates SHA256 checksums
- Supports Windows and Linux builds
- Handles multiple architectures (X86-64, Arm64)
- Gets version from package.json
- Gets commit ID from git repository

## Requirements

- Python 3.x
- Git (for commit ID extraction)
- Required directory structure:
 - package.json (for version information)
 - Artifacts directory with build files

## Usage

Basic command:
```
python3 filejson.py --package-json path/to/package.json --directory path/to/artifacts --extensions yml,yaml
```

Arguments:
- --package-json: Path to package.json file containing version information
- --directory: Directory containing artifact files to process
- --extensions: Comma-separated list of file extensions to process
- --verbose: Enable debug logging (optional)

Environment Variables:
- subProductName: Component name to use in metadata

## File Naming Convention

Current supported format:
```
{name}-{arch}-[linux-]{version}-{suffix}.{extension}
```

Examples:
- agent-x64-2.0.0-test.yml
- product1-server-arm64-linux-1.0.0-dev.yml

## Output

For each processed file:
1. Original file is renamed with timestamp:
  ```
  original-name-202401011200.extension
  ```
2. JSON metadata file is created:
  ```
  original-name-202401011200.json
  ```

Metadata format:
```
{
 "version": "1.0.0",
 "commit_id": "abc123...",
 "architecture": "X86-64",
 "platform": "windows",
 "component": "component_name",
 "timestamp": 1234567890,
 "checksum": "sha256_hash",
 "is_server": false
}
```

## Maintenance Guide

### Adding New Architectures

Modify ARCH_MAP in ArtifactProcessor class:
```
ARCH_MAP = {
   'x64': 'X86-64',
   'arm64': 'Arm64',
   'new_arch': 'New-Arch'  # Add new mapping
}
```

### Adding New Metadata Fields

1. Add field to FileInfo dataclass:
```
@dataclass
class FileInfo:
   # ... existing fields ...
   new_field: str
```

2. Update metadata generation in generate_metadata:
```
def generate_metadata(self, file_info: FileInfo) -> Dict[str, Any]:
   metadata = {
       # ... existing fields ...
       'new_field': file_info.new_field
   }
   return metadata
```

3. Add field initialization in process_file:
```
def process_file(self, file_path: Path) -> FileInfo:
   # ... existing code ...
   info = FileInfo(
       # ... existing fields ...
       new_field="value"
   )
   return info
```

### Modifying File Name Pattern

Update the regex pattern in _parse_filename method:
```
pattern = r'your-new-pattern-here'
```

Current pattern components:
- [\w-]+: matches name part
- (?P<arch>arm64|x64): captures architecture
- (?:-(?P<os>linux))?: optionally captures OS
- (?P<version>[\d.]+): captures version number
- -\w+: matches suffix
