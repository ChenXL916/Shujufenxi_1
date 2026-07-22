import { LockOutlined, SafetyCertificateOutlined, UserOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import { Alert, Button, Card, Divider, Form, Input, Space, Typography } from 'antd'
import axios from 'axios'
import { loginWithPassword } from '@/api/client'

type LoginFormValues = {
  username: string
  password: string
}

function loginErrorMessage(error: unknown): string {
  if (axios.isAxiosError<unknown>(error)) {
    const data = error.response?.data
    if (data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string') {
      return data.detail
    }
  }
  return '登录失败，请检查网络后重试'
}

export function LoginScreen({ onAuthenticated }: { onAuthenticated: () => Promise<void> }) {
  const login = useMutation({
    mutationFn: loginWithPassword,
    onSuccess: onAuthenticated,
  })
  return (
    <main className="login-screen">
      <Card className="login-card">
        <Space orientation="vertical" size={20} className="login-stack">
          <div className="login-heading">
            <span className="login-brand-mark" aria-hidden="true">
              <SafetyCertificateOutlined />
            </span>
            <div>
              <Typography.Title level={2}>直播运营驾驶舱</Typography.Title>
              <Typography.Text type="secondary">使用管理员分配的网页账号登录</Typography.Text>
            </div>
          </div>
          {login.isError ? (
            <Alert showIcon type="error" message={loginErrorMessage(login.error)} />
          ) : null}
          <Form<LoginFormValues>
            layout="vertical"
            requiredMark={false}
            onFinish={(values) => login.mutate(values)}
          >
            <Form.Item
              name="username"
              label="登录名"
              rules={[{ required: true, message: '请输入登录名' }]}
            >
              <Input
                autoFocus
                autoComplete="username"
                prefix={<UserOutlined />}
                placeholder="请输入管理员创建的登录名"
                size="large"
              />
            </Form.Item>
            <Form.Item
              name="password"
              label="密码"
              rules={[
                { required: true, message: '请输入密码' },
                { min: 10, message: '密码至少 10 位' },
              ]}
            >
              <Input.Password
                autoComplete="current-password"
                prefix={<LockOutlined />}
                placeholder="请输入密码"
                size="large"
              />
            </Form.Item>
            <Button block type="primary" htmlType="submit" size="large" loading={login.isPending}>
              登录并查看数据
            </Button>
          </Form>
          <Divider plain>管理员与已有飞书账号</Divider>
          <Button block onClick={() => window.location.assign('/auth/feishu/login')}>
            使用飞书登录
          </Button>
          <Typography.Paragraph type="secondary" className="login-help">
            登录后只能看到管理员分配给你的功能和直播间；没有账号请联系系统管理员创建。
          </Typography.Paragraph>
        </Space>
      </Card>
    </main>
  )
}
