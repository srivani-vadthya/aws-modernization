from pathlib import Path

from app.generated_dotnet import get_backend_template_dir, get_frontend_template_dir, write_dotnet_generated, write_frontend_generated
from app.github_deployer import build_feature_branch_name


def test_generated_dotnet_always_writes_to_backend_and_frontend_templates(tmp_path):
    output_dir = tmp_path / "generated-dotnet"
    write_dotnet_generated(output_dir)
    write_frontend_generated()

    backend = get_backend_template_dir()
    frontend = get_frontend_template_dir()
    assert backend.exists()
    assert frontend.exists()
    assert (backend / "Program.cs").exists()
    assert (frontend / "package.json").exists()
    assert (frontend / "src" / "App.tsx").exists()
    assert (output_dir / "Program.cs").exists()


def test_feature_branch_name_is_never_main_or_master():
    branch = build_feature_branch_name("US-204")
    assert branch.startswith("feature/Userstory")
    assert branch.lower() not in {"main", "master"}
    assert "US204" in branch or "US-204" in branch
