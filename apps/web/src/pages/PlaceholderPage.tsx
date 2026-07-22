import { Card, Result } from 'antd'

export function PlaceholderPage({ title }: { title: string }) {
  return (
    <Card>
      <Result
        status="info"
        title={title}
        subTitle="该模块将在对应实施阶段接入同一筛选与权限上下文。"
      />
    </Card>
  )
}
