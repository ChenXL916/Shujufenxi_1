export interface PermissionUser {
  id: string
  username: string | null
  name: string
  email: string | null
  role_codes: string[]
  role_level: number
  status: string
  active: boolean
  room_scope_mode: 'role' | 'custom'
  room_ids: string[] | null
  room_names: string[]
  scope_label: string
  feishu_bound: boolean
  password_login_enabled: boolean
  last_login_at: string | null
  can_edit_access: boolean
  can_edit_credentials: boolean
  can_delete: boolean
}

export interface PermissionRole {
  id: string
  role_code: string
  role_name: string
  description: string | null
  level: number
  level_label: string
  all_permissions: boolean
  system_role: boolean
  active: boolean
  permission_codes: string[]
  allowed_permission_codes: string[]
  room_ids: string[]
  room_names: string[]
  assignable: boolean
  editable: boolean
}

export interface PermissionDefinition {
  id: string
  code: string
  name: string
  description: string
}

export interface RoomResource {
  id: string
  room_id: string
  room_name: string
  product_category: string
  permission_group: string
  enabled: boolean
}

export interface FeishuPermissionGroup {
  id: string
  name: string
  chat_id: string
  enabled: boolean
  room_ids: string[]
  room_names: string[]
}

export interface PermissionOverview {
  current_actor: string | null
  current_actor_role_codes: string[]
  current_actor_level: number
  users: PermissionUser[]
  roles: PermissionRole[]
  permissions: PermissionDefinition[]
  room_resources: RoomResource[]
  feishu_groups: FeishuPermissionGroup[]
}

export interface PermissionUserInput {
  username?: string
  name?: string
  email?: string
  password?: string
  role_codes: string[]
  room_ids: string[] | null
  active: boolean
}

export interface PermissionUserCredentialsInput {
  username: string
  password?: string
}

export interface PermissionRoleInput {
  role_name?: string
  description?: string
  permission_codes: string[]
  room_ids: string[]
  active: boolean
}

export interface RoomResourceInput {
  product_category: string
  permission_group: string
  enabled: boolean
}

export interface FeishuPermissionGroupInput {
  name: string
  chat_id?: string
  room_ids: string[]
  enabled: boolean
}
