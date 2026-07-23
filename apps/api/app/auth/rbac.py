from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDefinition:
    code: str
    name: str
    description: str


@dataclass(frozen=True)
class RoleDefinition:
    code: str
    name: str
    description: str
    permissions: frozenset[str]
    room_groups: frozenset[str]
    all_permissions: bool = False


PERMISSION_DEFINITIONS = (
    PermissionDefinition("dashboard.view", "查看经营数据", "查看总览、图表、比较、人员与详情"),
    PermissionDefinition("dashboard.export", "导出经营数据", "按服务端数据范围导出 CSV/Excel"),
    PermissionDefinition("alert.view", "查看预警", "查看范围内普通预警与主播趋势预警"),
    PermissionDefinition("alert.manage", "处置预警", "评估、确认、重推与测试预警"),
    PermissionDefinition("user.manage", "用户管理", "创建、停用和配置用户角色"),
    PermissionDefinition("role.manage", "角色管理", "配置角色权限点"),
    PermissionDefinition("permission.manage", "权限管理", "查看和修改权限矩阵"),
    PermissionDefinition("room_scope.manage", "直播间权限管理", "配置直播间资源和数据范围"),
    PermissionDefinition("roi_target.manage", "ROI目标管理", "配置直播间 ROI 目标"),
    PermissionDefinition("alert_rule.manage", "预警规则管理", "配置普通及主播趋势预警规则"),
    PermissionDefinition("feishu.manage", "飞书配置管理", "配置飞书授权、机器人和群范围"),
    PermissionDefinition("data_source.manage", "数据源管理", "查看、扫描和同步数据源"),
    PermissionDefinition("sync.run", "执行数据同步", "手动触发飞书数据同步"),
    PermissionDefinition("system.manage", "系统设置管理", "修改系统运行设置和 Secret"),
    PermissionDefinition("audit.view", "查看审计日志", "查看通用及权限审计日志"),
    PermissionDefinition("database.manage", "数据库管理", "访问已有数据库管理入口"),
)

BUSINESS_VIEW_PERMISSIONS = frozenset({"dashboard.view", "dashboard.export", "alert.view"})
ALL_PERMISSION_CODES = frozenset(item.code for item in PERMISSION_DEFINITIONS)
ALL_BUSINESS_ROOM_GROUPS = frozenset({"water_pm", "primer_pm", "powder_pm"})

# Role rank is a server-side security boundary, not just a display order.
# Lower-ranked accounts can never create, edit, disable or delete an account at
# their own rank or above. The developer rank is reserved for the system owner.
ROLE_LEVELS = {
    "developer": 500,
    "admin": 400,
    "operations_lead": 300,
    "live_manager": 200,
    "water_pm": 100,
    "primer_pm": 100,
    "powder_pm": 100,
    "viewer": 50,
}

ROLE_LEVEL_LABELS = {
    500: "L5 · 开发者",
    400: "L4 · 管理员",
    300: "L3 · 运营负责人",
    200: "L2 · 直播主管",
    100: "L1 · 项目 PM",
    50: "兼容只读",
}

# A role may only be configured with permissions whose minimum rank does not
# exceed the role's own rank. This prevents an administrator from turning a
# lower-ranked role into a hidden administrator.
MINIMUM_ROLE_LEVEL_BY_PERMISSION = {
    "dashboard.view": 50,
    "dashboard.export": 50,
    "alert.view": 50,
    "alert.manage": 200,
    "roi_target.manage": 300,
    "alert_rule.manage": 300,
    "data_source.manage": 300,
    "sync.run": 300,
    "audit.view": 300,
    "user.manage": 400,
    "role.manage": 400,
    "permission.manage": 400,
    "room_scope.manage": 400,
    "feishu.manage": 400,
    "system.manage": 400,
    "database.manage": 500,
}

ADMIN_PERMISSIONS = ALL_PERMISSION_CODES - frozenset({"database.manage"})
OPERATIONS_LEAD_PERMISSIONS = BUSINESS_VIEW_PERMISSIONS | frozenset(
    {
        "alert.manage",
        "roi_target.manage",
        "alert_rule.manage",
        "data_source.manage",
        "sync.run",
        "audit.view",
    }
)
LIVE_MANAGER_PERMISSIONS = BUSINESS_VIEW_PERMISSIONS | frozenset({"alert.manage"})

ROLE_DEFINITIONS = (
    RoleDefinition(
        "developer",
        "开发者（最高权限）",
        "系统所有者，拥有全部数据、数据库、用户、权限和配置能力",
        ALL_PERMISSION_CODES,
        frozenset(),
        all_permissions=True,
    ),
    RoleDefinition(
        "admin",
        "管理员",
        "管理全部直播间、用户、权限和系统配置，但不能管理开发者或数据库入口",
        ADMIN_PERMISSIONS,
        ALL_BUSINESS_ROOM_GROUPS,
    ),
    RoleDefinition(
        "operations_lead",
        "运营负责人",
        "介于管理员和直播主管之间，负责全部直播间经营、同步、规则、目标和审计",
        OPERATIONS_LEAD_PERMISSIONS,
        ALL_BUSINESS_ROOM_GROUPS,
    ),
    RoleDefinition(
        "live_manager",
        "直播主管",
        "查看全部直播间经营数据并处置预警，不可修改系统、用户和规则配置",
        LIVE_MANAGER_PERMISSIONS,
        ALL_BUSINESS_ROOM_GROUPS,
    ),
    RoleDefinition(
        "water_pm",
        "水散粉PM",
        "仅查看水散粉直播间数据",
        BUSINESS_VIEW_PERMISSIONS,
        frozenset({"water_pm"}),
    ),
    RoleDefinition(
        "primer_pm",
        "妆前乳PM",
        "仅查看妆前乳直播间数据",
        BUSINESS_VIEW_PERMISSIONS,
        frozenset({"primer_pm"}),
    ),
    RoleDefinition(
        "powder_pm",
        "散粉PM",
        "仅查看散粉直播间数据",
        BUSINESS_VIEW_PERMISSIONS,
        frozenset({"powder_pm"}),
    ),
    RoleDefinition(
        "viewer",
        "受限查看者",
        "兼容既有按用户直播间授权的只读账号",
        BUSINESS_VIEW_PERMISSIONS,
        frozenset(),
    ),
)

ROLE_BY_CODE = {item.code: item for item in ROLE_DEFINITIONS}
LEGACY_ROLE_MAP = {"admin": "admin", "operator": "live_manager", "viewer": "viewer"}

# Automatic Feishu account creation must stay below elevated operational and
# administrative ranks. Administrators can promote a user explicitly later.
AUTO_PROVISION_ROLE_CODES = frozenset(
    {"live_manager", "water_pm", "primer_pm", "powder_pm", "viewer"}
)


def role_level(role_code: str) -> int:
    return ROLE_LEVELS.get(role_code, 0)


def role_level_label(role_code: str) -> str:
    return ROLE_LEVEL_LABELS.get(role_level(role_code), "未分级")


def allowed_permission_codes(role_code: str) -> frozenset[str]:
    level = role_level(role_code)
    return frozenset(
        permission_code
        for permission_code, minimum_level in MINIMUM_ROLE_LEVEL_BY_PERMISSION.items()
        if level >= minimum_level
    )


# Exact configuration only. This is deliberately not fuzzy matching. The currently
# running database uses a space in the Mistine room name, while older fixtures used
# a hyphen; both exact names map to the same formal permission group.
INITIAL_ROOM_RESOURCE_CONFIG = {
    "Mistine 水散粉": ("water_powder", "water_pm"),
    "Mistine-水散粉": ("water_powder", "water_pm"),
    "柏瑞美-妆前乳": ("primer", "primer_pm"),
    "柏瑞美-散粉": ("powder", "powder_pm"),
}

TEST_ACCOUNT_DEFINITIONS = (
    ("developer_test", "开发者测试账号", "developer"),
    ("live_manager_test", "直播主管测试账号", "live_manager"),
    ("water_pm_test", "水散粉PM测试账号", "water_pm"),
    ("primer_pm_test", "妆前乳PM测试账号", "primer_pm"),
    ("powder_pm_test", "散粉PM测试账号", "powder_pm"),
)
