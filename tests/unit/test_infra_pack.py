# SPDX-License-Identifier: Apache-2.0
"""The optional infra pack: agents, skills and the deploy workflow template."""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hooks" / "lib"))
import config  # noqa: E402

spec = importlib.util.spec_from_file_location("render", ROOT / "scripts" / "render.py")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)

INFRA_AGENTS = {
    "infra-researcher",
    "iac-builder",
    "k8s-manifest-writer",
    "cicd-pipeline-builder",
    "infra-validator",
    "monitoring-config-writer",
    "argocd-config-writer",
    "argocd-validator",
    "gitops-pipeline-builder",
}
ARGOCD_AGENTS = {"argocd-config-writer", "argocd-validator", "gitops-pipeline-builder"}
WORKFLOW = ".github/workflows/stagegate-deploy.yml"
# Details of the production system the pack was extracted from must not appear.
PROJECT_SPECIFIC = re.compile(
    r"t3\.(medium|large)|Keycloak|Postal|Harbor|14584|python-json-logger|"
    r"secret/[a-z]+/config|github\.com/[A-Z]",
)
PINNED = re.compile(r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")

CONFIGS = {
    "argocd": {"infra": {"enabled": True, "cluster": "demo", "learning_notes": True}},
    "kubectl": {"infra": {"enabled": True, "gitops": "none", "secrets": "none"}},
}


def collect(name: str, tmp_path: Path) -> dict[str, str]:
    cfg = config._merge(config.DEFAULTS, CONFIGS[name])
    return render.collect(cfg, tmp_path / "shop-api", packs=("core", "infra"))


def agent_names(files: dict[str, str]) -> set[str]:
    return {Path(p).stem for p in files if p.startswith(".claude/agents/")}


def test_argocd_agents_only_with_argocd(tmp_path: Path) -> None:
    assert INFRA_AGENTS <= agent_names(collect("argocd", tmp_path))
    names = agent_names(collect("kubectl", tmp_path))
    assert not names & ARGOCD_AGENTS
    assert INFRA_AGENTS - ARGOCD_AGENTS <= names


@pytest.mark.parametrize("cfg_name", list(CONFIGS))
def test_infra_agents_valid(cfg_name: str, tmp_path: Path) -> None:
    files = collect(cfg_name, tmp_path)
    for path, text in files.items():
        if not path.startswith(".claude/agents/") or Path(path).stem not in INFRA_AGENTS:
            continue
        meta = yaml.safe_load(text.split("---\n", 2)[1])
        assert meta["name"] == Path(path).stem
        if meta["name"].endswith(("validator", "researcher")):
            assert set(meta["tools"]) == {"Read", "Grep", "Glob"}
        body = text.split("---\n", 2)[2]
        assert body.count("SPDX-License-Identifier") == 1, "partials must not repeat the header"
        if meta["name"] != "infra-researcher" and not meta["name"].endswith("validator"):
            assert "no credentials, no applies, no live cluster" in body
        notes = "## Learning notes" in body
        assert notes == CONFIGS[cfg_name]["infra"].get("learning_notes", False)


@pytest.mark.parametrize("cfg_name", list(CONFIGS))
def test_workflow_is_valid_and_hardened(cfg_name: str, tmp_path: Path) -> None:
    text = collect(cfg_name, tmp_path)[WORKFLOW]
    wf = yaml.safe_load(text)
    assert wf["permissions"] == {"contents": "read"}
    assert wf["concurrency"]["cancel-in-progress"] is False
    jobs = wf["jobs"]
    expected = ["tests", "plan", "infrastructure", "platform", "deploy"]
    if cfg_name == "argocd":
        expected += ["release", "verify"]
    assert list(jobs) == expected
    assert jobs["plan"]["needs"] == "tests" and jobs["infrastructure"]["needs"] == "plan"
    # Approval happens after the plan is published; apply refuses a changed plan.
    plan_steps = str(jobs["plan"]["steps"])
    apply_steps = str(jobs["infrastructure"]["steps"])
    assert "GITHUB_STEP_SUMMARY" in plan_steps and "fingerprint" in plan_steps
    assert "REVIEWED" in apply_steps and "terraform apply -input=false tfplan" in apply_steps
    assert "upload-artifact" not in text  # plan files can contain secrets
    for name, job in jobs.items():
        # The plan runs BEFORE any approval so the approver can read it.
        assert ("environment" in job) == (name not in ("tests", "plan")), name
        if "environment" in job:
            assert job["environment"] == "production"
    # Only the release job may write to the repo, and only it keeps git credentials.
    for name, job in jobs.items():
        perms = job.get("permissions", {"contents": "read"})
        assert perms.get("contents", "read") == ("write" if name == "release" else "read"), name
        for step in job["steps"]:
            if str(step.get("uses", "")).startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is (name == "release"), name
    for job in jobs.values():
        for step in job["steps"]:
            if "uses" in step:
                assert PINNED.match(step["uses"]), f"unpinned action: {step['uses']}"
    # Plan job: read-only role. Everything that changes infrastructure: deploy role, in the env.
    assert "vars.AWS_PLAN_ROLE_ARN" in str(jobs["plan"]["steps"])
    for name in ("infrastructure", "platform", "deploy"):
        assert "vars.AWS_DEPLOY_ROLE_ARN" in str(jobs[name]["steps"]), name
    assert "secrets." not in text  # no secrets at all: OIDC + variables
    assert "aws-access-key-id" not in text and "AWS_SECRET_ACCESS_KEY" not in text
    assert 'exit-code: "1"' in text and "CRITICAL,HIGH" in text
    assert "shop-api" in text  # app name defaulted from the project folder


def test_workflow_delivery_mode(tmp_path: Path) -> None:
    argo = collect("argocd", tmp_path)[WORKFLOW]
    kube = collect("kubectl", tmp_path)[WORKFLOW]
    assert "[skip ci]" in argo and "jsonpath='{.status.health.status}'=Healthy" in argo
    # Must wait for the NEW revision; Synced alone passes instantly on the old one.
    assert "--for=jsonpath='{.status.sync.revision}'=\"$REVISION\"" in argo
    jobs = yaml.safe_load(argo)["jobs"]
    assert jobs["verify"]["needs"] == "release" and jobs["release"]["needs"] == "deploy"
    assert "uses" not in str(jobs["release"]["steps"][1])  # release runs no third-party action
    assert "kubectl rollout status" in kube and "argocd" not in kube.lower()
    deploy = yaml.safe_load(kube)["jobs"]["deploy"]
    assert deploy["permissions"]["contents"] == "read"


def test_infra_templates_have_no_project_specifics() -> None:
    paths = [
        *ROOT.glob("agents/infra/*.tmpl"),
        *ROOT.glob("agents/partials/*.tmpl"),
        *ROOT.glob("skills/infra/*/*.tmpl"),
        *ROOT.glob("templates/workflows/*.tmpl"),
    ]
    assert len(paths) >= 15
    for p in paths:
        hits = PROJECT_SPECIFIC.findall(p.read_text())
        assert not hits, f"{p.relative_to(ROOT)}: {hits}"


def test_infra_skills_render(tmp_path: Path) -> None:
    files = collect("argocd", tmp_path)
    for skill in ("infra-factory", "infra-change-review", "deploy-checklist"):
        text = files[f".claude/skills/{skill}/SKILL.md"]
        assert yaml.safe_load(text.split("---\n", 2)[1])["name"] == skill
    checklist = files[".claude/skills/deploy-checklist/SKILL.md"]
    assert "`demo`" in checklist and "<REGISTRY>/<IMAGE>" in checklist
