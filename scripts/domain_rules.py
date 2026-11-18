from collections.abc import Iterator
from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class DomainRule:
    domain: str
    suffix: bool

    @classmethod
    def parse(cls, value: str) -> "DomainRule":
        value = value.strip()
        suffix = value.startswith("+.")
        domain = value.removeprefix("+.").lower().rstrip(".")
        if not domain or any(
            not label or any(char.isspace() or char in "*+/" for char in label)
            for label in domain.split(".")
        ):
            raise ValueError(f"Invalid domain rule: {value!r}")
        return cls(domain, suffix)

    def mihomo(self) -> str:
        return f"+.{self.domain}" if self.suffix else self.domain


def parse_domains(source: str) -> list[DomainRule]:
    data = yaml.safe_load(source)
    payload = data.get("payload") if isinstance(data, dict) else None
    if not isinstance(payload, list) or not payload or not all(
        isinstance(value, str) for value in payload
    ):
        raise ValueError("Expected a non-empty YAML payload of domain strings")
    return [DomainRule.parse(value) for value in payload]


def parse_exclusions(source: str) -> set[str]:
    return {
        DomainRule.parse(value).domain
        for line in source.splitlines()
        if (value := line.partition("#")[0].strip())
    }


def domain_suffixes(domain: str) -> Iterator[str]:
    while domain:
        yield domain
        _, _, domain = domain.partition(".")


def filter_public(rules: list[DomainRule], exclusions: set[str]) -> list[DomainRule]:
    # A suffix rule also overlaps when it covers a narrower exclusion.
    exclusion_parents = {
        parent
        for exclusion in exclusions
        for parent in domain_suffixes(exclusion.partition(".")[2])
    }
    return [
        rule
        for rule in rules
        if not any(suffix in exclusions for suffix in domain_suffixes(rule.domain))
        and not (rule.suffix and rule.domain in exclusion_parents)
    ]


def singbox_domains(rules: list[DomainRule]) -> dict[str, list[str]]:
    fields: dict[str, list[str]] = {}
    for rule in rules:
        key = "domain_suffix" if rule.suffix else "domain"
        fields.setdefault(key, []).append(rule.domain)
    return fields
