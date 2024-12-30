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
from dataclasses import dataclass
from datetime import datetime, timezone

# Configure logging to write to stdout
logger = logging.getLogger(__name__)
logger.propagate = False
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s',
                                   datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

@dataclass
class DownloadTask:
    """Task configuration for downloading an extension."""
    extension_name: str
    project_id: int
    job_name: str
    branch: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary format."""
        data = {
            'extension_name': self.extension_name,
            'project_id': self.project_id,
            'job_name': self.job_name
        }
        if self.branch:
            data['branch'] = self.branch.strip()
        return data

    def format_info(self) -> str:
        """Format task information as string for logging."""
        branch = self.branch.strip() if self.branch else 'default'
        return "{:<30} job: {:<15} branch: {:<20}".format(
            self.extension_name,
            self.job_name,
            branch
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

        for ext_name, ext_data in config.get('extensions', {}).items():
            if 'id' not in ext_data:
                logger.error(f"Missing 'id' for extension {ext_name}")
                sys.exit(1)
            if 'build_configs' not in ext_data:
                logger.error(f"Missing 'build_configs' for extension {ext_name}")
                sys.exit(1)
            for build in ext_data['build_configs']:
                if 'job_name' not in build:
                    logger.error(f"Missing 'job_name' in build_configs for {ext_name}")
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
        """Get branch name with correct priority order."""
        # 1. Check global environment variable
        global_env_branch = os.getenv('EXTENSIONS_GLOBAL_BRANCH')
        if global_env_branch:
            global_env_branch = global_env_branch.strip()
            if global_env_branch.lower() not in ('default', 'null', ''):
                self.validate_branch(global_env_branch, 'global')
                logger.info("Using global branch from environment: {}".format(global_env_branch))
                return global_env_branch

        # 2. Check global configuration
        if self.global_branch:
            logger.info("Using global branch from config: {}".format(self.global_branch))
            return self.global_branch

        # 3. Check extension-specific environment variable
        ext_name = ext_data['name']
        env_name = "EXTENSIONS_{}_BRANCH".format(ext_name.upper())
        ext_env_branch = os.getenv(env_name)
        if ext_env_branch:
            ext_env_branch = ext_env_branch.strip()
            if ext_env_branch.lower() not in ('default', 'null', ''):
                self.validate_branch(ext_env_branch, ext_name)
                logger.info("Using branch from environment for {}: {}".format(ext_name, ext_env_branch))
                return ext_env_branch

        # 4. Check extension-specific configuration
        branch = ext_data.get('branch')
        if branch:
            branch = branch.strip()
            if branch:
                self.validate_branch(branch, ext_name)
                logger.info("Using branch from extension config for {}: {}".format(ext_name, branch))
                return branch

        logger.debug("No branch found for {}".format(ext_name))
        return None

    def filter_extensions(self, platforms: Set[str], product: str, include_extensions: Optional[Set[str]] = None) -> List[Dict[str, Any]]:
        """Filter extensions based on platforms and product criteria."""
        result = []
        include_extensions = include_extensions or set()

        logger.info("=== Search criteria ===")
        logger.info(f"Platforms required: {', '.join(sorted(platforms))}")
        if product:
            logger.info(f"Product required: {product}")
        if include_extensions:
            logger.info(f"Additional extensions: {', '.join(sorted(include_extensions))}")
        logger.info("=====================")

        # Обработка всех расширений с указанным продуктом
        processed_extensions = set()
        if product:
            for ext_name, ext_data in self.config.get('extensions', {}).items():
                ext_data['name'] = ext_name
                ext_products = set(ext_data.get('products', []))

                if product in ext_products:
                    logger.info(f"\nChecking extension by product: {ext_name}")
                    if self._check_and_add_extension(ext_name, ext_data, platforms, result):
                        processed_extensions.add(ext_name)

        # Добавление расширений из include_extensions, если они еще не были добавлены
        if include_extensions:
            for ext_name, ext_data in self.config.get('extensions', {}).items():
                if ext_name in include_extensions and ext_name not in processed_extensions:
                    ext_data['name'] = ext_name
                    logger.info(f"\nChecking included extension: {ext_name}")
                    self._check_and_add_extension(ext_name, ext_data, platforms, result)

        return result

    def _check_and_add_extension(self, ext_name: str, ext_data: Dict, platforms: Set[str], result: List) -> bool:
        """Check if extension matches platforms and add to results if it does."""
        logger.info("Checking build configurations:")
        for build in ext_data.get('build_configs', []):
            build_platforms = set(build.get('platforms', []))
            logger.info(f"  Job '{build['job_name']}' platforms: {', '.join(sorted(build_platforms))}")

            if platforms == build_platforms:
                logger.info(f"  ✓ Platforms match!")
                info = self._create_extension_info(ext_name, ext_data, build)
                result.append(info)
                return True
            else:
                logger.debug(f"  ✗ Platforms mismatch")

        logger.info("  ✗ No matching build configuration found")
        return False

    def _create_extension_info(self, ext_name: str, ext_data: Dict, build: Dict) -> Dict:
        """Create extension information dictionary."""
        info = {
            'name': ext_name,
            'id': ext_data['id'],
            'job_name': build['job_name']
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
            branch=ext.get('branch')
        ))
    return tasks

def parse_platforms(platforms_str: str) -> Set[str]:
    """Parse comma-separated platforms string into a set."""
    if not platforms_str:
        logger.error("Platforms cannot be empty")
        sys.exit(1)
    return {p.strip() for p in platforms_str.split(',') if p.strip()}

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
    parser = argparse.ArgumentParser(
        description='Generate extension download tasks',
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--config', required=True,
                      help='Path to YAML config file')
    parser.add_argument('--platforms', required=True,
                      help='Comma-separated platforms (e.g., linux,x64)')
    parser.add_argument('--product',
                      help='Single product to filter by (e.g., python)')
    parser.add_argument('--include-extensions',
                      help='Additional extensions to include')
    parser.add_argument('--output', required=True,
                      help='Output JSON path')
    parser.add_argument('--verbose', '-v', action='store_true',
                      help='''Enable verbose logging output. Shows detailed information about:
- Extension checking process
- Platform matching details
- Debug level messages
- Skipped extensions and reasons
Use this for debugging or to understand the selection process.''')
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.info("Checking environment variables:")
    for k, v in os.environ.items():
        if k.upper().startswith('EXTENSIONS_') or k.upper() in ('GITLAB_PLATFORMS', 'DOWNLOAD_INTERNAL_EXTENSIONS'):
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

    platforms = parse_platforms(args.platforms)
    if not platforms:
        logger.error("No valid platforms provided")
        return 1

    include_extensions = parse_extensions(args.include_extensions)

    if not include_extensions and not args.product:
        logger.error("Either --product or --include-extensions must be specified")
        return 1

    extensions = config.filter_extensions(platforms, args.product, include_extensions)
    if not extensions:
        logger.warning("No matching extensions found")
        write_tasks(args.output, [])
        return 0

    tasks = generate_tasks(extensions)
    write_tasks(args.output, tasks)

    logger.info("\nGenerated {} tasks:".format(len(tasks)))
    for task in tasks:
        logger.info("  - {}".format(task.format_info()))

    return 0

if __name__ == '__main__':
    sys.exit(main())
