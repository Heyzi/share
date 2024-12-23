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
       'arm64': 'ARM64'
   }

   OS_FILE_MAP = {
       'deb': 'debian',
       'rpm': 'debian', 
       'exe': 'windows',
       'dmg': 'darwin'
   }

   def __init__(self, package_json_path: str):
       self.package_path = Path(package_json_path)
       if not self.package_path.exists():
           raise FileNotFoundError(f"Package file not found: {package_json_path}")
           
       self.version = self._get_package_version()
       self.commit_id = self._get_git_commit_id()
       self.subproduct_name = os.environ.get('subProductName', 'default')
       
       logger.info(f"Initialized with version {self.version}, commit {self.commit_id}")

   def _get_package_version(self) -> str:
       try:
           with open(self.package_path) as f:
               version = json.load(f).get('version')
               if not version:
                   raise ValueError("No version found in package.json")
               return version
       except Exception as e:
           logger.error(f"Failed to read version: {e}")
           raise

   def _get_git_commit_id(self) -> str:
       try:
           result = subprocess.run(
               ['git', 'rev-parse', 'HEAD'],
               cwd=self.package_path.parent,
               capture_output=True,
               text=True,
               check=True
           )
           commit = result.stdout.strip()
           if not commit:
               raise ValueError("Empty commit ID returned")
           return commit
       except Exception as e:
           logger.error(f"Failed to get commit ID: {e}")
           raise

   def _calculate_sha256(self, file_path: Path) -> str:
       if not file_path.exists():
           raise FileNotFoundError(f"File not found: {file_path}")
           
       try:
           sha256_hash = hashlib.sha256()
           with open(file_path, "rb") as f:
               for chunk in iter(lambda: f.read(4096), b""):
                   sha256_hash.update(chunk)
           return sha256_hash.hexdigest()
       except Exception as e:
           logger.error(f"Failed to calculate SHA256: {e}")
           raise

   def _parse_filename(self, file_path: Path) -> Dict[str, str]:
       filename = file_path.stem
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
           
       if arch not in self.ARCH_MAP:
           raise ValueError(f"Unknown architecture: {arch}")
           
       os_type = self._detect_os_type(file_path)
       if not os_type:
           raise ValueError(f"Unsupported file extension for: {filename}")
           
       return {
           'product': product,
           'arch': arch,
           'version': version,
           'os': os_type
       }

   def _detect_os_type(self, file_path: Path) -> Optional[str]:
       extension = file_path.suffix.lower()[1:]
       return self.OS_FILE_MAP.get(extension)

   def process_file(self, file_path: Path) -> FileInfo:
       if not file_path.exists():
           raise FileNotFoundError(f"File not found: {file_path}")
           
       logger.info(f"Processing file: {file_path}")
       parsed = self._parse_filename(file_path)
       
       if parsed['version'] != self.version:
           raise ValueError(f"Version mismatch: {parsed['version']} != {self.version}")
       
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
       if not directory.exists():
           raise FileNotFoundError(f"Directory not found: {directory}")
           
       logger.info(f"Processing directory: {directory} for extensions: {extensions}")
       results = []

       for ext in extensions:
           if ext not in self.OS_FILE_MAP:
               logger.warning(f"Unsupported extension: {ext}")
               continue
               
           for file_path in directory.glob(f"*.{ext}"):
               try:
                   file_info = self.process_file(file_path)
                   metadata = self.generate_metadata(file_info)
                   timestamp = datetime.fromtimestamp(file_info.timestamp).strftime('%Y%m%d%H%M')
                   
                   new_file_path = file_path.with_name(f"{file_path.stem}-{timestamp}{file_path.suffix}")
                   metadata_path = new_file_path.with_suffix(f"{file_path.suffix}.json")
                   
                   file_path.rename(new_file_path)
                   with open(metadata_path, 'w') as f:
                       json.dump(metadata, f, indent=2)

                   logger.info(f"Processed {new_file_path}")
                   results.append(file_info)
               except Exception as e:
                   logger.warning(f"Failed to process {file_path}: {e}")
                   continue

       if not results:
           logger.warning(f"No valid files found in {directory}")
       else:
           logger.info(f"Successfully processed {len(results)} files")
           
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
   except Exception as e:
       logger.error(f"Error during processing: {e}")
       if args.verbose:
           logger.exception("Detailed error:")
   
   return 0

if __name__ == '__main__':
   sys.exit(main())

if __name__ == '__main__':
   sys.exit(main())
