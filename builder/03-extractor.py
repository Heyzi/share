#!/usr/bin/env python3
import os, sys, zipfile, json, shutil, argparse, logging, hashlib, re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from collections import defaultdict

logging.basicConfig(format='%(asctime)s [%(levelname)s] %(message)s',
                 level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

@dataclass
class ArtifactInfo:
   pipeline_id: str
   job_id: str
   branch: str
   
   @staticmethod
   def parse_filename(filename: str) -> Optional['ArtifactInfo']:
       pattern = r'.*[_-]pipeline(\d+)[_-]job(\d+)[_-]branch[_-](.+?)\.(?:zip|vsix|carts)$'
       try:
           match = re.match(pattern, filename)
           if match:
               branch = re.sub(r'%2[Ff]', '/', match.group(3))
               branch = re.sub(r'[^\w\-\.\/]', '_', branch)
               return ArtifactInfo(match.group(1), match.group(2), branch)
       except Exception as e:
           logger.error(f"Error parsing filename {filename}: {e}")
       return None

@dataclass
class ExtensionInfo:
   sha256: str
   install_path: str
   version: str
   file_format: str
   filename: str
   artifact_info: Optional[ArtifactInfo] = None

   @staticmethod
   def parse_line(line: str) -> Optional['ExtensionInfo']:
       try:
           parts = line.split(':', 4)
           if len(parts) == 5:
               ext = ExtensionInfo(*parts)
               ext.artifact_info = ArtifactInfo.parse_filename(ext.filename)
               return ext
       except Exception as e:
           logger.warning(f"Failed to parse line: {line}, error: {e}")
       return None

   def get_package_name(self) -> str:
       return self.install_path.split('.', 1)[-1]

   def format_artifact_info(self) -> str:
       if not self.artifact_info:
           return ""
       return (f" (pipeline #{self.artifact_info.pipeline_id}, "
               f"job #{self.artifact_info.job_id}, "
               f"branch: {self.artifact_info.branch})")

@dataclass
class ProcessingStats:
   found_files: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
   extracted_files: Dict[str, int] = field(default_factory=lambda: defaultdict(int)) 
   updated_extensions: List[tuple] = field(default_factory=list)
   new_extensions: List[ExtensionInfo] = field(default_factory=list)
   unchanged_extensions: List[ExtensionInfo] = field(default_factory=list)

class ExtensionProcessor:
   def __init__(self, source_dir: str, target_dir: str):
       self.source_dir = Path(source_dir).resolve()
       self.target_dir = Path(target_dir).resolve()
       self.extension_list = self.target_dir / 'extension_list.txt'
       self.existing_extensions = {}
       self.stats = ProcessingStats()
       
       self.target_dir.mkdir(parents=True, exist_ok=True)
       if self.extension_list.exists():
           self._load_extensions()

       logger.info(f"Starting extensions processing")
       logger.info(f"Source directory: {self.source_dir}")
       logger.info(f"Target directory: {self.target_dir}")

   def _load_extensions(self):
       try:
           with open(self.extension_list, 'r', encoding='utf-8') as f:
               for line in f:
                   ext = ExtensionInfo.parse_line(line.strip())
                   if ext:
                       self.existing_extensions[ext.filename] = ext
           logger.info(f"Loaded {len(self.existing_extensions)} entries from extension list")
       except Exception as e:
           logger.error(f"Failed to read extension list: {e}")

   def _process_file(self, file_path: Path) -> Optional[dict]:
       try:
           if zipfile.is_zipfile(file_path):
               with zipfile.ZipFile(file_path) as zf:
                   for name in zf.namelist():
                       if name.endswith('package.json'):
                           try:
                               info = json.loads(zf.read(name).decode())
                               if all(f in info for f in ['name', 'publisher', 'version']):
                                   return info
                           except:
                               continue
       except Exception as e:
           logger.error(f"Failed to process {file_path}: {e}")
       return None

   def _handle_transition(self, package_name: str, new_info: Optional[ExtensionInfo] = None):
       for filename, ext_info in list(self.existing_extensions.items()):
           if ext_info.get_package_name() == package_name:
               if new_info:
                   if ext_info.version != new_info.version:
                       self.stats.updated_extensions.append((ext_info, new_info))
                   else:
                       self.stats.unchanged_extensions.append(new_info)
               del self.existing_extensions[filename]
               if (self.target_dir / filename).exists():
                   (self.target_dir / filename).unlink()

   def _extract_extensions(self, zip_path: Path, temp_dir: Path) -> List[Path]:
       extracted = []
       try:
           temp_dir.mkdir(exist_ok=True)
           with zipfile.ZipFile(zip_path) as zf:
               for f in zf.filelist:
                   if f.filename.lower().endswith(('.vsix', '.carts')) and '__MACOSX' not in f.filename:
                       out_path = temp_dir / os.path.basename(f.filename)
                       with zf.open(f) as src, open(out_path, 'wb') as dst:
                           shutil.copyfileobj(src, dst)
                       extracted.append(out_path)
                       self.stats.extracted_files[zip_path.name] += 1
           if extracted:
               logger.info(f"- {zip_path.name}: extracted {len(extracted)} extensions")
       except Exception as e:
           logger.error(f"Failed to process {zip_path}: {e}")
       return extracted

   def process(self):
       temp_dir = Path('temp_extensions')
       try:
           if not self.source_dir.exists() or not any(self.source_dir.iterdir()):
               logger.info("No extensions found to process")
               return

           extension_files = []
           for file_path in self.source_dir.rglob('*'):
               if not file_path.is_file():
                   continue
               ext = file_path.suffix.lower()
               if ext in ['.vsix', '.carts']:
                   extension_files.append(file_path)
                   self.stats.found_files[ext[1:]] += 1
               elif ext == '.zip':
                   self.stats.found_files['zip'] += 1
                   extension_files.extend(self._extract_extensions(file_path, temp_dir))

           if not extension_files:
               logger.info("No extensions found to process")
               return

           logger.info("Found files by type:")
           for ext, count in self.stats.found_files.items():
               logger.info(f"- {ext.upper()}: {count} files")

           processed = set()
           for ext_file in extension_files:
               try:
                   pkg_info = self._process_file(ext_file)
                   if pkg_info:
                       name = pkg_info['name']
                       if name in processed:
                           continue
                       processed.add(name)

                       sha256 = hashlib.sha256()
                       with open(ext_file, "rb") as f:
                           for chunk in iter(lambda: f.read(4096), b""):
                               sha256.update(chunk)

                       new_ext = ExtensionInfo(
                           sha256=sha256.hexdigest(),
                           install_path=f"{pkg_info['publisher']}.{name}",
                           version=pkg_info['version'],
                           file_format='carts' if ext_file.suffix.lower() == '.carts' else 'vsix',
                           filename=ext_file.name
                       )
                       new_ext.artifact_info = ArtifactInfo.parse_filename(ext_file.name)

                       self._handle_transition(name, new_ext)
                       
                       shutil.copy2(ext_file, self.target_dir)
                       self.existing_extensions[new_ext.filename] = new_ext
                       
                       if not any(t[1] == new_ext for t in self.stats.updated_extensions):
                           if not any(e == new_ext for e in self.stats.unchanged_extensions):
                               self.stats.new_extensions.append(new_ext)

               except Exception as e:
                   logger.error(f"Failed to process {ext_file}: {e}")

           with open(self.extension_list, 'w', encoding='utf-8') as f:
               for ext in sorted(self.existing_extensions.values(), key=lambda x: x.install_path):
                   f.write(f"{ext.sha256}:{ext.install_path}:{ext.version}:{ext.file_format}:{ext.filename}\n")

           logger.info("Final state summary:")
           logger.info(f"Total extensions in target: {len(self.existing_extensions)}")

           if self.stats.updated_extensions:
               logger.info("Updated extensions:")
               for old, new in self.stats.updated_extensions:
                   logger.info(f"- {new.install_path}: v{old.version} -> v{new.version} [{new.file_format}]{new.format_artifact_info()}")

           if self.stats.new_extensions:
               logger.info("Newly added extensions:")
               for ext in self.stats.new_extensions:
                   logger.info(f"- {ext.install_path} v{ext.version} [{ext.file_format}]{ext.format_artifact_info()}")

           logger.info("Changes summary:")
           logger.info(f"- Updated: {len(self.stats.updated_extensions)}")
           logger.info(f"- Added: {len(self.stats.new_extensions)}")
           logger.info(f"- Unchanged: {len(self.stats.unchanged_extensions)}")

           formats = defaultdict(int)
           for ext in self.existing_extensions.values():
               formats[ext.file_format] += 1

           logger.info("Extension formats:")
           for fmt, count in formats.items():
               logger.info(f"- {fmt.upper()}: {count} extensions")

           logger.info("Extension list updated successfully")

       finally:
           if temp_dir.exists():
               shutil.rmtree(temp_dir)

def main():
   parser = argparse.ArgumentParser(description='Install and manage VSIX/CARTS extensions.')
   parser.add_argument('--source', required=True, help='Source directory')
   parser.add_argument('--target', required=True, help='Target directory')
   parser.add_argument('--debug', action='store_true', help='Enable debug logging')
   
   args = parser.parse_args()
   if args.debug:
       logging.getLogger().setLevel(logging.DEBUG)

   try:
       ExtensionProcessor(args.source, args.target).process()
   except Exception as e:
       logger.error(f"Installation failed: {e}")
       sys.exit(1)

if __name__ == '__main__':
   main()
