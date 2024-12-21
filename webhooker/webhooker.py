from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import gitlab
import yaml
import logging
from typing import List, Optional
from gitlab.exceptions import GitlabError

# Load configuration file
try:
    with open('config.yml', 'r') as file:
        config = yaml.safe_load(file)
except FileNotFoundError:
    raise SystemExit("Config file 'config.yml' not found")
except yaml.YAMLError as e:
    raise SystemExit(f"Error parsing config file: {e}")

# Configure logger
logging.basicConfig(
    level=config['logging']['level'].upper(),
    format=config['logging'].get('format', '%(asctime)s - %(levelname)s - %(message)s')
)
logger = logging.getLogger(__name__)

app = FastAPI()

# Initialize GitLab client
try:
    gl = gitlab.Gitlab(
        config['gitlab']['url'],
        private_token=config['gitlab']['token']
    )
    gl.auth()
    logger.info(f"GitLab client initialized: {config['gitlab']['url']}")
except KeyError as e:
    logger.error(f"Missing config parameter: {e}")
    raise SystemExit(f"Missing required config parameter: {e}")
except GitlabError as e:
    logger.error(f"GitLab auth failed: {e}")
    raise SystemExit(f"Failed to authenticate with GitLab: {e}")

class MergeRequestEvent(BaseModel):
    object_kind: str
    project: dict
    object_attributes: dict
    user: Optional[dict]

def ensure_labels_exist(project, config_labels: List[dict]):
    """
    Ensure all configured labels exist in project with correct colors.
    Creates or updates labels as needed.
    """
    try:
        existing_labels = {label.name: label for label in project.labels.list(all=True)}

        for label_config in config_labels:
            name = label_config['name']
            color = label_config['color'].lstrip('#')  # Remove # from color

            if name in existing_labels:
                label = existing_labels[name]
                if label.color != color:
                    label.color = color
                    label.save()
                    logger.info(f"Updated color for label '{name}' to {color}")
            else:
                project.labels.create({
                    'name': name,
                    'color': color
                })
                logger.info(f"Created new label '{name}' with color {color}")
    except GitlabError as e:
        logger.error(f"Failed to manage labels: {e}")
        raise

def get_label_names_from_config(config: dict) -> List[str]:
    """Extract just the label names from config"""
    if 'labels' not in config['merge_request']:
        return []
    return [label['name'] for label in config['merge_request']['labels']]

def is_branch_allowed(branch_name: str, config: dict) -> bool:
    """
    Check if branch is in whitelist (trigger_branches)
    If trigger_branches is empty - no branches are allowed
    """
    trigger_branches = config['merge_request'].get('trigger_branches', [])
    return bool(trigger_branches and branch_name in trigger_branches)

def format_template(template: str, **kwargs) -> str:
    """Format template with provided variables"""
    try:
        return template.format(**kwargs)
    except KeyError as e:
        logger.error(f"Missing template variable: {e}")
        return template

def add_error_label(project, mr_iid: int):
    """Helper function to add error label and remove success label from MR"""
    try:
        mr = project.mergerequests.get(mr_iid)
        current_labels = mr.labels

        # Remove success label if exists
        if "mr-sync-success" in current_labels:
            current_labels.remove("mr-sync-success")

        # Add error label if not exists
        if "mr-sync-error" not in current_labels:
            current_labels.append("mr-sync-error")

        mr.labels = current_labels
        mr.save()
        logger.info(f"Updated labels for MR {mr_iid} (added error, removed success)")
    except GitlabError as e:
        logger.error(f"Failed to update labels for MR {mr_iid}: {e}")

@app.post("/webhook", status_code=200)
async def webhook_receiver(event: MergeRequestEvent):
    """
    Webhook receiver for GitLab merge request events.
    Creates a new branch from default branch and creates MR to the default branch.
    """
    try:
        logger.info(f"Received webhook: {event.object_kind} for project {event.project.get('id')}")

        if event.object_kind != 'merge_request':
            logger.warning(f"Invalid webhook type: {event.object_kind}")
            return

        # Extract MR details early
        project_id = event.project['id']
        source_branch = event.object_attributes['source_branch']
        target_branch = event.object_attributes['target_branch']
        mr_title = event.object_attributes['title']
        action = event.object_attributes.get('action')
        original_mr_iid = event.object_attributes['iid']
        title_postfix = config['merge_request']['title_postfix']

        # Get assignee and author details
        assignee_id = event.object_attributes.get('assignee_id')
        author_username = event.user.get('username') if event.user else None

        # Early return for non-configured actions
        if action not in config['merge_request']['actions']:
            logger.info(f"Skipping merge request: action {action} not in configured actions")
            return

        # Get project and ensure labels exist
        try:
            project = gl.projects.get(project_id)
            default_branch = project.default_branch

            # Ensure all configured labels exist with correct colors
            if 'labels' in config['merge_request']:
                ensure_labels_exist(project, config['merge_request']['labels'])

        except GitlabError as e:
            logger.error(f"Failed to get project {project_id}: {e}")
            raise HTTPException(status_code=500)

        # Handle update action separately
        if action == 'update':
            if title_postfix in mr_title:
                logger.info(f"Updating MR {original_mr_iid}")
            return

        # Check for branch whitelist
        if not is_branch_allowed(target_branch, config):
            logger.info(f"Skipping merge request: {target_branch} not in trigger branches whitelist")
            return

        # Prevent processing if:
        # 1. Source is default branch
        # 2. MR title already contains postfix
        # 3. Source branch already contains postfix
        if (source_branch == default_branch or
            title_postfix in mr_title or
            config['merge_request']['branch_postfix'] in source_branch):
            logger.info(
                f"Skipping merge request: source={source_branch}, "
                f"title='{mr_title}' (preventing duplicate processing)"
            )
            return

        # Create new branch name
        branch_postfix = config['merge_request']['branch_postfix']
        new_branch_name = f"{source_branch}{branch_postfix}"

        # Check if branch already exists and create new one from default
        try:
            try:
                existing_branch = project.branches.get(new_branch_name)
                logger.info(f"Branch {new_branch_name} already exists")
            except GitlabError as e:
                if e.response_code == 404:
                    project.branches.create({
                        'branch': new_branch_name,
                        'ref': default_branch
                    })
                    logger.info(f"Created new branch: {new_branch_name} from {default_branch}")
                else:
                    raise e

            # Check for existing merge requests
            existing_mrs = project.mergerequests.list(
                state='opened',
                source_branch=new_branch_name,
                target_branch=default_branch
            )

            if existing_mrs:
                logger.info(f"MR from {new_branch_name} to {default_branch} already exists (MR ID: {existing_mrs[0].iid})")

                # Format and add comment about existing MR
                comment = format_template(
                    config['templates']['existing_mr'],
                    mr_iid=existing_mrs[0].iid,
                    source_branch=new_branch_name,
                    target_branch=default_branch
                )

                original_mr = project.mergerequests.get(original_mr_iid)
                original_mr.notes.create({'body': comment})
                return

        except GitlabError as e:
            logger.error(f"Failed to manage branch {new_branch_name}: {e}")
            add_error_label(project, original_mr_iid)
            raise HTTPException(status_code=500)

        # Create new merge request
        try:
            new_title = f"{mr_title} {title_postfix}"
            mr_params = {
                'source_branch': new_branch_name,
                'target_branch': default_branch,
                'title': new_title,
                'description': (
                    f'{event.object_attributes.get("description", "")}\n\n'
                    f'Original merge request: !{original_mr_iid}'
                ),
                'labels': get_label_names_from_config(config),
                'remove_source_branch': config['merge_request'].get('auto_delete_source', False)
            }

            # Add assignee if exists
            if assignee_id:
                mr_params['assignee_id'] = assignee_id

            mr = project.mergerequests.create(mr_params)

            logger.info(
                f"Created MR - ID: {mr.iid}, "
                f"Title: '{new_title}', "
                f"Source: {new_branch_name}, "
                f"Target: {default_branch}, "
                f"Assignee: {assignee_id}"
            )

            # Update original MR
            try:
                original_mr = project.mergerequests.get(original_mr_iid)

                # Add labels from config and success label
                current_labels = original_mr.labels
                if 'labels' in config['merge_request']:
                    new_labels = get_label_names_from_config(config)
                    current_labels = list(set(current_labels + new_labels))

                if "mr-sync-success" not in current_labels:
                    current_labels.append("mr-sync-success")

                original_mr.labels = current_labels

                # Get reviewers for template
                reviewers = [f"@{r['username']}" for r in event.object_attributes.get('reviewers', [])]
                reviewers_str = ", ".join(reviewers) if reviewers else "No reviewers assigned"

                # Format and add informative comment
                comment = format_template(
                    config['templates']['mr_comment'],
                    mr=mr,
                    new_branch_name=new_branch_name,
                    default_branch=default_branch,
                    author_username=author_username,
                    original_mr_iid=original_mr_iid,
                    reviewers=reviewers_str,
                    reviewers_mentions=" ".join(reviewers)
                )

                original_mr.notes.create({'body': comment})

                # Save all changes
                original_mr.save()
                logger.info(f"Updated original MR {original_mr_iid} with labels and comment")

            except GitlabError as e:
                logger.error(f"Failed to update original MR: {e}")
                add_error_label(project, original_mr_iid)

        except GitlabError as e:
            logger.error(f"Failed to create merge request: {e}")
            add_error_label(project, original_mr_iid)
            raise HTTPException(status_code=500)

    except KeyError as e:
        logger.error(f"Missing required field: {e}")
        try:
            add_error_label(project, original_mr_iid)
        except:
            pass
        raise HTTPException(status_code=400)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        try:
            add_error_label(project, original_mr_iid)
        except:
            pass
        raise HTTPException(status_code=500)

if __name__ == "__main__":
    import uvicorn
    server_config = config.get('server', {})
    host = server_config.get('host', '0.0.0.0')
    port = server_config.get('port', 8000)

    logger.info(f"Starting server at {host}:{port} with log level: {config['logging']['level']}")
    uvicorn.run(app, host=host, port=port)