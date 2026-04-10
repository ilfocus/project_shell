#!/usr/bin/env python3
"""Sync Tencent Lighthouse firewall rules to the current public IP.

This script is designed for one-shot execution. Pair it with macOS launchd
to run every few minutes.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


API_HOST = "lighthouse.tencentcloudapi.com"
API_SERVICE = "lighthouse"
API_VERSION = "2020-03-24"
API_ENDPOINT = f"https://{API_HOST}"
DEFAULT_IP_CHECK_URLS = [
    "https://api.ipify.org",
    "https://checkip.amazonaws.com",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
    "https://ident.me",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Update Tencent Lighthouse firewall rules to this machine's current public IP."
    )
    parser.add_argument(
        "--config",
        default=str(Path(__file__).with_name("tencent_lighthouse_ip_sync.json")),
        help="Path to config JSON file.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Update firewall even if the cached IP has not changed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print intended changes without calling Tencent Cloud APIs.",
    )
    return parser


def setup_logging(log_file: str | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_path = Path(log_file).expanduser().resolve()
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
        except (PermissionError, OSError) as exc:
            print(f"Warning: Could not create log file at {log_path}: {exc}", file=sys.stderr)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def load_json_file(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return copy.deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json_file(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    required_fields = ["secret_id", "secret_key", "region", "instance_id", "managed_rules"]
    missing = [field for field in required_fields if not raw.get(field)]
    if missing:
        raise ValueError(f"Missing required config fields: {', '.join(missing)}")

    managed_rules = raw["managed_rules"]
    if not isinstance(managed_rules, list) or not managed_rules:
        raise ValueError("managed_rules must be a non-empty array.")

    validated_rules: list[dict[str, str]] = []
    for index, rule in enumerate(managed_rules):
        if not isinstance(rule, dict):
            raise ValueError(f"managed_rules[{index}] must be an object.")

        protocol = str(rule.get("protocol", "")).upper()
        port = str(rule.get("port", "")).strip()
        action = str(rule.get("action", "ACCEPT")).upper()
        description = str(rule.get("description", f"auto-ip-sync {protocol}:{port}")).strip()

        if not protocol or not port:
            raise ValueError(f"managed_rules[{index}] must include protocol and port.")
        if action not in {"ACCEPT", "DROP"}:
            raise ValueError(f"managed_rules[{index}].action must be ACCEPT or DROP.")

        validated_rules.append(
            {
                "Protocol": protocol,
                "Port": port,
                "Action": action,
                "FirewallRuleDescription": description[:64],
            }
        )

    return {
        "secret_id": str(raw["secret_id"]).strip(),
        "secret_key": str(raw["secret_key"]).strip(),
        "region": str(raw["region"]).strip(),
        "instance_id": str(raw["instance_id"]).strip(),
        "managed_rules": validated_rules,
        "ip_check_urls": raw.get("ip_check_urls") or DEFAULT_IP_CHECK_URLS,
        "request_timeout_seconds": int(raw.get("request_timeout_seconds", 10)),
        "state_file": str(
            raw.get("state_file")
            or Path(__file__).with_name("tencent_lighthouse_ip_sync.state.json")
        ),
        "log_file": str(
            raw.get("log_file")
            or Path(__file__).with_name("tencent_lighthouse_ip_sync.log")
        ),
        "dry_run": bool(raw.get("dry_run", False)),
    }


def fetch_public_ip(ip_check_urls: list[str], timeout_seconds: int) -> str:
    headers = {"User-Agent": "Mozilla/5.0 ip-sync-script"}
    last_error: Exception | None = None

    for round_number in range(1, 4):
        for url in ip_check_urls:
            try:
                request = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                    body = response.read().decode("utf-8").strip()
                ip = str(ipaddress.ip_address(body))
                logging.info("Current public IP detected as %s via %s", ip, url)
                return ip
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logging.warning(
                    "Fetch public IP failed on round %s from %s: %s",
                    round_number,
                    url,
                    exc,
                )

        if round_number < 3:
            time.sleep(2)

    raise RuntimeError(f"Unable to determine public IP: {last_error}")


def sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def tc3_headers(secret_id: str, secret_key: str, action: str, payload: dict[str, Any], region: str) -> dict[str, str]:
    timestamp = int(time.time())
    date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    hashed_request_payload = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

    canonical_headers = f"content-type:application/json\nhost:{API_HOST}\n"
    signed_headers = "content-type;host"
    canonical_request = "\n".join(
        [
            "POST",
            "/",
            "",
            canonical_headers,
            signed_headers,
            hashed_request_payload,
        ]
    )

    credential_scope = f"{date}/{API_SERVICE}/tc3_request"
    string_to_sign = "\n".join(
        [
            "TC3-HMAC-SHA256",
            str(timestamp),
            credential_scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )

    secret_date = sign(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = sign(secret_date, API_SERVICE)
    secret_signing = sign(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    authorization = (
        "TC3-HMAC-SHA256 "
        f"Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    return {
        "Authorization": authorization,
        "Content-Type": "application/json",
        "Host": API_HOST,
        "X-TC-Action": action,
        "X-TC-Version": API_VERSION,
        "X-TC-Region": region,
        "X-TC-Timestamp": str(timestamp),
    }


def call_lighthouse_api(
    secret_id: str,
    secret_key: str,
    region: str,
    action: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    headers = tc3_headers(secret_id, secret_key, action, payload, region)
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(API_ENDPOINT, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            response_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{action} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{action} failed: {exc}") from exc

    data = json.loads(response_text)
    response_data = data.get("Response", {})
    if "Error" in response_data:
        err = response_data["Error"]
        raise RuntimeError(f"{action} failed: {err.get('Code')}: {err.get('Message')}")
    return response_data


def normalize_existing_rule(rule: dict[str, Any]) -> dict[str, str]:
    return {
        "Protocol": str(rule.get("Protocol", "")).upper(),
        "Port": str(rule.get("Port", "")).strip(),
        "CidrBlock": str(rule.get("CidrBlock", "")).strip(),
        "Action": str(rule.get("Action", "")).upper(),
        "FirewallRuleDescription": str(rule.get("FirewallRuleDescription", "")).strip()[:64],
    }


def build_rule_map_key(rule: dict[str, str]) -> tuple[str, str, str]:
    return (rule["Protocol"], rule["Port"], rule["Action"])


def dedupe_rules(rules: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str, str]] = set()
    deduped: list[dict[str, str]] = []

    for rule in rules:
        rule_key = (
            rule["Protocol"],
            rule["Port"],
            rule["Action"],
            rule["CidrBlock"],
        )
        if rule_key in seen:
            continue
        seen.add(rule_key)
        deduped.append(rule)

    return deduped


def merge_rules(
    existing_rules: list[dict[str, Any]],
    managed_rules: list[dict[str, str]],
    current_ip: str,
) -> tuple[list[dict[str, str]], int]:
    target_cidr = f"{current_ip}/32"
    managed_keys = {build_rule_map_key(rule) for rule in managed_rules}

    preserved_rules: list[dict[str, str]] = []
    replaced_count = 0

    for existing in existing_rules:
        normalized = normalize_existing_rule(existing)
        if build_rule_map_key(normalized) in managed_keys:
            replaced_count += 1
            continue
        preserved_rules.append(normalized)

    new_rules = preserved_rules + [
        {
            **rule,
            "CidrBlock": target_cidr,
        }
        for rule in managed_rules
    ]

    return dedupe_rules(new_rules), replaced_count


def describe_firewall(config: dict[str, Any]) -> dict[str, Any]:
    return call_lighthouse_api(
        config["secret_id"],
        config["secret_key"],
        config["region"],
        "DescribeFirewallRules",
        {
            "InstanceId": config["instance_id"],
            "Offset": 0,
            "Limit": 100,
        },
        config["request_timeout_seconds"],
    )


def modify_firewall(config: dict[str, Any], firewall_rules: list[dict[str, str]], firewall_version: int) -> dict[str, Any]:
    return call_lighthouse_api(
        config["secret_id"],
        config["secret_key"],
        config["region"],
        "ModifyFirewallRules",
        {
            "InstanceId": config["instance_id"],
            "FirewallRules": firewall_rules,
            "FirewallVersion": firewall_version,
        },
        config["request_timeout_seconds"],
    )


def main() -> int:
    args = build_parser().parse_args()
    config_path = Path(args.config).expanduser().resolve()
    raw_config = load_json_file(config_path)
    if not raw_config:
        raise FileNotFoundError(
            f"Config file not found: {config_path}. Copy the example JSON file and fill in your values first."
        )

    config = validate_config(raw_config)
    config["dry_run"] = bool(config["dry_run"] or args.dry_run)
    setup_logging(config["log_file"])

    state_path = Path(config["state_file"]).expanduser()
    state = load_json_file(state_path, default={}) or {}

    current_ip = fetch_public_ip(config["ip_check_urls"], config["request_timeout_seconds"])
    last_ip = state.get("public_ip")
    logging.info("Last cached public IP: %s", last_ip or "<none>")

    if last_ip == current_ip and not args.force and not config["dry_run"]:
        logging.info("Public IP unchanged, skipping Tencent Cloud update.")
        return 0

    describe_response = describe_firewall(config)
    existing_rules = describe_response.get("FirewallRuleSet", [])
    firewall_version = int(describe_response.get("FirewallVersion", 0))

    merged_rules, replaced_count = merge_rules(existing_rules, config["managed_rules"], current_ip)
    logging.info(
        "Prepared %s firewall rules total. Replaced %s managed rule(s).",
        len(merged_rules),
        replaced_count,
    )

    if config["dry_run"]:
        logging.info("Dry run enabled, not calling ModifyFirewallRules.")
        print(json.dumps({"FirewallRules": merged_rules}, indent=2, ensure_ascii=True))
        return 0

    modify_response = modify_firewall(config, merged_rules, firewall_version)
    request_id = modify_response.get("RequestId", "<unknown>")
    logging.info("Firewall updated successfully. RequestId=%s", request_id)

    dump_json_file(
        state_path,
        {
            "public_ip": current_ip,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id,
        },
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        logging.exception("IP sync failed: %s", exc)
        raise SystemExit(1)
