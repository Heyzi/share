#!/usr/bin/env python3

import argparse
import os
import sys
import yaml
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Set, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

logging.basicConfig(
   format='%(asctime)s [%(levelname)s] %(message)s',
   level=logging.INFO,
   datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

@dataclass
class DownloadTask:
   """Task configuration for downloading an extension."""
   extension_name: str
   project_id: int
   job_name: str
   branch: Optional[str] = None
   tags: List[str] = field(default_factory=list)

   def __post_init__(self):
       """Initialize default values after instance creation."""
       self.tags = self.tags or []

   def to_dict(self) -> Dict[str, Any]:
       """Convert task to dictionary format."""
       data = {
           'extension_name': self.extension_name,
           'project_id': self.project_id,
           'job_name': self.job_name,
           'tags': self.tags
       }
       if self.branch:
           data['branch'] = self.branch.strip()
       return data

   def format_info(self) -> str:
       """Format task information as string for logging."""
       branch = self.branch.strip() if self.branch else 'default'
       return "{:<30} job: {:<15} branch: {:<20}{}".format(
           self.extension_name,
           self.job_name,
           branch,
           ' tags: [{}]'.format(", ".join(self.tags)) if self.tags else ''
       )

class ExtensionConfig:
   """Handler for loading and processing extension configuration."""

   def __init__(self, config_path: str):
       """Initialize configuration handler with config file path."""
       self.config_path = Path(config_path)
       logger.debug("Loading configuration from: {}".format(self.config_path))
       self.config = self._load_config()
       self.global_branch = self._get_global_branch()

   def _load_config(self) -> Dict:
       """Load and validate the YAML configuration file."""
       try:
           with open(self.config_path, encoding='utf-8') as f:
               config = yaml.safe_load(f)
               self._validate_config(config)
               return config
       except Exception as e:
           logger.error("Failed to load config: {}".format(e))
           sys.exit(1)

   def _validate_config(self, config: Dict) -> None:
       """Validate the configuration structure."""
       if not isinstance(config, dict):
           logger.error("Configuration must be a dictionary")
           sys.exit(1)

       required = {'extensions', 'version'}
       missing = required - set(config.keys())
       if missing:
           logger.error("Missing required fields: {}".format(', '.join(missing)))
           sys.exit(1)

   def _get_global_branch(self) -> Optional[str]:
       """Get global branch from environment or config."""
       global_branch = os.getenv('EXTENSIONS_GLOBAL_BRANCH')
       
       if global_branch:
           global_branch = global_branch.strip()
           logger.info("Using global branch from environment: {}".format(global_branch))
           if global_branch.lower() not in ('default', 'null', ''):
               self.validate_branch(global_branch, 'global')
               return global_branch

       config_branch = self.config.get('global_branch')
       if config_branch:
           config_branch = config_branch.strip()
           if config_branch:
               self.validate_branch(config_branch, 'global')
               logger.info("Using global branch from config: {}".format(config_branch))
               return config_branch

       logger.info("No global branch configured")
       return None

   def validate_branch(self, branch: str, ext_name: str) -> None:
       """Validate GitLab branch name format."""
       if not branch or not isinstance(branch, str):
           logger.error("Invalid branch name for {}".format(ext_name))
           sys.exit(1)

       branch = branch.strip()

       if len(branch) > 255:
           logger.error("Branch name too long for {}".format(ext_name))
           sys.exit(1)

       if branch.startswith('-') or branch.endswith('.lock'):
           logger.error("Invalid branch name format for {}".format(ext_name))
           sys.exit(1)

       forbidden = {'\\', '*', '?', '[', ']', '^', '~', ':', ' ', '\t', '(', ')', '#', '@'}
       if any(c in branch for c in forbidden):
           logger.error("Branch contains forbidden chars: {}".format(ext_name))
           sys.exit(1)

       if not re.match(r'^[a-zA-Z0-9\-_./]+$', branch):
           logger.error("Invalid branch format: {}".format(ext_name))
           sys.exit(1)

   def get_branch(self, ext_data: Dict[str, Any]) -> Optional[str]:
       """Get branch name from environment, config, or global setting."""
       ext_name = ext_data['name']
       env_name = "EXTENSIONS_{}_BRANCH".format(ext_name.upper())

       logger.info("Checking branch for extension {}".format(ext_name))
       logger.info("Looking for environment variable: {}".format(env_name))

       branch = None
       if os.name == 'nt':  # Windows
           for k, v in os.environ.items():
               if k.upper() == env_name.upper():
                   branch = v
                   logger.info("Found environment variable {}={}".format(k, v))
                   break
       else:  # Unix-like systems
           branch = os.getenv(env_name)
           if branch is not None:
               logger.info("Found environment variable {}={}".format(env_name, branch))

       if branch:
           branch = branch.strip()
           if branch.lower() not in ('default', 'null', ''):
               self.validate_branch(branch, ext_name)
               logger.info("Using branch from environment: {}".format(branch))
               return branch

       branch = ext_data.get('branch')
       if branch:
           branch = branch.strip()
           if branch:
               self.validate_branch(branch, ext_name)
               logger.info("Using branch from extension config: {}".format(branch))
               return branch

       if self.global_branch:
           logger.info("Using global branch for {}: {}".format(ext_name, self.global_branch))
           return self.global_branch

       logger.info("No branch found for {}".format(ext_name))
       return None

   def filter_extensions(self, base_tags: Set[str], include_extensions: Set[str] = None) -> List[Dict[str, Any]]:
       """Filter extensions based on tags and explicitly included extensions."""
       result = []
       include_extensions = include_extensions or set()

       logger.debug("Filtering extensions with base tags: {}".format(base_tags))
       logger.debug("Include extensions: {}".format(include_extensions))

       for ext_name, ext_data in self.config.get('extensions', {}).items():
           ext_data['name'] = ext_name
           ext_tags = set(ext_data.get('tags', []))

           for build in ext_data.get('build_configs', []):
               all_tags = ext_tags | set(build.get('tags', []))
               
               if ext_name in include_extensions:
                   matching_tags = base_tags & all_tags
                   if matching_tags:
                       logger.debug("Including extension {} (explicit inclusion) - matched tags: {}".format(ext_name, matching_tags))
                       info = self._create_extension_info(ext_name, ext_data, build, all_tags)
                       result.append(info)
               else:
                   if base_tags.issubset(all_tags):
                       logger.debug("Including extension {} (tag match) - all required tags present: {}".format(ext_name, base_tags))
                       info = self._create_extension_info(ext_name, ext_data, build, all_tags)
                       result.append(info)

       return result

   def _create_extension_info(self, ext_name: str, ext_data: Dict, build: Dict, tags: Set[str]) -> Dict:
       """Create extension information dictionary."""
       info = {
           'name': ext_name,
           'id': ext_data['id'],
           'job_name': build['job_name'],
           'tags': list(tags)
       }
       branch = self.get_branch(ext_data)
       if branch:
           info['branch'] = branch
       return info

def generate_tasks(extensions: List[Dict[str, Any]]) -> List[DownloadTask]:
   """Generate download tasks from extension configurations."""
   seen = set()
   tasks = []

   for ext in extensions:
       key = (ext['id'], ext['job_name'])
       if key in seen:
           logger.error("Duplicate task: {}".format(ext['name']))
           sys.exit(1)
       seen.add(key)

       tasks.append(DownloadTask(
           extension_name=ext['name'],
           project_id=ext['id'],
           job_name=ext['job_name'],
           branch=ext.get('branch'),
           tags=ext.get('tags', [])
       ))
   return tasks

def parse_tags(tags_str: Optional[str]) -> Set[str]:
   """Parse comma-separated tags string into a set."""
   if not tags_str:
       return set()
   return {t.strip() for t in tags_str.split(',') if t.strip()}

def parse_extensions(extensions_str: Optional[str]) -> Set[str]:
   """Parse comma-separated extensions string into a set."""
   if not extensions_str:
       return set()
   return {e.strip() for e in extensions_str.split(',') if e.strip()}

def write_tasks(path: str, tasks: List[DownloadTask]) -> None:
   """Write tasks to JSON file."""
   data = {
       'version': '1.0',
       'generated_at': datetime.now(timezone.utc).isoformat(),
       'tasks': [t.to_dict() for t in tasks]
   }

   path_obj = Path(path)
   tmp_path = path_obj.with_suffix('.tmp')
   try:
       path_obj.parent.mkdir(parents=True, exist_ok=True)
       with open(tmp_path, 'w', encoding='utf-8') as f:
           json.dump(data, f, indent=2, ensure_ascii=False)
       tmp_path.replace(path_obj)
       logger.debug("Tasks written to: {}".format(path_obj))
   except Exception as e:
       if tmp_path.exists():
           tmp_path.unlink()
       logger.error("Failed writing tasks: {}".format(e))
       sys.exit(1)

def main() -> int:
   """Main function for generating extension download tasks."""
   parser = argparse.ArgumentParser(description='Generate extension download tasks')
   parser.add_argument('--config', required=True, help='YAML config path')
   parser.add_argument('--tags', required=True, help='Comma-separated tags')
   parser.add_argument('--include-extensions', nargs='?', const='', help='Additional extensions to include regardless of tags (comma-separated)')
   parser.add_argument('--output', required=True, help='Output JSON path')
   parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
   args = parser.parse_args()

   if args.verbose:
       logging.getLogger().setLevel(logging.DEBUG)

   logger.info("Checking environment variables:")
   for k, v in os.environ.items():
       if k.upper().startswith('EXTENSIONS_') or k.upper() in ('GITLAB_TAGS', 'DOWNLOAD_INTERNAL_EXTENSIONS'):
           logger.info("  {}={}".format(k, v))

   downloads_enabled = True
   for k, v in os.environ.items():
       if k.upper() == 'DOWNLOAD_INTERNAL_EXTENSIONS':
           downloads_enabled = v.lower().strip() == 'true'
           logger.info("Download internal extensions setting: {}".format(downloads_enabled))
           break

   if not downloads_enabled:
       logger.info("Downloads disabled by environment variable, generating empty config")
       write_tasks(args.output, [])
       return 0

   logger.info("Starting task generation with config: {}".format(args.config))

   config = ExtensionConfig(args.config)

   tags_str = args.tags
   if not tags_str:
       for k, v in os.environ.items():
           if k.upper() == 'GITLAB_TAGS':
               tags_str = v
               logger.info("Using tags from environment: {}".format(v))
               break

   base_tags = parse_tags(tags_str)
   if not base_tags:
       logger.error("No valid base tags provided")
       return 1

   include_extensions = parse_extensions(args.include_extensions)

   logger.info("Processing base tags: {}".format(', '.join(sorted(base_tags))))
   if include_extensions:
       logger.info("Including additional extensions: {}".format(', '.join(sorted(include_extensions))))

   extensions = config.filter_extensions(base_tags, include_extensions)
   if not extensions:
       logger.warning("No matching extensions found")
       write_tasks(args.output, [])
       return 0

   tasks = generate_tasks(extensions)
   write_tasks(args.output, tasks)

   logger.info("Generated {} tasks:".format(len(tasks)))
   for task in tasks:
       logger.info("  - {}".format(task.format_info()))

   return 0

if __name__ == '__main__':
   sys.exit(main())
