# [FILE: core/project_manager.py]
import os
import sys
import json
import time
from pathlib import Path

class ProjectManager:
    """Manages recent projects list and project history."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProjectManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.config_dir = self._get_config_directory()
        self.recent_projects_file = os.path.join(self.config_dir, "recent_projects.json")
        self.max_recent_projects = 10
        self._ensure_config_dir()
    
    def _get_config_directory(self):
        """Get platform-appropriate config directory."""
        if os.name == 'nt':  # Windows
            appdata = os.getenv('APPDATA')
            return os.path.join(appdata, 'CyneDirector')
        elif sys.platform == 'darwin':  # macOS
            return os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'CyneDirector')
        else:  # Linux
            return os.path.join(os.path.expanduser('~'), '.config', 'cynedirector')
    
    def _ensure_config_dir(self):
        """Ensure config directory exists."""
        os.makedirs(self.config_dir, exist_ok=True)
    
    def add_recent_project(self, project_path, project_name):
        """
        Add or update a project in the recent projects list.
        
        Args:
            project_path: Full path to project directory
            project_name: Name of the project
        """
        recent_projects = self.get_recent_projects()
        
        # Remove if already exists
        recent_projects = [p for p in recent_projects if p['path'] != project_path]
        
        # Add to front
        recent_projects.insert(0, {
            'name': project_name,
            'path': project_path,
            'last_accessed': time.time()
        })
        
        # Limit to max
        recent_projects = recent_projects[:self.max_recent_projects]
        
        # Save
        self._save_recent_projects(recent_projects)
    
    def get_recent_projects(self):
        """
        Get list of recent projects, with invalid projects removed.
        
        Returns:
            List of dicts with 'name', 'path', 'last_accessed' keys
        """
        if not os.path.exists(self.recent_projects_file):
            return []
        
        try:
            with open(self.recent_projects_file, 'r', encoding='utf-8') as f:
                recent_projects = json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
        
        # Validate and clean up
        valid_projects = []
        for project in recent_projects:
            project_path = project.get('path', '')
            project_file = os.path.join(project_path, f"{project.get('name', '')}.cyne")
            
            # Check if project file exists
            if os.path.exists(project_file):
                valid_projects.append(project)
        
        # If we removed invalid projects, save the cleaned list
        if len(valid_projects) != len(recent_projects):
            self._save_recent_projects(valid_projects)
        
        return valid_projects
    
    def remove_recent_project(self, project_path):
        """
        Remove a project from recent projects list.
        
        Args:
            project_path: Path to project to remove
        """
        recent_projects = self.get_recent_projects()
        recent_projects = [p for p in recent_projects if p['path'] != project_path]
        self._save_recent_projects(recent_projects)
    
    def _save_recent_projects(self, projects):
        """Save recent projects list to file."""
        try:
            with open(self.recent_projects_file, 'w', encoding='utf-8') as f:
                json.dump(projects, f, indent=2)
        except IOError as e:
            print(f"Error saving recent projects: {e}")
    
    def get_project_info(self, project_path):
        """
        Get project information including file count and last modified.
        
        Args:
            project_path: Path to project directory
            
        Returns:
            Dict with 'name', 'path', 'file_count', 'last_modified', 'exists'
        """
        project_name = os.path.basename(project_path)
        project_file = os.path.join(project_path, f"{project_name}.cyne")
        
        info = {
            'name': project_name,
            'path': project_path,
            'exists': os.path.exists(project_file),
            'file_count': 0,
            'last_modified': 0
        }
        
        if info['exists']:
            # Get file count from project file
            try:
                with open(project_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    files = data.get('files', [])
                    info['file_count'] = len(files)
            except (json.JSONDecodeError, IOError):
                pass
            
            # Get last modified time
            try:
                info['last_modified'] = os.path.getmtime(project_file)
            except OSError:
                pass
        
        return info

