import Link from "next/link";

export default function SitesFallback() {
  return (
    <main className="fallback-shell">
      <section className="fallback-card" role="status">
        <span className="fallback-mark">数</span>
        <p className="fallback-kicker">LIVE OPS</p>
        <h1>直播运营驾驶舱正在连接</h1>
        <p>
          Sites
          尚未读取到前端生产资源。请稍后重新加载；系统不会在此状态下显示旧数据或模拟数据。
        </p>
        <Link href="/">重新加载</Link>
      </section>
    </main>
  );
}
