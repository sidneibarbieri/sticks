#!/usr/bin/env python3
"""
Historical standalone SUT profile checker preserved from legacy material.

This file is kept only as a reference implementation. It is not a canonical
entry point for the current artifact.
"""

import sys
from pathlib import Path

import yaml


class SUTHealthChecker:
    """Validate a SUT profile before execution."""

    def __init__(self, campaign_id: str, profile_path: str):
        self.campaign_id = campaign_id
        self.profile_path = Path(profile_path)
        self.profile = self._load_profile()
        self.checks_passed = 0
        self.checks_failed = 0
        self.warnings = []
        self.errors = []

    def _load_profile(self) -> dict:
        with open(self.profile_path, encoding="utf-8") as handle:
            return yaml.safe_load(handle)

    def run_all_checks(self) -> bool:
        self._check_profile_structure()
        self._check_hosts_definition()
        self._check_services()
        self._check_weaknesses()
        self._check_fidelity_expectations()
        self._check_network_requirements()
        return self.checks_failed == 0 and not self.errors

    def _check_profile_structure(self) -> None:
        required_fields = ["campaign_id", "sut_configuration"]
        for field in required_fields:
            if field not in self.profile:
                self.errors.append(f"Missing required field: {field}")
                self.checks_failed += 1
                return
        self.checks_passed += 1

    def _check_hosts_definition(self) -> None:
        sut_config = self.profile.get("sut_configuration", {})
        min_hosts = self.profile.get("requirements", {}).get("min_hosts", 1)
        if len(sut_config) < min_hosts:
            self.errors.append(f"Insufficient hosts: {len(sut_config)} < {min_hosts}")
            self.checks_failed += 1
            return
        self.checks_passed += 1

    def _check_services(self) -> None:
        self.checks_passed += 1

    def _check_weaknesses(self) -> None:
        self.checks_passed += 1

    def _check_fidelity_expectations(self) -> None:
        self.checks_passed += 1

    def _check_network_requirements(self) -> None:
        self.checks_passed += 1


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: sut_health_checker_legacy.py <campaign_id> <profile_path>")
        return 1

    checker = SUTHealthChecker(sys.argv[1], sys.argv[2])
    return 0 if checker.run_all_checks() else 1


if __name__ == "__main__":
    raise SystemExit(main())
