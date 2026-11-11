"""Command-line client for the phase 1 API (step 1.7).

Commands follow the API's roles: ``request`` (requester), ``reserve`` and
``submit`` (station), ``challenge`` (requester or station), ``review``
(reviewer), ``admin`` (admin), plus ``balance``. Each takes ``--api``,
``--key`` (or ``ORBIT_WATCH_API`` / ``ORBIT_WATCH_KEY``) and ``--json``.
Changes are sent with an idempotency key; it is printed, and passing it again
with ``--idempotency-key`` makes a retry safe.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from orbit_watch.canonical import sha256_bytes, write_text
from orbit_watch.client import ApiClient, Reply


def _client(args: argparse.Namespace) -> ApiClient:
    client = ApiClient(args.api, args.key)
    for warning in client.warnings:
        print(f"orbit-watch: warning: {warning}", file=sys.stderr)
    return client


def _post(
    args: argparse.Namespace,
    path: str,
    document: dict[str, Any] | None = None,
    *,
    body: bytes | None = None,
    content_type: str = "application/json",
    headers: dict[str, str] | None = None,
) -> Reply:
    client = _client(args)
    if body is None and document is not None:
        body = json.dumps(document).encode("utf-8")
    key = args.idempotency_key or str(uuid.uuid4())
    reply = client.request(
        "POST", path, body=body, content_type=content_type, idempotency_key=key, headers=headers
    )
    note = " (replayed: this call was already done; nothing changed)" if reply.replayed else ""
    print(f"idempotency key: {key}{note}", file=sys.stderr)
    return reply


def _print(args: argparse.Namespace, document: Any, human: str) -> None:
    if args.json:
        sys.stdout.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    else:
        print(human)


def describe_request(view: dict[str, Any]) -> str:
    summary, record = view["summary"], view["record"]
    lines = [
        f"Request {summary['request_id']}: {summary['status']}"
        + (f" ({summary['outcome']})" if summary["outcome"] else "")
    ]
    if summary["outcome_reason"]:
        lines.append(f"  reason: {summary['outcome_reason']}")
    if record.get("split"):
        split = record["split"]
        lines.append(
            f"  deposit: {split['total']} points (observer {split['observer']}, "
            f"reviewer {split['reviewer']} each, platform fee {split['platform_fee']})"
        )
    if record.get("reserved_by"):
        lines.append(
            f"  reserved by {record['reserved_by']} until {record['reservation_expires_at']}"
        )
    if record.get("observer"):
        lines.append(f"  delivered by {record['observer']} at {record['delivered_at']}")
    if summary["automated_verdict"]:
        lines.append(f"  automated verification: {summary['automated_verdict']}")
    if record.get("challenge_deadline") and summary["status"] == "challenge_period":
        lines.append(f"  challenge period ends {record['challenge_deadline']}")
    if summary["reviewers"]:
        votes = {r: ("approve" if a else "reject") for r, a in summary["votes"]}
        lines.append(
            "  reviewers: "
            + ", ".join(f"{r} ({votes.get(r, 'no vote yet')})" for r in summary["reviewers"])
        )
    if summary["settlement"]:
        payouts = summary["settlement"]["plan"]["payouts"]
        lines.append(
            "  settled: "
            + (
                ", ".join(f"{p['party']} +{p['points']} ({p['reason']})" for p in payouts)
                or "no points moved"
            )
        )
    return "\n".join(lines)


# ------------------------------------------------------------------ requester


def cmd_request_create(args: argparse.Namespace) -> int:
    document = json.loads(Path(args.file).read_text(encoding="utf-8"))
    terms: dict[str, Any] = {}
    for name in (
        "delivery_deadline",
        "reservation_hours",
        "challenge_period_hours",
        "review_hours",
        "embargo_days",
    ):
        value = getattr(args, name)
        if value is not None:
            terms[name] = value
    reply = _post(args, "/v1/requests", {"request": document, "terms": terms})
    view = reply.json()
    _print(args, view, describe_request(view))
    return 0


def _request_action(action: str):
    def run(args: argparse.Namespace) -> int:
        document = None
        if action == "fund":
            document = {
                "observer": args.observer,
                "reviewer": args.reviewer,
                "platform_fee": args.platform_fee,
            }
        view = _post(args, f"/v1/requests/{args.request_id}/{action}", document).json()
        _print(args, view, describe_request(view))
        return 0

    return run


def cmd_request_list(args: argparse.Namespace) -> int:
    result = _client(args).get("/v1/requests")
    lines = [
        f"{r['request_id']:<24}{r['status']:<18}{r['outcome'] or ''}" for r in result["requests"]
    ] or ["no requests"]
    _print(args, result, "\n".join(lines))
    return 0


def cmd_request_show(args: argparse.Namespace) -> int:
    view = _client(args).get(f"/v1/requests/{args.request_id}")
    _print(args, view, describe_request(view))
    return 0


def cmd_request_report(args: argparse.Namespace) -> int:
    reply = _client(args).request("GET", f"/v1/requests/{args.request_id}/report")
    if args.output:
        Path(args.output).write_bytes(reply.body)
        print(f"wrote {args.output}")
    else:
        from orbit_watch.verify.engine import render_text

        report = reply.json()
        if args.json:
            sys.stdout.write(reply.body.decode("utf-8"))
        else:
            sys.stdout.write(render_text(report))
    return 0


# ------------------------------------------------------------------ station


def cmd_reserve(args: argparse.Namespace) -> int:
    view = _post(args, f"/v1/requests/{args.request_id}/reserve").json()
    _print(args, view, describe_request(view))
    return 0


def cmd_submit(args: argparse.Namespace) -> int:
    from orbit_watch.documents import Delivery, is_delivery_manifest

    source = Path(args.delivery)
    data = source.read_bytes()
    request_id, fmt, declared = args.request, args.input_format, None
    if is_delivery_manifest(data):
        manifest = Delivery.parse(data)
        if request_id and request_id != manifest.request_id:
            raise ValueError(f"the manifest is for {manifest.request_id}, not {request_id}")
        request_id = manifest.request_id
        fmt = fmt or manifest.format
        declared = manifest.sha256
        data = (source.parent / manifest.file).read_bytes()
        if sha256_bytes(data) != declared:
            raise ValueError("the observation file does not match the hash in the manifest")
    if not request_id:
        raise ValueError("give --request for a plain observation file, or submit a manifest")
    path = f"/v1/requests/{request_id}/deliveries" + (f"?format={fmt}" if fmt else "")
    view = _post(
        args,
        path,
        body=data,
        content_type="application/octet-stream",
        headers={"Content-SHA256": declared or sha256_bytes(data)},
    ).json()
    _print(args, view, describe_request(view))
    return 0


def cmd_challenge(args: argparse.Namespace) -> int:
    view = _post(args, f"/v1/requests/{args.request_id}/challenge", {"reason": args.reason}).json()
    _print(args, view, describe_request(view))
    return 0


# ------------------------------------------------------------------ reviewer


def cmd_review_list(args: argparse.Namespace) -> int:
    result = _client(args).get("/v1/tasks")
    lines = [
        f"{t['task_id']}  automated: {t['automated_verdict']:<12} due {t['due']}\n"
        f"    challenge: {t['challenge_reason']}\n"
        f"    observations: /v1/files/{t['observations_sha256']}\n"
        f"    report: /v1/files/{t['report_sha256']}"
        for t in result["tasks"]
    ] or ["no open tasks"]
    _print(args, result, "\n".join(lines))
    return 0


def cmd_review_answer(args: argparse.Namespace) -> int:
    reply = _post(
        args,
        f"/v1/tasks/{args.task_id}/review",
        {"approve": args.decision == "approve", "reason": args.reason},
    )
    _print(args, reply.json(), f"recorded your answer to {args.task_id}")
    return 0


def cmd_review_profile(args: argparse.Namespace) -> int:
    profile = _client(args).get(f"/v1/reviewers/{args.reviewer}/profile")
    calibration, votes = profile["calibration"], profile["votes"]
    accuracy = calibration["accuracy"]
    human = (
        f"{profile['reviewer']}: calibration accuracy "
        f"{'-' if accuracy is None else f'{accuracy:.0%}'} "
        f"({calibration['correct']}/{calibration['answered']}), approval rate "
        f"{'-' if votes['approval_rate'] is None else f'{votes["approval_rate"]:.0%}'}"
        + (f", flags: {', '.join(profile['flags'])}" if profile["flags"] else "")
    )
    _print(args, profile, human)
    return 0


# ------------------------------------------------------------------ admin and balances


def cmd_admin_grant(args: argparse.Namespace) -> int:
    result = _post(args, "/v1/admin/grants", {"party": args.party, "points": args.points}).json()
    _print(args, result, f"{result['party']} now holds {result['points']} points")
    return 0


def cmd_admin_key(args: argparse.Namespace) -> int:
    result = _post(args, "/v1/admin/keys", {"party": args.party, "role": args.role}).json()
    if result["key"] is None:
        print(
            "this key was already created with that idempotency key; it is not shown again",
            file=sys.stderr,
        )
        return 1
    if args.output:
        write_text(args.output, result["key"] + "\n")
        Path(args.output).chmod(0o600)
        print(f"wrote the {args.role} key for {args.party} to {args.output}")
    else:
        print(result["key"])
        print(
            f"created a {args.role} key for {args.party}; it is shown only this once",
            file=sys.stderr,
        )
    return 0


def cmd_admin_tick(args: argparse.Namespace) -> int:
    result = _post(args, "/v1/admin/tick").json()
    changed = result["changed"]
    _print(args, result, "deadlines applied; changed: " + (", ".join(changed) or "nothing"))
    return 0


def cmd_balance(args: argparse.Namespace) -> int:
    result = _client(args).get(f"/v1/balances/{args.party}")
    _print(args, result, f"{result['party']}: {result['points']} points")
    return 0


# ------------------------------------------------------------------ public data (no key)


def cmd_public_list(args: argparse.Namespace) -> int:
    result = _client(args).request("GET", "/v1/public/requests", auth=False).json()
    lines = [
        f"{p['request_id']:<20}{p['licence']:<12}public since {p['public_from']}"
        for p in result["requests"]
    ] or ["no published requests"]
    _print(args, result, "\n".join(lines))
    return 0


def cmd_public_get(args: argparse.Namespace) -> int:
    client = _client(args)
    view = client.request("GET", f"/v1/public/requests/{args.request_id}", auth=False).json()
    publication = view["publication"]
    lines = [
        f"{args.request_id}: {view['summary']['outcome']}, {publication['licence']} "
        f"({publication['licence_url']})",
        f"  attribution: {publication['attribution']}",
    ]
    if publication["simulated"]:
        lines.append("  SIMULATED data")
    if args.download:
        target = Path(args.download)
        target.mkdir(parents=True, exist_ok=True)
        for item in publication["files"]:
            data = client.request("GET", item["url"], auth=False).body
            if sha256_bytes(data) != item["sha256"]:
                raise ValueError(f"downloaded {item['role']} does not match its SHA-256")
            path = target / f"{args.request_id}-{item['role']}.{_suffix(item['role'])}"
            path.write_bytes(data)
            lines.append(f"  {item['role']}: {path} (SHA-256 checked)")
        write_text(
            target / f"{args.request_id}-LICENCE.txt",
            f"{publication['licence']} {publication['licence_url']}\n"
            f"Attribution: {publication['attribution']}\n",
        )
    else:
        lines += [
            f"  {item['role']}: {item['url']} ({item['size']} bytes)"
            for item in publication["files"]
        ]
    _print(args, view, "\n".join(lines))
    return 0


def _suffix(role: str) -> str:
    return "json" if role in ("request", "report") else "dat"


# ------------------------------------------------------------------ parser


def add_commands(commands: argparse._SubParsersAction) -> None:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--api", help="API address (default: $ORBIT_WATCH_API or http://127.0.0.1:8000)"
    )
    common.add_argument(
        "--key",
        help="API key (prefer $ORBIT_WATCH_KEY: keys on the "
        "command line end up in the shell history)",
    )
    common.add_argument("--json", action="store_true", help="print the API's JSON answer")
    common.add_argument("--idempotency-key", help="reuse to retry a change safely")

    request = commands.add_parser(
        "request", help="requests: create, open, fund, cancel, list, show, report (API client)"
    )
    sub = request.add_subparsers(dest="request_command", metavar="command")
    sub.required = True
    create = sub.add_parser("create", parents=[common], help="create a request in draft")
    create.add_argument("file", help="request document (JSON)")
    create.add_argument("--delivery-deadline", help="UTC, YYYY-MM-DDThh:mm:ssZ")
    create.add_argument("--reservation-hours", type=float)
    create.add_argument("--challenge-period-hours", type=float)
    create.add_argument("--review-hours", type=float)
    create.add_argument("--embargo-days", type=int)
    create.set_defaults(handler=cmd_request_create)
    for action, text in (
        ("open", "publish a request (freezes its terms)"),
        ("cancel", "cancel a request before it is reserved"),
    ):
        parser = sub.add_parser(action, parents=[common], help=text)
        parser.add_argument("request_id")
        parser.set_defaults(handler=_request_action(action))
    fund = sub.add_parser("fund", parents=[common], help="lock a reward split and deposit points")
    fund.add_argument("request_id")
    fund.add_argument("--observer", type=int, required=True, help="points for the observer")
    fund.add_argument("--reviewer", type=int, required=True, help="points per completed review")
    fund.add_argument("--platform-fee", type=int, default=0)
    fund.set_defaults(handler=_request_action("fund"))
    listing = sub.add_parser("list", parents=[common], help="list requests")
    listing.set_defaults(handler=cmd_request_list)
    show = sub.add_parser("show", parents=[common], help="show a request")
    show.add_argument("request_id")
    show.set_defaults(handler=cmd_request_show)
    report = sub.add_parser("report", parents=[common], help="the automated verification report")
    report.add_argument("request_id")
    report.add_argument("-o", "--output", help="write the JSON report to this file")
    report.set_defaults(handler=cmd_request_report)

    reserve = commands.add_parser(
        "reserve", parents=[common], help="reserve a request (station, API client)"
    )
    reserve.add_argument("request_id")
    reserve.set_defaults(handler=cmd_reserve)

    submit = commands.add_parser(
        "submit",
        parents=[common],
        help="deliver observations for a reserved request (station, API client)",
        description="Send a delivery manifest (or a plain observation file with --request) to "
        "the API. The file is verified at once; the result opens the challenge period.",
    )
    submit.add_argument("delivery", help="delivery manifest, or an observation file")
    submit.add_argument("--request", help="request id (for a plain observation file)")
    submit.add_argument("--from", dest="input_format", choices=("json", "iod", "tdm"))
    submit.set_defaults(handler=cmd_submit)

    challenge = commands.add_parser(
        "challenge", parents=[common], help="challenge an automated result (API client)"
    )
    challenge.add_argument("request_id")
    challenge.add_argument("--reason", required=True)
    challenge.set_defaults(handler=cmd_challenge)

    review = commands.add_parser("review", help="reviewer tasks (API client)")
    sub = review.add_subparsers(dest="review_command", metavar="command")
    sub.required = True
    sub.add_parser("list", parents=[common], help="your open tasks").set_defaults(
        handler=cmd_review_list
    )
    answer = sub.add_parser("answer", parents=[common], help="answer a task")
    answer.add_argument("task_id")
    decision = answer.add_mutually_exclusive_group(required=True)
    decision.add_argument("--approve", dest="decision", action="store_const", const="approve")
    decision.add_argument("--reject", dest="decision", action="store_const", const="reject")
    answer.add_argument("--reason", required=True)
    answer.set_defaults(handler=cmd_review_answer)
    profile = sub.add_parser("profile", parents=[common], help="a reviewer's accuracy profile")
    profile.add_argument("reviewer")
    profile.set_defaults(handler=cmd_review_profile)

    admin = commands.add_parser("admin", help="administration (API client)")
    sub = admin.add_subparsers(dest="admin_command", metavar="command")
    sub.required = True
    grant = sub.add_parser("grant", parents=[common], help="give points to a party")
    grant.add_argument("party")
    grant.add_argument("points", type=int)
    grant.set_defaults(handler=cmd_admin_grant)
    key = sub.add_parser("key", parents=[common], help="create an API key (shown once)")
    key.add_argument("party")
    key.add_argument("role", choices=("requester", "station", "reviewer", "admin"))
    key.add_argument("-o", "--output", help="write the key to this file (mode 600)")
    key.set_defaults(handler=cmd_admin_key)
    sub.add_parser("tick", parents=[common], help="apply passed deadlines").set_defaults(
        handler=cmd_admin_tick
    )

    public = commands.add_parser("public", help="published requests and files (no key needed)")
    sub = public.add_subparsers(dest="public_command", metavar="command")
    sub.required = True
    sub.add_parser("list", parents=[common], help="published requests").set_defaults(
        handler=cmd_public_list
    )
    get = sub.add_parser("get", parents=[common], help="a published request and its files")
    get.add_argument("request_id")
    get.add_argument("--download", help="download the files (hash-checked) into this directory")
    get.set_defaults(handler=cmd_public_get)

    balance = commands.add_parser("balance", parents=[common], help="points held (API client)")
    balance.add_argument("party")
    balance.set_defaults(handler=cmd_balance)
