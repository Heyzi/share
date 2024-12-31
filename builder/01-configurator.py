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

logger = logging.getLogger(__name__)
logger.propagate = False
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s',
                                   datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(handler)
logger.setLevel(logging.INFO)

@dataclass
class DownloadTask:
    extension_name: str
    project_id: int
    job_name: str
    branch: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = {
            'extension_name': self.extension_name,
            'project_id': self.project_id,
            'job_name': self.job_name
        }
        if self.branch:
            data['branch'] = self.branch.strip()
        return data

    def format_info(self) -> str:
        branch = self.branch.strip() if self.branch else 'default'
        return "{:<30} job: {:<15} branch: {:<20}".format(
            self.extension_name,
            self.job_name,
            branch
        )

class ExtensionConfig:
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        logger.debug("Loading configuration from: {}".format(self.config_path))
        self.config = self._load_config()
        self.global_branch = self._get_global_branch()

    def _load_config(self) -> Dict:
        try:
            with open(self.config_path, encoding='utf-8') as f:
                config = yaml.safe_load(f)
                self._validate_config(config)
                return config
        except Exception as e:
            logger.error("Failed to load config: {}".format(e))
            sys.exit(1)

    def _validate_config(self, config: Dict) -> None:
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
        global_env_branch = os.getenv('EXTENSIONS_GLOBAL_BRANCH')
        if global_env_branch:
            global_env_branch = global_env_branch.strip()
            if global_env_branch.lower() not in ('default', 'null', ''):
                self.validate_branch(global_env_branch, 'global')
                logger.info("Using global branch from environment: {}".format(global_env_branch))
                return global_env_branch

        if self.global_branch:
            logger.info("Using global branch from config: {}".format(self.global_branch))
            return self.global_branch

        ext_name = ext_data['name']
        env_name = "EXTENSIONS_{}_BRANCH".format(ext_name.upper())
        ext_env_branch = os.getenv(env_name)
        if ext_env_branch:
            ext_env_branch = ext_env_branch.strip()
            if ext_env_branch.lower() not in ('default', 'null', ''):
                self.validate_branch(ext_env_branch, ext_name)
                logger.info("Using branch from environment for {}: {}".format(ext_name, ext_env_branch))
                return ext_env_branch

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
        try:
            result = []
            include_extensions = include_extensions or set()

            logger.info("\n=== Search criteria ===")
            logger.info(f"| Required platforms: {', '.join(sorted(platforms))}")
            if product:
                logger.info(f"| Product: {product}")
            if include_extensions:
                logger.info(f"| Additional extensions: {', '.join(sorted(include_extensions))}")
            logger.info("=" * 50)

            processed_extensions = set()
            if product:
                for ext_name, ext_data in self.config.get('extensions', {}).items():
                    ext_data['name'] = ext_name
                    ext_products = set(ext_data.get('products', []))
                    if product in ext_products:
                        if self._check_and_add_extension(ext_name, ext_data, platforms, result):
                            processed_extensions.add(ext_name)

            if include_extensions:
                for ext_name, ext_data in self.config.get('extensions', {}).items():
                    if ext_name in include_extensions and ext_name not in processed_extensions:
                        ext_data['name'] = ext_name
                        self._check_and_add_extension(ext_name, ext_data, platforms, result)

            return result
        except Exception as e:
            logger.error(f"Error during extension filtering: {e}")
            sys.exit(1)

    def _check_and_add_extension(self, ext_name: str, ext_data: Dict, platforms: Set[str], result: List) -> bool:
        try:
            logger.info(f"\nChecking extension: {ext_name}")
            for build in ext_data.get('build_configs', []):
                build_platforms = set(build.get('platforms', []))
                job_name = build['job_name']
                logger.info(f"| Job: {job_name}")
                logger.info(f"|   Available platforms: {', '.join(sorted(build_platforms))}")
                
                matching_platforms = platforms & build_platforms
                if matching_platforms:
                    logger.info(f"|   [MATCH] Found matching platforms: {', '.join(sorted(matching_platforms))}")
                    info = self._create_extension_info(ext_name, ext_data, build)
                    result.append(info)
                    return True
                else:
                    logger.info("|   [SKIP] No matching platforms found")

            logger.info("| No matching build configuration found")
            return False
        except Exception as e:
            logger.error(f"Error checking extension {ext_name}: {e}")
            sys.exit(1)

    def _create_extension_info(self, ext_name: str, ext_data: Dict, build: Dict) -> Dict:
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
    try:
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
    except Exception as e:
        logger.error(f"Error generating tasks: {e}")
        sys.exit(1)

def parse_platforms(platforms_str: str) -> Set[str]:
    try:
        if not platforms_str:
            logger.error("Platforms cannot be empty")
            sys.exit(1)
        return {p.strip() for p in platforms_str.split(',') if p.strip()}
    except Exception as e:
        logger.error(f"Error parsing platforms: {e}")
        sys.exit(1)

def parse_extensions(extensions_str: Optional[str]) -> Set[str]:
    try:
        if extensions_str is None or not extensions_str.strip():
            return set()
        return {e.strip() for e in extensions_str.split(',') if e.strip()}
    except Exception as e:
        logger.error(f"Error parsing extensions: {e}")
        sys.exit(1)

def write_tasks(path: str, tasks: List[DownloadTask]) -> None:
    try:
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
            raise
    except Exception as e:
        logger.error(f"Failed writing tasks: {e}")
        sys.exit(1)

def main() -> int:
    try:
        parser = argparse.ArgumentParser(description='Generate extension download tasks')
        parser.add_argument('--config', required=True, help='Path to YAML config file')
        parser.add_argument('--platforms', required=True, help='Comma-separated platforms (e.g., linux,x64)')
        parser.add_argument('--product', help='Single product to filter by (e.g., python)')
        parser.add_argument('--include-extensions', nargs='?', const='', default=None, help='Additional extensions to include')
        parser.add_argument('--output', required=True, help='Output JSON path')
        parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging output')
        args = parser.parse_args()

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        logger.info("\nEnvironment variables:")
        env_vars = [k for k in os.environ if k.upper().startswith('EXTENSIONS_') or k.upper() in ('GITLAB_PLATFORMS', 'DOWNLOAD_INTERNAL_EXTENSIONS')]
        if env_vars:
            for k in env_vars:
                logger.info(f"| {k}={os.environ[k]}")
        else:
            logger.info("| No relevant environment variables found")

        downloads_enabled = True
        for k, v in os.environ.items():
            if k.upper() == 'DOWNLOAD_INTERNAL_EXTENSIONS':
                downloads_enabled = v.lower().strip() == 'true'
                logger.info(f"\nDownload internal extensions: {downloads_enabled}")
                break

        if not downloads_enabled:
            logger.info("Downloads disabled by environment variable, generating empty config")
            write_tasks(args.output, [])
            return 0

        logger.info(f"\nLoading config: {args.config}")

        config = ExtensionConfig(args.config)
        platforms = parse_platforms(args.platforms)
        if not platforms:
            logger.error("No valid platforms provided")
            return 1

        include_extensions = parse_extensions(args.include_extensions)
        product = args.product.strip() if args.product else ''

        if not include_extensions and not product:
            logger.info("\nNo extensions or product specified, generating empty config")
            write_tasks(args.output, [])
            return 0

        extensions = config.filter_extensions(platforms, product, include_extensions)
        if not extensions:
            logger.warning("\nNo matching extensions found")
            write_tasks(args.output, [])
            return 0

        tasks = generate_tasks(extensions)
        write_tasks(args.output, tasks)
        logger.info(f"\nTotal tasks generated: {len(tasks)}")
        return 0

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
