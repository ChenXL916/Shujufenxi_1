from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WINDOWS_INFRA = ROOT / "infra" / "windows"
SERVICE_SCRIPT = ROOT / "scripts" / "realtime_sync_service.py"
GATEWAY_SCRIPT = ROOT / "scripts" / "gateway_service.py"
LAUNCHER_INSTALLER = WINDOWS_INFRA / "install-dashboard-launcher.ps1"
LAUNCHER_UNINSTALLER = WINDOWS_INFRA / "uninstall-dashboard-launcher.ps1"


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
    paths = [*WINDOWS_INFRA.glob("*.ps1"), SERVICE_SCRIPT, GATEWAY_SCRIPT]
    content = "\n".join(path.read_text(encoding="utf-8") for path in paths)

    assert "FEISHU_APP_ID" not in content
    assert "FEISHU_APP_SECRET" not in content
    assert "FEISHU_BOT_WEBHOOK" not in content
    assert "cli_" not in content


def test_gateway_task_starts_api_tunnel_and_publishes_runtime_origin() -> None:
    register = (WINDOWS_INFRA / "register-gateway-task.ps1").read_text(encoding="utf-8")
    service = GATEWAY_SCRIPT.read_text(encoding="utf-8")

    assert "scripts\\gateway_service.py" in register
    assert "-AtLogOn" in register
    assert "-MultipleInstances IgnoreNew" in register
    assert "-RestartCount 99" in register
    assert "install-dashboard-launcher.ps1" in register
    assert "gateway-service.lock" in service
    assert 'environment["APP_ENV_FILE"] = str(ENV_FILE)' in service
    assert '[wsl, "--exec", "/bin/sleep", "infinity"]' in service
    assert '"uvicorn"' in service
    assert '"http://127.0.0.1:8000"' in service
    assert "trycloudflare" in service
    assert '"gh", "api"' not in service
    assert 'command = [gh, "api", endpoint]' in service
    assert "runtime/backend-origin.json" in service
    assert "WSL dependency keeper exited, code=" in service
    assert "gateway service restarting in 60 seconds" in service


def test_gateway_task_has_reversible_unregister_script() -> None:
    unregister = (WINDOWS_INFRA / "unregister-gateway-task.ps1").read_text(encoding="utf-8")

    assert "Stop-ScheduledTask" in unregister
    assert "Unregister-ScheduledTask" in unregister
    assert "gateway_service.py" in unregister
    assert "cloudflared.exe" in unregister
    assert "uninstall-dashboard-launcher.ps1" in unregister
    assert "Stop-Process" in unregister


def test_dashboard_launcher_uses_fixed_entry_on_desktop_and_at_logon() -> None:
    installer = LAUNCHER_INSTALLER.read_text(encoding="utf-8")
    uninstaller = LAUNCHER_UNINSTALLER.read_text(encoding="utf-8")

    assert "https://chenxl916.github.io/Shujufenxi_1/" in installer
    assert "trycloudflare.com" not in installer
    assert "[InternetShortcut]" in installer
    assert "[Environment+SpecialFolder]::Desktop" in installer
    assert "[Environment+SpecialFolder]::Startup" in installer
    assert "WriteAllLines" in installer
    assert "[Environment+SpecialFolder]::Desktop" in uninstaller
    assert "[Environment+SpecialFolder]::Startup" in uninstaller
    assert "Remove-Item" in uninstaller
