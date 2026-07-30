import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "多直播间小时数据驾驶舱",
  description: "直播运营数据、主播分析、预警和权限管理工作台。",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
