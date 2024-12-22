#!/usr/bin/env python3

import argparse
import os
import sys
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional
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
class EnvVariable:
    """Representation of environment variable with its value."""
    name: str
    value: Optional[str] = None

class EnvironmentConfig:
    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config = self._load_config()

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
        if not isinstance(config, dict) or 'variables' not in config:
            logger.error("Invalid config format")
            sys.exit(1)

    def get_variables(self) -> List[EnvVariable]:
        variables = []
        seen = set()

        for var_name in self.config['variables']:
            if var_name in seen:
                logger.warning("Duplicate variable found: {}".format(var_name))
                continue

            seen.add(var_name)
            variables.append(EnvVariable(
                name=var_name,
                value=os.environ.get(var_name)
            ))

        return variables

def print_variables(variables: List[EnvVariable]) -> None:
    for var in sorted(variables, key=lambda x: x.name):
        value = '<NOT SET>' if var.value is None else var.value
        logger.info("{} = {}".format(var.name, value))

def main() -> int:
    parser = argparse.ArgumentParser(description='Check environment variables from config')
    parser.add_argument('--config', required=True, help='YAML config path')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose logging')
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    config = EnvironmentConfig(args.config)
    variables = config.get_variables()
    print_variables(variables)
    return 0

if __name__ == '__main__':
    sys.exit(main())