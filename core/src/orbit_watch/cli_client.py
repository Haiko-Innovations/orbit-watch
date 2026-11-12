"""Command-line client for the request API (steps 1.7 and 2.6).

Commands follow the API's roles: ``request`` (requester), ``reserve`` and
``submit`` (station), ``challenge`` (requester or station), ``review``
(reviewer), ``admin`` (admin), plus ``balance``. Each takes ``--api``,
``--key`` (or ``ORBIT_WATCH_API`` / ``ORBIT_WATCH_KEY``) and ``--json``.
Changes are sent with an idempotency key; it is printed, and passing it again
with ``--idempotency-key`` makes a retry safe.

**On a testnet chain** (step 2.6) the API answers a change to a funded request
with transactions to sign. The command line signs them with the user's own
encrypted keystore (``--keystore``, for example one made with ``cast wallet
import``), sends them through ``--rpc`` and reports each hash to the API; the
key never leaves this process. With ``--unsigned`` it prints them instead, for
another wallet. ``wallet``, ``tx`` and ``chain`` manage the rest.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from orbit_watch.canonical import sha256_bytes, write_text
from orbit_watch.client import ApiClient, ClientError, Reply


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


def _chain_info(args: argparse.Namespace) -> dict[str, Any] | None:
    """The API's chain, or None if it does not run on one."""
    if not hasattr(args, "_chain"):
        try:
            args._chain = _client(args).request("GET", "/v1/chain", auth=False).json()
        except ClientError as error:
            if error.code != "not_on_chain":
                raise
            args._chain = None
    return args._chain


def _wallet(args: argparse.Namespace, *, send: bool = True):
    """The user's own wallet: an encrypted keystore, opened in this process only."""
    try:
        from orbit_watch.chain.wallet import Wallet, load_keystore, open_wallet, read_password
    except ImportError:
        raise ValueError(
            'signing needs the optional "evm" dependencies: pip install "orbit-watch[evm]"'
        ) from None
    keystore = args.keystore or os.environ.get("ORBIT_WATCH_KEYSTORE")
    rpc = args.rpc or os.environ.get("ORBIT_WATCH_RPC")
    if send and not rpc:
        rpc = _public_rpc(args)
    if not keystore or (send and not rpc):
        raise ValueError(
            "to sign, give your encrypted keystore (--keystore or $ORBIT_WATCH_KEYSTORE, for "
            "example one made with 'cast wallet import') and the chain's RPC endpoint (--rpc "
            "or $ORBIT_WATCH_RPC); or use --unsigned to sign with another wallet"
        )
    if not send:
        return Wallet(None, load_keystore(keystore, read_password(args.password_file)))  # type: ignore[arg-type]
    return open_wallet(rpc, keystore, args.password_file)


def _public_rpc(args: argparse.Namespace) -> str | None:
    """The public RPC endpoint of the API's chain, if it has one (Base Sepolia)."""
    from orbit_watch.chain.networks import public_rpc

    info = _chain_info(args)
    return public_rpc(info["chain_id"]) if info else None


def _report(args: argparse.Namespace, tx_hash: str) -> dict[str, Any]:
    reply = _client(args).request(
        "POST",
        "/v1/transactions",
        body=json.dumps({"tx_hash": tx_hash}).encode("utf-8"),
        idempotency_key=f"report-{tx_hash}",
    )
    result = reply.json()
    print(describe_transaction(result["transaction"]), file=sys.stderr)
    return result


def _finish(args: argparse.Namespace, reply: Reply) -> Any:
    """The API's answer. When it asks for signatures (202), sign each transaction with the
    user's own keystore, send it and report it; with ``--unsigned``, print them instead."""
    if reply.status != 202:
        return reply.json()
    prepared = reply.json()
    print(f"orbit-watch: {prepared['notice']}", file=sys.stderr)
    if args.unsigned:
        sys.stdout.write(json.dumps(prepared, indent=2) + "\n")
        for item in prepared["sign"]:
            tx = item["transaction"]
            print(
                f"to sign: {item['action']} from {tx['from']}, for example: cast send "
                f"{tx['to']} --data {tx['data']} --rpc-url <RPC> --account <name>",
                file=sys.stderr,
            )
        print(
            "send them in this order, then report each hash: orbit-watch tx report <hash>",
            file=sys.stderr,
        )
        return None
    wallet = _wallet(args)
    result = None
    for item in prepared["sign"]:
        tx_hash = wallet.send(item["transaction"])
        print(f"sent {item['action']}: {tx_hash}", file=sys.stderr)
        result = _report(args, tx_hash)
    return result


def _show(args: argparse.Namespace, result: Any, human: str | None = None) -> int:
    """Print a request view, or what reporting a transaction gave."""
    if result is None:  # printed for an external wallet
        return 0
    if "transaction" in result and "request" in result:
        view = result["request"]
        if view is None:
            human = f"{describe_transaction(result['transaction'])} ({result['notice']})"
            _print(args, result, human)
            return 0
        result = view
    _print(args, result, human or describe_request(result))
    return 0


def _print(args: argparse.Namespace, document: Any, human: str) -> None:
    if args.json:
        sys.stdout.write(json.dumps(document, indent=2, ensure_ascii=False) + "\n")
    else:
        print(human)


def amount(value: int, token: dict[str, Any] | None) -> str:
    """Points, or token units with the token's decimals (``135 TESTUSD``)."""
    if token is None:
        return f"{value} points"
    whole = Decimal(value).scaleb(-int(token["decimals"])).normalize()
    return f"{whole:f} {token['symbol']}"


def describe_transaction(transaction: dict[str, Any]) -> str:
    where = transaction["explorer"] or transaction["tx_hash"]
    error = f" ({transaction['error']})" if transaction["error"] else ""
    request = f" for {transaction['request_id']}" if transaction["request_id"] else ""
    return f"{transaction['status']}: {transaction['action']}{request} {where}{error}"


def describe_request(view: dict[str, Any]) -> str:
    summary, record = view["summary"], view["record"]
    chain = view.get("chain")
    token = chain["token"] if chain else None
    lines = [
        f"Request {summary['request_id']}: {summary['status']}"
        + (f" ({summary['outcome']})" if summary["outcome"] else "")
    ]
    if summary["outcome_reason"]:
        lines.append(f"  reason: {summary['outcome_reason']}")
    if record.get("split"):
        split = record["split"]
        if token is None:
            lines.append(
                f"  deposit: {split['total']} points (observer {split['observer']}, "
                f"reviewer {split['reviewer']} each, platform fee {split['platform_fee']})"
            )
        else:
            lines.append(
                f"  deposit: {amount(split['total'], token)} (observer "
                f"{amount(split['observer'], token)}, reviewer {amount(split['reviewer'], token)}"
                f" each, platform fee {amount(split['platform_fee'], token)})"
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
        moved = [
            f"{p['party']} +{p['points'] if token is None else amount(p['points'], token)}"
            f" ({p['reason']})"
            for p in payouts
        ]
        nothing = "no points moved" if token is None else "nothing moved"
        lines.append("  settled: " + (", ".join(moved) or nothing))
    if chain:
        lines.append(f"  on chain ({chain['notice']}): {chain['status'] or 'not funded on chain'}")
        for event in chain["events"]:
            lines.append(
                f"    {event['event']:<21} block {event['block']:<6} "
                f"{event['explorer'] or event['tx_hash']}"
            )
        lines += [f"    {describe_transaction(t)}" for t in chain["transactions"]]
        lines += [f"    conflict: {c['code']}: {c['message']}" for c in chain["conflicts"]]
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


def _split(args: argparse.Namespace) -> dict[str, int]:
    """Whole points, or token amounts (``1.5``) in the token's smallest units on a chain."""
    chain = _chain_info(args)
    decimals = int(chain["token"]["decimals"]) if chain else 0
    split = {}
    for name in ("observer", "reviewer", "platform_fee"):
        text = getattr(args, name)
        try:
            value = Decimal(text).scaleb(decimals)
        except InvalidOperation:
            raise ValueError(f"--{name.replace('_', '-')}: not a number: {text!r}") from None
        if value != value.to_integral_value() or value < 0:
            unit = f"{chain['token']['symbol']} with {decimals} decimals" if chain else "points"
            raise ValueError(f"--{name.replace('_', '-')}: {text} is not a whole amount of {unit}")
        split[name] = int(value)
    return split


def _request_action(action: str):
    def run(args: argparse.Namespace) -> int:
        document = _split(args) if action == "fund" else None
        reply = _post(args, f"/v1/requests/{args.request_id}/{action}", document)
        return _show(args, _finish(args, reply))

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
    return _show(args, _finish(args, _post(args, f"/v1/requests/{args.request_id}/reserve")))


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
    reply = _post(
        args,
        path,
        body=data,
        content_type="application/octet-stream",
        headers={"Content-SHA256": declared or sha256_bytes(data)},
    )
    return _show(args, _finish(args, reply))


def cmd_challenge(args: argparse.Namespace) -> int:
    reply = _post(args, f"/v1/requests/{args.request_id}/challenge", {"reason": args.reason})
    return _show(args, _finish(args, reply))


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
    result = _finish(args, reply)
    if result is not None and "recorded" in result:
        _print(args, result, f"recorded your answer to {args.task_id}")
        return 0
    return _show(args, result)


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
    if "points" in result:
        _print(args, result, f"{result['party']}: {result['points']} points")
    elif result["address"] is None:
        _print(args, result, f"{result['party']}: no wallet registered ({result['notice']})")
    else:
        token = result["token"]
        _print(
            args,
            result,
            f"{result['party']}: {amount(result['balance'], token)} in {result['address']}, "
            f"{amount(result['withdrawable'], token)} to withdraw ({result['notice']})",
        )
    return 0


# ------------------------------------------------------------------ chain (step 2.6)


def cmd_chain(args: argparse.Namespace) -> int:
    info = _chain_info(args)
    if info is None:
        print("this API does not run on a chain: payments are points")
        return 0
    token = info["token"]
    lines = [
        f"{info['network']} (chain {info['chain_id']}): {info['notice']}",
        f"  escrow    {info['escrow']}",
        f"  reviewers {info['registry']} (registry)",
        f"  token     {token['symbol']} {token['address']} ({token['decimals']} decimals)",
        f"  EAS       {info['eas']}",
        f"  schemas   result {info['result_schema']}",
        f"            vote   {info['vote_schema']}",
        f"  verifier  {info['verifier']}",
        f"  explorer  {info['explorer'] or 'none (local chain)'}",
        f"  read up to block {info['synced_block']}",
    ]
    _print(args, info, "\n".join(lines))
    return 0


def cmd_wallet_register(args: argparse.Namespace) -> int:
    view = _client(args).get("/v1/wallet")
    if args.print_message:
        print(view["message"])
        return 0
    if args.address or args.signature:
        if not (args.address and args.signature):
            raise ValueError("give --address and --signature together (from another wallet)")
        address, signature = args.address, args.signature
    else:
        wallet = _wallet(args, send=False)
        address, signature = wallet.address, wallet.sign_message(view["message"])
    result = _post(args, "/v1/wallet", {"address": address, "signature": signature}).json()
    _print(args, result, f"{result['party']}: wallet {result['address']} ({result['notice']})")
    return 0


def cmd_wallet_withdraw(args: argparse.Namespace) -> int:
    return _show(args, _finish(args, _post(args, "/v1/wallet/withdraw")))


def cmd_tx_list(args: argparse.Namespace) -> int:
    path = "/v1/transactions" + (f"?request={args.request}" if args.request else "")
    result = _client(args).get(path)
    lines = [describe_transaction(t) for t in result["transactions"]] or ["no transactions"]
    _print(args, result, "\n".join([*lines, f"({result['notice']})"]))
    return 0


def cmd_tx_report(args: argparse.Namespace) -> int:
    return _show(args, _report(args, args.tx_hash))


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
    signing = common.add_argument_group("signing on a testnet chain")
    signing.add_argument(
        "--keystore",
        help="your encrypted keystore, e.g. ~/.foundry/keystores/<name> "
        "(default $ORBIT_WATCH_KEYSTORE); the key never leaves this process",
    )
    signing.add_argument(
        "--password-file",
        help="file with the keystore's password (default $ORBIT_WATCH_PASSWORD_FILE; "
        "otherwise it is asked for)",
    )
    signing.add_argument(
        "--rpc",
        help="the chain's RPC endpoint (default $ORBIT_WATCH_RPC, or Base Sepolia's public one)",
    )
    signing.add_argument(
        "--unsigned",
        action="store_true",
        help="print the transactions to sign with another wallet instead",
    )

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
    fund = sub.add_parser(
        "fund",
        parents=[common],
        help="lock a reward split and deposit it (points, or testnet tokens on a chain)",
    )
    fund.add_argument("request_id")
    fund.add_argument(
        "--observer", required=True, help="for the observer (points, or e.g. 1.5 on a chain)"
    )
    fund.add_argument("--reviewer", required=True, help="per completed review")
    fund.add_argument("--platform-fee", default="0")
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

    balance = commands.add_parser(
        "balance", parents=[common], help="points held, or a wallet's tokens (API client)"
    )
    balance.add_argument("party")
    balance.set_defaults(handler=cmd_balance)

    commands.add_parser(
        "chain", parents=[common], help="the testnet chain the API runs on (API client)"
    ).set_defaults(handler=cmd_chain)

    wallet = commands.add_parser("wallet", help="your wallet on a testnet chain (API client)")
    sub = wallet.add_subparsers(dest="wallet_command", metavar="command")
    sub.required = True
    register = sub.add_parser(
        "register",
        parents=[common],
        help="register your wallet address, proven by a signature",
        description="Sign the API's registration message with your keystore, or print it "
        "(--print-message) to sign with another wallet (for example 'cast wallet sign') and "
        "pass --address and --signature.",
    )
    register.add_argument("--print-message", action="store_true")
    register.add_argument("--address", help="with --signature: a signature from another wallet")
    register.add_argument("--signature")
    register.set_defaults(handler=cmd_wallet_register)
    sub.add_parser(
        "withdraw", parents=[common], help="transfer everything credited to you"
    ).set_defaults(handler=cmd_wallet_withdraw)

    tx = commands.add_parser("tx", help="transactions on a testnet chain (API client)")
    sub = tx.add_subparsers(dest="tx_command", metavar="command")
    sub.required = True
    listing = sub.add_parser("list", parents=[common], help="pending, confirmed and failed")
    listing.add_argument("--request", help="only this request's")
    listing.set_defaults(handler=cmd_tx_list)
    report = sub.add_parser(
        "report", parents=[common], help="report a transaction sent with another wallet"
    )
    report.add_argument("tx_hash")
    report.set_defaults(handler=cmd_tx_report)
