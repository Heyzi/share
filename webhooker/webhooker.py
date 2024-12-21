from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import gitlab
import yaml
import logging
import json
from logging.handlers import TimedRotatingFileHandler
import sys
from typing import List, Optional, Tuple
from gitlab.exceptions import GitlabError
from functools import wraps

class JsonFormatter(logging.Formatter):
    def format(self, record):
        if hasattr(record, 'props'):
            return json.dumps(record.props)
        return json.dumps({
            'msg': record.getMessage(),
            'error': self.formatException(record.exc_info) if record.exc_info else None
        })

def setup_logging(config):
    logger = logging.getLogger()
    logger.setLevel(config['logging']['level'].upper())
    logger.handlers = []

    handlers = [
        logging.StreamHandler(sys.stdout),
        TimedRotatingFileHandler(
            filename=config['logging'].get('file', 'app.log'),
            when='midnight',
            interval=1,
            backupCount=7,
            encoding='utf-8'
        )
    ]

    formatter = JsonFormatter()
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

def load_config():
    try:
        with open('config.yml', 'r') as file:
            return yaml.safe_load(file)
    except (FileNotFoundError, yaml.YAMLError) as e:
        raise SystemExit(f"Config error: {e}")

config = load_config()
logger = setup_logging(config)

def init_gitlab_client():
    try:
        gl = gitlab.Gitlab(config['gitlab']['url'], private_token=config['gitlab']['token'])
        gl.auth()
        logger.info({'event': 'startup', 'msg': 'GitLab client initialized'})
        return gl
    except Exception as e:
        raise SystemExit(f"GitLab init failed: {e}")

gl = init_gitlab_client()
app = FastAPI()

class MergeRequestEvent(BaseModel):
    object_kind: str
    project: dict
    object_attributes: dict
    user: Optional[dict] = None

    class Config:
        extra = "allow"

def gitlab_error_handler(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error({'event': 'error', 'error': str(e), 'func': func.__name__})
            raise HTTPException(status_code=500, detail=str(e))
    return wrapper

class MergeRequestManager:
    LABEL_COLORS = {
        'mr-sync-success': '#1FCC56',
        'mr-sync-error': '#FF0000'
    }

    def __init__(self, project, config):
        self.project = project
        self.config = config
        self.mr_config = config['merge_request']
        self.default_branch = project.attributes['default_branch']

        self._ensure_status_labels()

    def _ensure_status_labels(self):
        status_labels = [
            {'name': name, 'color': color, 'description': f'MR sync {name.split("-")[-1]}'}
            for name, color in self.LABEL_COLORS.items()
        ]
        self.ensure_labels_exist(status_labels)

    def _should_process_mr(self, event: MergeRequestEvent) -> Tuple[bool, str]:
        if event.object_kind != 'merge_request':
            return False, 'not_mr'

        if event.object_attributes.get('action') not in self.mr_config['actions']:
            return False, f"action:{event.object_attributes.get('action')}"

        if not self._is_branch_allowed(event.object_attributes['target_branch']):
            return False, f"branch:{event.object_attributes['target_branch']}"

        return True, ''

    def _is_branch_allowed(self, branch: str) -> bool:
        return branch in self.mr_config.get('trigger_branches', [])

    def _get_label_names(self) -> List[str]:
        return [label['name'] for label in self.mr_config.get('labels', [])]

    def _extract_mr_details(self, event: MergeRequestEvent) -> dict:
        return {
            'source_branch': event.object_attributes['source_branch'],
            'target_branch': event.object_attributes['target_branch'],
            'title': event.object_attributes['title'],
            'original_mr_iid': event.object_attributes['iid'],
            'description': event.object_attributes.get('description', ''),
            'assignee_id': event.object_attributes.get('assignee_id'),
            'author_username': event.user.get('username') if event.user else None,
            'reviewers': event.object_attributes.get('reviewers', [])
        }

    def ensure_labels_exist(self, labels):
        existing = {l.name: l for l in self.project.labels.list(all=True)}
        for label in labels:
            try:
                if label['name'] in existing:
                    current = existing[label['name']]
                    if current.color != label['color']:
                        current.color = label['color']
                        current.save()
                else:
                    self.project.labels.create(label)
            except GitlabError as e:
                logger.error({'event': 'label_error', 'label': label['name'], 'error': str(e)})

    def _handle_branch_creation(self, new_branch_name: str) -> None:
        try:
            self.project.branches.get(new_branch_name)
        except GitlabError as e:
            if e.response_code == 404:
                self.project.branches.create({
                    'branch': new_branch_name,
                    'ref': self.default_branch
                })

    def _create_new_mr(self, new_branch_name: str, mr_details: dict):
        project_url = self.project.attributes['web_url']
        original_mr_url = f"{project_url}/-/merge_requests/{mr_details['original_mr_iid']}"

        # Create MR with basic info
        mr_params = {
            'source_branch': new_branch_name,
            'target_branch': self.default_branch,
            'title': f"{mr_details['title']} {self.mr_config['title_postfix']}",
            'description': mr_details['description'],
            'labels': self._get_label_names(),
            'remove_source_branch': self.mr_config.get('auto_delete_source', False)
        }
        if mr_details['assignee_id']:
            mr_params['assignee_id'] = mr_details['assignee_id']

        new_mr = self.project.mergerequests.create(mr_params)

        # Add comment with sync information
        comment = self.config['templates']['target_mr_comment'].format(
            original_mr_url=original_mr_url,
            source_branch=mr_details['source_branch'],
            target_branch=self.default_branch,
            original_description=mr_details['description']
        )
        new_mr.notes.create({'body': comment})

        return new_mr

    def _update_original_mr(self, mr_details: dict, new_mr) -> None:
        original_mr = self.project.mergerequests.get(mr_details['original_mr_iid'])

        # Update labels from config
        if 'labels' in self.mr_config:
            current_labels = set(original_mr.labels)
            new_labels = set(self._get_label_names())
            original_mr.labels = list(current_labels | new_labels)

        # Add comment with new MR info
        reviewers = [f"@{r['username']}" for r in mr_details['reviewers']]
        reviewers_str = ", ".join(reviewers) if reviewers else "No reviewers assigned"

        comment = self.config['templates']['source_mr_comment'].format(
            mr=new_mr,
            new_branch_name=new_mr.source_branch,
            default_branch=self.default_branch,
            author_username=mr_details['author_username'],
            original_mr_iid=mr_details['original_mr_iid'],
            reviewers=reviewers_str,
            reviewers_mentions=" ".join(reviewers)
        )

        original_mr.notes.create({'body': comment})
        original_mr.save()

    def _update_mr_labels(self, mr_iid: int, success: bool):
        try:
            mr = self.project.mergerequests.get(mr_iid)
            labels = set(mr.labels) - {'mr-sync-success', 'mr-sync-error'}
            labels.add('mr-sync-success' if success else 'mr-sync-error')
            mr.labels = list(labels)
            mr.save()
        except GitlabError as e:
            logger.error({'event': 'label_update_error', 'mr': mr_iid, 'error': str(e)})

    async def process_merge_request(self, event: MergeRequestEvent):
        mr_id = event.object_attributes['iid']
        user = event.user.get('username', 'unknown') if event.user else 'unknown'

        logger.info({
            'event': 'webhook',
            'mr': mr_id,
            'user': user,
            'action': event.object_attributes.get('action'),
            'source': event.object_attributes['source_branch'],
            'target': event.object_attributes['target_branch']
        })

        should_process, skip_reason = self._should_process_mr(event)
        if not should_process:
            logger.info({
                'event': 'skip',
                'mr': mr_id,
                'user': user,
                'reason': skip_reason
            })
            return

        try:
            mr_details = self._extract_mr_details(event)
            new_branch = f"{mr_details['source_branch']}{self.mr_config['branch_postfix']}"

            self._handle_branch_creation(new_branch)
            new_mr = self._create_new_mr(new_branch, mr_details)
            self._update_original_mr(mr_details, new_mr)
            self._update_mr_labels(mr_details['original_mr_iid'], True)

            logger.info({
                'event': 'success',
                'mr': mr_id,
                'user': user,
                'new_mr': new_mr.iid,
                'branch': new_branch
            })

        except Exception as e:
            logger.error({
                'event': 'error',
                'mr': mr_id,
                'user': user,
                'error': str(e)
            })
            self._update_mr_labels(mr_details['original_mr_iid'], False)
            raise

@app.post("/webhook")
@gitlab_error_handler
async def webhook_receiver(event: MergeRequestEvent):
    project = gl.projects.get(event.project['id'])
    mr_manager = MergeRequestManager(project, config)
    return await mr_manager.process_merge_request(event)

if __name__ == "__main__":
    import uvicorn
    server_config = config.get('server', {})
    uvicorn.run(app,
                host=server_config.get('host', '0.0.0.0'),
                port=server_config.get('port', 8000))