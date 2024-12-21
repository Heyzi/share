# Extension Processor

A tool for processing and tracking VSCode/CARTS extensions, managing their versions and metadata.

## Features

- Processes .vsix and .carts extension files
- Extracts metadata from extensions
- Tracks version changes
- Handles nested extensions in ZIP archives
- Maintains extensions.txt catalog
- Reports additions and updates
- Preserves file timestamps
- Supports recursive directory scanning

## Requirements

- Python 3.x
- Read/write permissions for source and target directories
- Sufficient disk space for temporary files

## Usage

Basic command:
```
python3 extension_processor.py --source /path/to/source --target /path/to/target
```

Arguments:
- --source: Directory containing extension files
- --target: Directory to store processed extensions
- --verbose: Enable debug logging (optional)

## File Types

The processor handles:
- .vsix: VSCode extensions
- .carts: CARTS extensions
- .zip: Archives containing extensions

## Output Format

1. Processed Extensions:
- Copied to target directory preserving filenames
- Metadata extracted and tracked

2. extensions.txt format:
```
extension_name:publisher:version
```

3. Processing Report:
- Files processed by type
- Updated extensions (old → new version)
- Added extensions
- Unchanged extensions

## Maintenance Guide

### Adding New Extension Types

1. Update file extension handling:
```
if ext in ['.vsix', '.carts', '.new_ext']:
   # Process extension
```

2. Modify metadata extraction if needed:
```
def _extract_metadata(self, file_path: Path) -> Optional[ExtensionMetadata]:
   # Add handling for new format
```

### Modifying Metadata Tracking

1. Update ExtensionMetadata dataclass:
```
@dataclass
class ExtensionMetadata:
   # Add new fields
   new_field: str
```

2. Update metadata extraction:
```
metadata = ExtensionMetadata(
   # Add new field extraction
   new_field=data['new_field']
)
```

### Modifying Output Format

1. Update extensions.txt format:
```
def _write_extensions_file(self):
   # Modify output format
   f.write(f"{metadata.name}:{metadata.publisher}:{metadata.version}:{new_field}\n")
```

2. Update reporting:
```
def _report_results(self):
   # Add new statistics
   # Modify logging format
```

### Adding Archive Support

Modify ZIP handling in process method:
```
elif ext == '.zip':
   # Add handling for new archive types
   # Modify extraction logic
```

### Modifying Version Comparison

Update version comparison logic in _handle_extension:
```
def _handle_extension(self, file_path: Path, metadata: ExtensionMetadata):
   # Add new version comparison rules
   # Modify update detection
```

### Adding Results Tracking

1. Update ProcessingResult dataclass:
```
@dataclass
class ProcessingResult:
   # Add new tracking fields
   new_metric: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
```

2. Update result collection:
```
def _handle_extension(self, file_path: Path, metadata: ExtensionMetadata):
   # Track new metrics
   self.result.new_metric[category] += 1
```