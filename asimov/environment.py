"""
Environment capture and management for asimov.

This module provides utilities for capturing the current software environment
to ensure reproducibility of analyses.
"""

import os
import subprocess
import sys
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any


class EnvironmentCapture:
    """
    Capture details of the current software environment.
    
    This class provides methods to detect and capture the current Python
    environment (conda, virtualenv, or system Python) and export it in
    a reproducible format.
    """
    
    def __init__(self):
        """Initialize the environment capture."""
        self.env_type = self._detect_environment_type()
        
    def _detect_environment_type(self) -> str:
        """
        Detect the type of Python environment currently in use.
        
        Returns
        -------
        str
            One of: 'conda', 'virtualenv', 'venv', or 'system'
        """
        # Check for conda environment
        if os.environ.get('CONDA_DEFAULT_ENV') or os.environ.get('CONDA_PREFIX'):
            return 'conda'
        
        # Check for virtualenv or venv
        if hasattr(sys, 'real_prefix') or (
            hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix
        ):
            # Determine if it's virtualenv or venv
            if os.path.exists(os.path.join(sys.prefix, 'conda-meta')):
                return 'conda'
            return 'virtualenv'
        
        return 'system'
    
    def capture_conda_environment(self) -> Optional[str]:
        """
        Capture the conda environment specification.
        
        Returns
        -------
        str or None
            The output of 'conda list --export' if successful, None otherwise
        """
        # Validate conda exists in PATH before attempting to run
        if not shutil.which('conda'):
            return None
        
        try:
            result = subprocess.run(
                ['conda', 'list', '--export'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            return None
    
    def capture_pip_environment(self) -> Optional[str]:
        """
        Capture the pip environment specification.
        
        Returns
        -------
        str or None
            The output of 'pip freeze' if successful, None otherwise
        """
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'freeze'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            return None
    
    def get_environment_info(self) -> Dict[str, Any]:
        """
        Get comprehensive environment information.
        
        Returns
        -------
        dict
            Dictionary containing environment metadata including:
            - timestamp: When the environment was captured
            - environment_type: Type of environment (conda/virtualenv/system)
            - python_version: Python version string
            - python_executable: Path to Python executable
            - conda_environment: Output of 'conda list --export' if applicable
            - pip_packages: Output of 'pip freeze'
            - conda_env_name: Name of conda environment if applicable
        """
        info = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'environment_type': self.env_type,
            'python_version': sys.version,
            'python_executable': sys.executable,
        }
        
        # Add conda-specific information
        if self.env_type == 'conda':
            info['conda_env_name'] = os.environ.get('CONDA_DEFAULT_ENV', 'unknown')
            conda_env = self.capture_conda_environment()
            if conda_env:
                info['conda_environment'] = conda_env
        
        # Always try to capture pip packages as well
        pip_packages = self.capture_pip_environment()
        if pip_packages:
            info['pip_packages'] = pip_packages
        
        return info
    
    def save_environment(self, directory: str, prefix: str = 'environment') -> Dict[str, str]:
        """
        Save the environment specification to files in the given directory.
        
        This method creates multiple files containing the environment specification:
        - environment.json: Metadata about the environment
        - environment-conda.txt: Conda package list (if conda environment)
        - environment-pip.txt: Pip package list
        
        Parameters
        ----------
        directory : str
            Directory where environment files should be saved
        prefix : str, optional
            Prefix for the environment files (default: 'environment')
            
        Returns
        -------
        dict
            Dictionary mapping file type to filepath for files that were created
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        
        env_info = self.get_environment_info()
        created_files = {}
        
        # Save JSON metadata
        json_file = directory / f'{prefix}.json'
        with open(json_file, 'w') as f:
            # Create a copy without the potentially large package lists
            metadata = {k: v for k, v in env_info.items() 
                       if k not in ['conda_environment', 'pip_packages']}
            json.dump(metadata, f, indent=2)
        created_files['metadata'] = str(json_file)
        
        # Save conda environment if available
        if 'conda_environment' in env_info and env_info['conda_environment']:
            conda_file = directory / f'{prefix}-conda.txt'
            with open(conda_file, 'w') as f:
                f.write(env_info['conda_environment'])
            created_files['conda'] = str(conda_file)
        
        # Save pip packages if available
        if 'pip_packages' in env_info and env_info['pip_packages']:
            pip_file = directory / f'{prefix}-pip.txt'
            with open(pip_file, 'w') as f:
                f.write(env_info['pip_packages'])
            created_files['pip'] = str(pip_file)
        
        return created_files


def capture_and_save_environment(directory: str, prefix: str = 'environment') -> Dict[str, str]:
    """
    Convenience function to capture and save the current environment.
    
    Parameters
    ----------
    directory : str
        Directory where environment files should be saved
    prefix : str, optional
        Prefix for the environment files (default: 'environment')
        
    Returns
    -------
    dict
        Dictionary mapping file type to filepath for files that were created
    """
    capture = EnvironmentCapture()
    return capture.save_environment(directory, prefix)
