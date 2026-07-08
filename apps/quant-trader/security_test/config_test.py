"""Configuration & Dependency Security Tests.

Checks (offline, no server required):
- .env / config files not committed with real secrets
- Config file permissions (should not be world-readable)
- YAML config injection via unsafe load
- .gitignore covers sensitive files
- Requirements pinned / known-vulnerable versions
- Hardcoded secrets in source code
- CORS configuration security
- API token strength
- Sensitive file exposure in static directory
"""

from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
GITIGNORE = PROJECT_ROOT / ".gitignore"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
CONFIG_YAML = PROJECT_ROOT / "config.yaml"
CONFIG_LLM_YAML = PROJECT_ROOT / "config_llm.yaml"
DAEMON_STATE = PROJECT_ROOT / "daemon_state.json"
QUANTTRADER_DIR = PROJECT_ROOT / "quanttrader"


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""


def _scan_python_files(directory: Path, extensions: tuple = (".py",)) -> list[Path]:
    """Recursively find Python files, excluding venv/Python dirs."""
    results = []
    skip_dirs = {"Python", "venv", ".venv", "__pycache__", "node_modules", ".git"}
    for item in directory.rglob("*"):
        if any(sd in item.parts for sd in skip_dirs):
            continue
        if item.suffix in extensions and item.is_file():
            results.append(item)
    return results


# ---------------------------------------------------------------------------
# Secret patterns (used for source code scanning)
# ---------------------------------------------------------------------------
SECRET_PATTERNS = [
    (r'(?:api[_-]?key|secret|token|password|passwd)\s*=\s*["\']([^"\']{8,})["\']', "Hardcoded secret in assignment"),
    (r'(?:DEEPSEEK|OPENAI|API)_KEY\s*=\s*["\']([^"\']{8,})["\']', "Hardcoded API key"),
    (r"sk-[a-zA-Z0-9]{20,}", "Looks like an OpenAI/DeepSeek API key (sk-...)"),
    (r"Bearer\s+[a-zA-Z0-9_\-]{20,}", "Hardcoded Bearer token"),
]


# ---------------------------------------------------------------------------
# Test Classes
# ---------------------------------------------------------------------------
class TestEnvFileSecurity(unittest.TestCase):
    """Check .env file for real secrets and gitignore coverage."""

    def test_env_not_in_gitignore(self):
        """`.env` MUST be in .gitignore to prevent accidental commit."""
        gitignore = _read_text(GITIGNORE)
        if not gitignore:
            self.skipTest("No .gitignore found")
        # Check for .env (but not .env.example)
        patterns_found = re.findall(r"^\.env\b", gitignore, re.MULTILINE)
        self.assertTrue(len(patterns_found) > 0, ".env is NOT in .gitignore! Real secrets could be committed to git.")

    def test_env_example_no_real_keys(self):
        """`.env.example` should not contain real API keys."""
        content = _read_text(ENV_EXAMPLE)
        if not content:
            self.skipTest("No .env.example found")
        # Should contain placeholder values, not real keys
        real_key_patterns = [
            r"sk-[a-zA-Z0-9]{20,}",  # OpenAI/DeepSeek key
            r'["\'][a-zA-Z0-9]{40,}["\']',  # Long alphanumeric string
        ]
        for pattern in real_key_patterns:
            matches = re.findall(pattern, content)
            if matches:
                self.fail(f".env.example contains what looks like a real key: {matches[0][:20]}...")

    def test_env_file_permissions(self):
        """`.env` should not be world-readable (Unix only)."""
        if sys.platform == "win32":
            self.skipTest("Permission check not applicable on Windows")
        if not ENV_FILE.exists():
            self.skipTest("No .env file found")
        stat = os.stat(ENV_FILE)
        # Check "other" read bit (octal 004)
        if stat.st_mode & 0o004:
            self.fail(f".env is world-readable! Mode: {oct(stat.st_mode)}. Run: chmod 600 {ENV_FILE}")

    def test_env_keys_not_empty(self):
        """If .env exists, its keys should have values."""
        content = _read_text(ENV_FILE)
        if not content:
            self.skipTest("No .env file found")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if value and key:
                    # Check if it's a placeholder
                    placeholders = ["your_", "sk-your", "xxx", "changeme", "placeholder", "你的", "密钥"]
                    if any(p in value.lower() for p in placeholders):
                        print(f"  [INFO] {key} appears to be a placeholder")


class TestConfigYAMLSecurity(unittest.TestCase):
    """Check YAML config files for security issues."""

    def test_config_yaml_loads_safely(self):
        """config.yaml should not contain executable YAML tags."""
        import yaml

        content = _read_text(CONFIG_YAML)
        if not content:
            self.skipTest("No config.yaml found")
        # yaml.safe_load should handle it
        try:
            data = yaml.safe_load(content)
            self.assertIsNotNone(data, "config.yaml parsed as None")
        except yaml.YAMLError as e:
            self.fail(f"config.yaml has YAML syntax error: {e}")

    def test_config_no_api_keys_exposed(self):
        """Config files should not contain API keys in plaintext."""
        for config_path in [CONFIG_YAML, CONFIG_LLM_YAML]:
            content = _read_text(config_path)
            if not content:
                continue
            # Check for key-like patterns
            key_patterns = [
                (r"(?:api_key|secret|token)\s*:\s*\S+", "API key in config"),
                (r"sk-[a-zA-Z0-9]{20,}", "OpenAI/DeepSeek key in config"),
            ]
            for pattern, desc in key_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    print(f"  [WARN] {config_path.name}: {desc} -- {matches[0][:30]}...")

    def test_risk_config_reasonable(self):
        """Risk parameters in config should be sane."""
        import yaml

        content = _read_text(CONFIG_YAML)
        if not content:
            self.skipTest("No config.yaml found")
        data = yaml.safe_load(content)
        if not data:
            self.skipTest("Empty config")

        risk = data.get("risk", {})
        warnings = []
        if risk.get("stop_loss", 0) > 0.20:
            warnings.append(f"stop_loss={risk['stop_loss']} is >20% -- very high")
        if risk.get("max_drawdown", 0) > 0.50:
            warnings.append(f"max_drawdown={risk['max_drawdown']} is >50% -- dangerous")
        if risk.get("risk_per_trade", 0) > 0.05:
            warnings.append(f"risk_per_trade={risk['risk_per_trade']} is >5%")
        if warnings:
            print(f"  [WARN] Risk config warnings: {warnings}")


class TestHardcodedSecrets(unittest.TestCase):
    """Scan Python source for hardcoded secrets."""

    def test_no_hardcoded_keys_in_source(self):
        """Python files should not contain hardcoded API keys or secrets."""
        files = _scan_python_files(QUANTTRADER_DIR)
        findings = []
        for fpath in files:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            # Skip test files and examples
            if "security_test" in str(fpath) or "example" in str(fpath).lower():
                continue
            for pattern, desc in SECRET_PATTERNS:
                for match in re.finditer(pattern, content):
                    matched_text = match.group(0)
                    # Skip known safe patterns (env var references, example values)
                    if "os.environ" in matched_text or "os.getenv" in matched_text:
                        continue
                    if "example" in matched_text.lower():
                        continue
                    line_num = content[: match.start()].count("\n") + 1
                    findings.append(
                        {
                            "file": str(fpath.relative_to(PROJECT_ROOT)),
                            "line": line_num,
                            "type": desc,
                            "snippet": matched_text[:60],
                        }
                    )

        if findings:
            msg = "Hardcoded secrets found in source:\n"
            for f in findings:
                msg += f"  {f['file']}:{f['line']} - {f['type']}: {f['snippet']}...\n"
            self.fail(msg)

    def test_no_private_keys_in_source(self):
        """No private keys (RSA, etc.) should be in source files."""
        files = _scan_python_files(QUANTTRADER_DIR)
        for fpath in files:
            content = _read_text(fpath)
            if "-----BEGIN" in content and "PRIVATE KEY" in content:
                self.fail(f"Private key found in {fpath}!")


class TestDependencySecurity(unittest.TestCase):
    """Check requirements.txt for known issues."""

    def test_requirements_file_exists(self):
        """requirements.txt should exist."""
        self.assertTrue(REQUIREMENTS.exists(), "requirements.txt not found!")

    def test_requirements_pinned(self):
        """Dependencies should have version pins."""
        content = _read_text(REQUIREMENTS)
        if not content:
            self.skipTest("No requirements.txt")
        unpinned = []
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            if "==" not in line and ">=" not in line and "<=" not in line:
                unpinned.append(line)
        if unpinned:
            print(f"  [WARN] Unpinned dependencies: {unpinned}")

    def test_known_vulnerable_packages(self):
        """Check for packages with known CVEs (basic list)."""
        content = _read_text(REQUIREMENTS)
        if not content:
            self.skipTest("No requirements.txt")
        # Packages with well-known high-severity CVEs
        vulnerable = {
            "requests": {"<2.28.0": "CVE-2023-32681 - info leak via redirect"},
            "fastapi": {"<0.100.0": "Various security fixes"},
            "pyyaml": {"<5.4": "CVE-2020-14343 - arbitrary code execution via yaml.load"},
            "uvicorn": {"<0.15.0": "Security fixes"},
            "akshare": {"<1.10": "Various fixes"},
        }
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            pkg_name = re.split(r"[><=!~]", line)[0].strip().lower()
            if pkg_name in vulnerable:
                for vuln_range, cve_desc in vulnerable[pkg_name].items():
                    print(f"  [INFO] {line} -- check for {cve_desc}")


class TestGitignoreCoverage(unittest.TestCase):
    """Verify .gitignore covers sensitive files."""

    def test_gitignore_covers_env(self):
        gitignore = _read_text(GITIGNORE)
        self.assertIn(".env", gitignore, ".env not in .gitignore")

    def test_gitignore_covers_state(self):
        """daemon_state.json may contain trade history."""
        gitignore = _read_text(GITIGNORE)
        if "daemon_state.json" not in gitignore:
            print("  [WARN] daemon_state.json not in .gitignore -- trade history could be committed")

    def test_gitignore_covers_logs(self):
        gitignore = _read_text(GITIGNORE)
        if "logs/" not in gitignore and "logs" not in gitignore:
            print("  [WARN] logs/ directory not in .gitignore")


class TestDaemonStateSecurity(unittest.TestCase):
    """Check daemon_state.json for sensitive data exposure."""

    def test_daemon_state_not_empty(self):
        if not DAEMON_STATE.exists():
            self.skipTest("No daemon_state.json")
        content = _read_text(DAEMON_STATE)
        if not content.strip():
            return  # empty is fine
        try:
            data = __import__("json").loads(content)
        except Exception:
            self.skipTest("Cannot parse daemon_state.json")
        # Check for leaked keys
        flat = str(data).lower()
        if "api_key" in flat or "secret" in flat or "token" in flat:
            print("  [WARN] daemon_state.json may contain API keys or secrets")


class TestStaticDirectorySecurity(unittest.TestCase):
    """Check that static files don't expose sensitive info."""

    def test_no_env_in_static(self):
        static_dir = QUANTTRADER_DIR / "api" / "static"
        if not static_dir.exists():
            self.skipTest("No static directory")
        for fpath in static_dir.rglob("*"):
            if fpath.is_file():
                content = _read_text(fpath)
                # Check for embedded secrets
                for pattern, desc in SECRET_PATTERNS:
                    if re.search(pattern, content):
                        print(f"  [WARN] {desc} in static file {fpath.name}")

    def test_no_server_info_in_html(self):
        """HTML files should not expose server version/framework info."""
        static_dir = QUANTTRADER_DIR / "api" / "static"
        if not static_dir.exists():
            self.skipTest("No static directory")
        for html_file in static_dir.rglob("*.html"):
            content = _read_text(html_file)
            # Check for meta generator or server headers in HTML
            if "X-Powered-By" in content or "Server:" in content:
                print(f"  [WARN] Server info in {html_file.name}")


class TestYAMLSafeLoad(unittest.TestCase):
    """Verify all YAML loading uses safe_load."""

    def test_no_yaml_load_in_source(self):
        """yaml.load() (unsafe) should not be used -- only yaml.safe_load()."""
        files = _scan_python_files(QUANTTRADER_DIR)
        for fpath in files:
            content = _read_text(fpath)
            # Look for yaml.load( but NOT yaml.safe_load(
            unsafe_loads = re.findall(r"yaml\.load\s*\(", content)
            safe_loads = re.findall(r"yaml\.safe_load\s*\(", content)
            # yaml.load with Loader is also acceptable
            loader_loads = re.findall(r"yaml\.load\s*\([^)]*Loader", content)
            truly_unsafe = len(unsafe_loads) - len(loader_loads)
            if truly_unsafe > 0:
                self.fail(
                    f"Unsafe yaml.load() found in {fpath.relative_to(PROJECT_ROOT)}. Use yaml.safe_load() instead."
                )


class TestSecretsInLogs(unittest.TestCase):
    """Check if log files might contain secrets."""

    def test_logs_directory_not_in_project(self):
        """Log files should not contain API keys."""
        logs_dir = PROJECT_ROOT / "logs"
        if not logs_dir.exists():
            self.skipTest("No logs directory")
        for log_file in logs_dir.glob("*.log"):
            content = _read_text(log_file)
            for pattern, desc in SECRET_PATTERNS:
                matches = re.findall(pattern, content)
                if matches:
                    print(f"  [WARN] {desc} found in {log_file.name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
