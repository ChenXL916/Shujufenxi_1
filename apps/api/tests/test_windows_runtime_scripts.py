from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WINDOWS_INFRA = ROOT / "infra" / "windows"
SERVICE_SCRIPT = ROOT / "scripts" / "realtime_sync_service.py"


def test_realtime_sync_task_uses_local_env_and_singleton_guard() -> None:
    runner = (WINDOWS_INFRA / "run-realtime-sync.ps1").read_text(encoding="utf-8")
    register = (WINDOWS_INFRA / "register-realtime-sync-task.ps1").read_text(encoding="utf-8")
    service = SERVICE_SCRIPT.read_text(encoding="utf-8")

    assert "scripts\\realtime_sync_service.py" in runner
    assert ".env.tunnel" in service
    assert "realtime-sync-service.lock" in service
    assert "msvcrt.locking" in service
    assert "from realtime_sync import run_forever" in service
    assert "-Execute $python" in register
    assert "-WorkingDirectory $root" in register
    assert "-AtLogOn" in register
    assert "-MultipleInstances IgnoreNew" in register
    assert "-RestartCount 99" in register
    assert "-RestartInterval (New-TimeSpan -Minutes 1)" in register


def test_realtime_sync_task_has_reversible_unregister_script() -> None:
    unregister = (WINDOWS_INFRA / "unregister-realtime-sync-task.ps1").read_text(encoding="utf-8")

    assert "Stop-ScheduledTask" in unregister
    assert "Unregister-ScheduledTask" in unregister
    assert "-Confirm:$false" in unregister
    assert "Get-CimInstance Win32_Process" in unregister
    assert "Stop-Process" in unregister


def test_windows_runtime_scripts_do_not_embed_feishu_credentials() -> None:
    paths = [*WINDOWS_INFRA.glob("*.ps1"), SERVICE_SCRIPT]
    content = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "FEISHU_APP_ID" not in content
    assert "FEISHU_APP_SECRET" not in content
    assert "FEISHU_BOT_WEBHOOK" not in content
    assert "cli_" not in content
