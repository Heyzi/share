#!/usr/bin/env python3

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import time
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# Configure logging
logger = logging.getLogger(__name__)
logger.propagate = False
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s',
                                    datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

@dataclass
class FileInfo:
    path: Path
    version: str
    commit_id: str
    arch: str
    os_type: str
    subproduct_name: str
    timestamp: int
    sha256: str
    new_name: str

class ArtifactProcessor:
    ARCH_MAP = {
        'x64': 'X86-64',
        'arm64': 'ARM64',
        'arm': 'ARM64',
        'x86_64': 'X86-64'
    }

    OS_FILE_MAP = {
        'deb': 'debian',
        'rpm': 'debian',
        'exe': 'windows',
        'dmg': 'darwin',
        'linux': 'debian',
        'windows': 'windows',
        'darwin': 'darwin'
    }

    def __init__(self, package_json_path: str):
        self.package_path = Path(package_json_path)
        self.version = self._get_package_version()
        self.commit_id = self._get_git_commit_id()
        self.subproduct_name = os.environ.get('subProductName', 'default')
        logger.info(f"Initialized with version {self.version}, commit {self.commit_id}")

    def _get_package_version(self) -> str:
        try:
            with open(self.package_path) as f:
                return json.load(f).get('version', '')
        except Exception as e:
            logger.error(f"Failed to read version: {e}")
            raise

    def _get_git_commit_id(self) -> str:
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=self.package_path.parent,
                capture_output=True,
                text=True
            )
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"Failed to get commit ID: {e}")
            raise

    def _calculate_sha256(self, file_path: Path) -> str:
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate SHA256: {e}")
            raise

    def _detect_os_type(self, file_path: Path, name_components: Dict[str, str]) -> str:
        extension = file_path.suffix.lower()[1:]
        os_type = self.OS_FILE_MAP.get(extension)
        
        if not os_type:
            # Try to detect OS from filename
            filename_lower = file_path.stem.lower()
            for os_key in ['linux', 'windows', 'darwin']:
                if os_key in filename_lower:
                    os_type = self.OS_FILE_MAP[os_key]
                    break
            
            if not os_type:
                logger.warning(f"Could not detect OS type for {file_path}, defaulting to windows")
                os_type = 'windows'

        return os_type

    def _parse_filename(self, file_path: Path) -> Dict[str, str]:
        filename = file_path.stem
        # Fixed pattern that better handles Linux/Windows paths
        pattern = r'(?:codearts-)?(?:[\w-]+)-(?P<arch>arm64|x64|x86_64)?-?(?P<version>[\d.]+)(?:-[\w]+)?'
        match = re.match(pattern, filename)
        
        if not match:
            raise ValueError(f"Invalid filename format: {filename}")
    
        components = match.groupdict()
        # Default architecture handling
        arch = components.get('arch')
        if not arch:
            if 'linux' in filename.lower():
                arch = 'x64'
            elif 'darwin' in filename.lower():
                arch = 'arm64'
            else:
                arch = 'x64'
    
        components['arch'] = arch
        components['os'] = self._detect_os_type(file_path, components)
        
        return components

    def process_file(self, file_path: Path) -> FileInfo:
        logger.info(f"Processing file: {file_path}")
        parsed = self._parse_filename(file_path)
        
        return FileInfo(
            path=file_path,
            version=self.version,
            commit_id=self.commit_id,
            arch=self.ARCH_MAP[parsed['arch']],
            os_type=parsed['os'],
            subproduct_name=self.subproduct_name,
            timestamp=int(time.time()),
            sha256=self._calculate_sha256(file_path),
            new_name=file_path.stem
        )

    def generate_metadata(self, file_info: FileInfo) -> Dict[str, Any]:
        return {
            'current_version': file_info.version,
            'commit_id': file_info.commit_id,
            'arch': file_info.arch,
            'os_type': file_info.os_type,
            'sub_product_name': file_info.subproduct_name,
            'timestamp': file_info.timestamp,
            'sha256hash': file_info.sha256,
            'is_server': False
        }

    def process_directory(self, directory: Path, extensions: List[str]) -> List[FileInfo]:
        logger.info(f"Processing directory: {directory} for extensions: {extensions}")
        results = []

        for ext in extensions:
            for file_path in directory.glob(f"*.{ext}"):
                try:
                    file_info = self.process_file(file_path)
                    metadata = self.generate_metadata(file_info)
                    timestamp = datetime.fromtimestamp(file_info.timestamp).strftime('%Y%m%d%H%M')
                    
                    # Create new filenames
                    new_file_path = file_path.with_name(f"{file_path.stem}-{timestamp}{file_path.suffix}")
                    metadata_path = new_file_path.with_suffix(f"{file_path.suffix}.json")
                    
                    # Rename and save files
                    file_path.rename(new_file_path)
                    with open(metadata_path, 'w') as f:
                        json.dump(metadata, f, indent=2)

                    logger.info(f"Processed {new_file_path}")
                    results.append(file_info)
                except Exception as e:
                    logger.warning(f"Failed to process {file_path}: {e}")

        return results

def main():
    parser = argparse.ArgumentParser(description='Process artifacts')
    parser.add_argument('--package-json', required=True, help='Path to package.json file')
    parser.add_argument('--directory', required=True, help='Directory path')
    parser.add_argument('--extensions', required=True, help='File extensions (comma-separated)')
    parser.add_argument('--verbose', action='store_true', help='Enable debug logging')

    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    try:
        processor = ArtifactProcessor(args.package_json)
        processor.process_directory(
            directory=Path(args.directory),
            extensions=args.extensions.split(',')
        )
        return 0
    except Exception as e:
        logger.error(f"Error during processing: {e}")
        if args.verbose:
            logger.exception("Detailed error:")
        return 1

if __name__ == '__main__':
    sys.exit(main())
