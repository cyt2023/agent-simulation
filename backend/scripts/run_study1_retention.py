"""Create or execute controlled Study 1 retention jobs.

Example:
    python backend/scripts/run_study1_retention.py dry-run SESSION_ID
    python backend/scripts/run_study1_retention.py execute JOB_ID CHECKSUM --reason "Participant withdrawal"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from study1.media_gateway import create_media_gateway_from_env
from study1.retention_service import InMemoryRetentionStore, RetentionService


def main() -> int:
    parser = argparse.ArgumentParser(description="Study 1 retention workflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run = subparsers.add_parser("dry-run")
    dry_run.add_argument("session_id")
    dry_run.add_argument("--requested-by", default="privacy-admin")
    dry_run.add_argument("--subject", action="append", default=[])

    execute = subparsers.add_parser("execute")
    execute.add_argument("job_id")
    execute.add_argument("checksum")
    execute.add_argument("--approved-by", default="privacy-admin")
    execute.add_argument("--reason", required=True)

    args = parser.parse_args()
    store = InMemoryRetentionStore()
    service = RetentionService(
        store=store,
        media_gateway=(
            create_media_gateway_from_env()
            if os.environ.get("MEDIA_GATEWAY_MODE", "mock") != "mock"
            else None
        ),
    )

    if args.command == "dry-run":
        job = service.create_dry_run(
            args.session_id,
            requested_by=args.requested_by,
            subject_pseudo_ids=args.subject,
        )
    else:
        job = service.execute(
            args.job_id,
            approved_manifest_checksum=args.checksum,
            approved_by=args.approved_by,
            reason=args.reason,
        )
    print(json.dumps(job.public_dict(include_subjects=True), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
