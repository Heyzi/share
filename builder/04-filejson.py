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

# Configure logging to write to stdout
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
    os_type: Optional[str]
    subproduct_name: str
    timestamp: int
    sha256: str
    new_name: str

class ArtifactProcessor:
    ARCH_MAP = {
        'x64': 'X86-64',
        'arm64': 'Arm64',
        'arm': 'Arm64'
    }

    OS_MAP = {
        'linux': 'debian',
        'darwin': 'darwin',
        None: 'windows'
    }

    def __init__(self, package_json_path: str):
        logger.info(f"Initializing processor with {package_json_path}")
        self.package_path = Path(package_json_path)
        self.version = self._get_version()
        self.commit_id = self._get_commit_id()
        logger.info(f"Initialized with version {self.version}, commit {self.commit_id}")

    def _get_version(self) -> str:
        logger.debug(f"Reading version from {self.package_path}")
        try:
            with open(self.package_path) as f:
                version = json.load(f).get('version', '')
                logger.debug(f"Found version: {version}")
                return version
        except Exception as e:
            logger.error(f"Failed to read version: {e}")
            raise

    def _get_commit_id(self) -> str:
        repo_path = self.package_path.parent
        logger.debug(f"Getting commit ID from repo: {repo_path}")
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                cwd=repo_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            commit = result.stdout.strip()
            logger.debug(f"Found commit ID: {commit}")
            return commit
        except Exception as e:
            logger.error(f"Failed to get commit ID: {e}")
            raise

    def _get_sha256(self, file_path: Path) -> str:
        logger.debug(f"Calculating SHA256 for: {file_path}")
        sha256_hash = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            hash_value = sha256_hash.hexdigest()
            logger.debug(f"SHA256: {hash_value}")
            return hash_value
        except Exception as e:
            logger.error(f"Failed to calculate SHA256: {e}")
            raise

    def _parse_filename(self, filename: str) -> Dict[str, str]:
        logger.debug(f"Parsing filename: {filename}")
        pattern = r'[\w-]+-(?:(?P<arch>arm64|x64)(?:-(?P<os>linux|darwin))?-)?(?P<version>[\d.]+)(?:-\w+)?'
        match = re.match(pattern, filename)
        if not match:
            logger.error(f"Invalid filename format: {filename}")
            raise ValueError(f"Invalid filename format: {filename}")
        components = match.groupdict()
        logger.debug(f"Parsed components: {components}")

        # Установка значений по умолчанию
        if not components.get('arch'):
            components['arch'] = 'x64'

        return components

    def process_file(self, file_path: Path) -> FileInfo:
        logger.info(f"Processing file: {file_path}")
        parsed = self._parse_filename(file_path.stem)
        timestamp = int(time.time())

        if parsed['arch'] not in self.ARCH_MAP:
            raise ValueError(f"Unknown architecture: {parsed['arch']}")

        subproduct_name = os.environ.get('subProductName', '')

        info = FileInfo(
            path=file_path,
            version=self.version,
            commit_id=self.commit_id,
            arch=self.ARCH_MAP[parsed['arch']],
            os_type=self.OS_MAP.get(parsed.get('os')),
            subproduct_name=subproduct_name,
            timestamp=timestamp,
            sha256=self._get_sha256(file_path),
            new_name=file_path.stem
        )
        logger.debug(f"File info: {info}")
        return info

    def process_directory(self, directory: Path, extensions: List[str]) -> List[FileInfo]:
        logger.info(f"Processing directory: {directory}")
        logger.info(f"Looking for extensions: {extensions}")

        results = []
        for ext in extensions:
            logger.debug(f"Scanning for .{ext} files")
            for file_path in directory.glob(f"*.{ext}"):
                try:
                    file_info = self.process_file(file_path)
                    metadata = self.generate_metadata(file_info)
                    timestamp = datetime.fromtimestamp(file_info.timestamp).strftime('%Y%m%d%H%M')

                    new_file_path = file_path.with_name(f"{file_path.stem}-{timestamp}{file_path.suffix}")
                    file_path.rename(new_file_path)

                    metadata_path = new_file_path.with_suffix(f"{new_file_path.suffix}.json")
                    with open(metadata_path, 'w') as f:
                        json.dump(metadata, f, indent=2)

                    logger.info(f"Renamed original file to {new_file_path}")
                    logger.info(f"Saved metadata to {metadata_path}")
                    results.append(file_info)
                except Exception as e:
                    logger.warning(f"Failed to process {file_path}: {e}")
                    continue

        logger.info(f"Found {len(results)} valid files")
        return results

    def generate_metadata(self, file_info: FileInfo) -> Dict[str, Any]:
        logger.debug(f"Generating metadata for: {file_info.path}")
        metadata = {
            'version': self.version,
            'commit_id': file_info.commit_id,
            'architecture': file_info.arch,
            'platform': file_info.os_type,
            'component': file_info.subproduct_name,
            'timestamp': file_info.timestamp,
            'checksum': file_info.sha256,
            'is_server': False
        }
        logger.debug(f"Generated metadata: {metadata}")
        return metadata

def main():
    parser = argparse.ArgumentParser(description='Process artifacts')
    parser.add_argument('--package-json', required=True, help='Path to package.json file')
    parser.add_argument('--directory', required=True, help='Directory path')
    parser.add_argument('--extensions', required=True, help='File extensions (comma-separated)')
    parser.add_argument('--verbose', action='store_true', help='Enable debug logging')

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.info("Starting artifact processing")

    if not os.path.exists(args.package_json):
        logger.warning(f"Package file not found: {args.package_json}")
        return 0

    if not os.path.exists(args.directory):
        logger.warning(f"Directory not found: {args.directory}")
        return 0

    if not args.extensions:
        logger.warning("Extensions parameter is empty")
        return 0

    try:
        processor = ArtifactProcessor(args.package_json)
        processor.process_directory(
            directory=Path(args.directory),
            extensions=args.extensions.split(',')
        )
    except Exception as e:
        logger.warning(f"Error during processing: {e}")
        if args.verbose:
            logger.debug("Stack trace:", exc_info=True)
        return 0

    logger.info("Processing completed")
    return 0

if __name__ == '__main__':
    exit(main())