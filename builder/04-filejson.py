def _parse_filename(self, file_path: Path) -> Dict[str, str]:
    filename = file_path.stem
    
    # Split filename into components
    parts = filename.split('-')
    if len(parts) < 4:
        raise ValueError(f"Invalid filename format: {filename}")
        
    # Extract components
    product = parts[1]  # e.g. 'inscode' or 'python'
    
    # Find version and arch
    version_pattern = r'(\d+\.\d+\.\d+)'
    arch = None
    version = None
    
    for part in parts:
        if part in ['x64', 'arm64']:
            arch = part
        elif re.match(version_pattern, part):
            version = part
            
    if not arch or not version:
        raise ValueError(f"Missing architecture or version in filename: {filename}")
        
    # Validate architecture
    if arch not in self.ARCH_MAP:
        raise ValueError(f"Unknown architecture: {arch}")
        
    # Detect OS type from extension
    os_type = self._detect_os_type(file_path, filename)
    if not os_type:
        raise ValueError(f"Could not determine OS type for: {filename}")
        
    return {
        'product': product,
        'arch': arch,
        'version': version,
        'os': os_type
    }

def _detect_os_type(self, file_path: Path, filename: str) -> Optional[str]:
    extension = file_path.suffix.lower()[1:]
    return self.OS_FILE_MAP.get(extension)
