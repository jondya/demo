import argparse
import json
import subprocess
from ipaddress import IPv4Network, collapse_addresses
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.request import urlopen

import yaml

from domain_rules import (
    DomainRule,
    filter_public,
    parse_domains,
    parse_exclusions,
    singbox_domains,
)

ROOT = Path(__file__).resolve().parents[1]
LOYALSOLDIER = "https://raw.githubusercontent.com/Loyalsoldier/clash-rules/release"
CHNROUTES = "https://chnroutes2.cdn.skk.moe/chnroutes.txt"
SING_BOX_RULESET_VERSION = 4


def fetch(url: str) -> str:
    with urlopen(url, timeout=30) as response:
        return response.read().decode("utf-8")


def load_domains(name: str) -> list[DomainRule]:
    source = fetch(f"{LOYALSOLDIER}/{name}.txt")
    try:
        return parse_domains(source)
    except (ValueError, yaml.YAMLError) as error:
        raise ValueError(f"Invalid upstream {name}.txt: {error}") from error


def build_public(output: Path, extra_exclusions: Path) -> None:
    direct = load_domains("direct")
    exclusions = parse_exclusions(extra_exclusions.read_text(encoding="utf-8"))
    for name in ("apple", "google"):
        for rule in load_domains(name):
            if not rule.suffix:
                raise ValueError(f"Expected a suffix in {name}.txt: {rule.domain}")
            exclusions.add(rule.domain)

    public = filter_public(direct, exclusions)
    write_rules(output, "public", [rule.mihomo() for rule in public], singbox_domains(public))
    print(f"public: retained {len(public)} of {len(direct)} rules")


def build_router(output: Path) -> None:
    router = load_domains("private")
    write_rules(output, "router", [rule.mihomo() for rule in router], singbox_domains(router))
    print(f"router: {len(router)} rules")


def build_cncidr(output: Path) -> None:
    networks = [
        IPv4Network(line)
        for raw_line in fetch(CHNROUTES).splitlines()
        if (line := raw_line.strip()) and not line.startswith("#")
    ]
    cidrs = [str(network) for network in networks]
    write_rules(output, "cncidr", cidrs, {"ip_cidr": cidrs})

    elements = ",\n".join(f"        {network}" for network in collapse_addresses(networks))
    (output / "cncidr.nft").write_text(
        "# Include this file inside an inet table.\n"
        "set cncidr_v4 {\n"
        "    type ipv4_addr;\n"
        "    flags interval;\n"
        "    auto-merge;\n"
        "    elements = {\n"
        f"{elements}\n"
        "    };\n"
        "}\n",
        encoding="utf-8",
    )
    print(f"cncidr: {len(cidrs)} IPv4 networks")


def write_rules(
    output: Path, name: str, payload: list[str], singbox_rule: dict[str, list[str]]
) -> None:
    if not payload:
        raise ValueError(f"{name} rule set is empty")

    with TemporaryDirectory() as directory:
        source = Path(directory) / f"{name}.json"
        source.write_text(
            json.dumps({"version": SING_BOX_RULESET_VERSION, "rules": [singbox_rule]}),
            encoding="utf-8",
        )
        subprocess.run(
            ["sing-box", "rule-set", "compile", "--output", str(output / f"{name}.srs"), str(source)],
            check=True,
        )

    (output / f"{name}.txt").write_text(
        yaml.safe_dump({"payload": payload}, allow_unicode=True), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Mihomo, sing-box and nftables rule sets.")
    parser.add_argument("--output", type=Path, default=ROOT / "site")
    parser.add_argument("--exclusions", type=Path, default=ROOT / "public-exclusions.txt")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=args.output.parent) as directory:
        staging = Path(directory)
        build_public(staging, args.exclusions)
        build_router(staging)
        build_cncidr(staging)

        args.output.mkdir(exist_ok=True)
        for artifact in staging.iterdir():
            artifact.replace(args.output / artifact.name)


if __name__ == "__main__":
    main()
