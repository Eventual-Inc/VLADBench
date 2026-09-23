"""Upload results/dataset/ (parquet tables, card, figures) to the Hugging Face dataset. The Hub is content-addressed,
so only changed files are sent, in one commit."""
from __future__ import annotations

from pathlib import Path

from . import paths
from .record import Record

DATASET_REPO = "Eventual-Inc/VLADBench-reeval"


def commit_message(record: Record) -> str:
    return f"Results as of {record['generated_at'][:19]}Z: {len(record['models'])} models, {record['dataset']['responses']:,} answers"


def publish_dataset(record: Record, *, repo: str = DATASET_REPO, folder: Path = paths.DATASET, token: str) -> str:
    """Upload the folder; returns the commit URL."""
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(repo, repo_type="dataset", exist_ok=True)
    return api.upload_folder(repo_id=repo, repo_type="dataset", folder_path=str(folder), commit_message=commit_message(record)).commit_url
