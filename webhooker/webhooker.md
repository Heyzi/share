# GitLab MR Automation Service

Service for automating GitLab merge requests workflow. Creates additional MRs to default branch and manages branch cleanup.

# Core functionality:

1. MR Creation Workflow:
  - Listens for new MRs to configured trigger branches
  - Creates new branch from default branch with configured postfix
  - Creates new MR to default branch
  - Adds labels and comments to original MR
  - Copies assignee from original MR

2. Branch Cleanup:
  - Monitors updates to MRs with branch postfix
  - Sets remove_source_branch flag automatically

3. Error Handling:
  - Adds error labels on failures
  - Removes success labels when errors occur
  - Comprehensive logging
  - Retries failed GitLab API calls

4. Security:
  - Webhook token validation
  - Input data validation 
  - Configuration validation

# Configuration:

Required config.yml structure:
- gitlab: API connection settings
- logging: Log configuration
- merge_request: MR workflow settings
- server: Web server settings

# Installation:
1. Clone repository
2. Install dependencies: pip install -r requirements.txt
3. Copy config.yml.example to config.yml and configure
4. Run: python app.py

# Requirements:
- Python 3.8+
- FastAPI
- python-gitlab
- PyYAML 
- uvicorn
