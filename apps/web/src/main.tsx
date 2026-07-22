import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter } from 'react-router-dom'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import { dashboardTheme } from './theme/dashboardTheme'
import './styles/global.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      placeholderData: (previousData: unknown) => previousData,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider locale={zhCN} theme={dashboardTheme}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  </StrictMode>,
)
