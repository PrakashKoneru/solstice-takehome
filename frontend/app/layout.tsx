import type { Metadata } from 'next'
import { Geist } from 'next/font/google'
import './globals.css'
import Navbar from '@/components/Navbar'

const geist = Geist({ subsets: ['latin'], variable: '--font-geist' })

export const metadata: Metadata = {
  title: 'ContentStudio — Pharma Content Platform',
  description: 'AI-assisted pharma content creation that stays within approved claims.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${geist.variable} h-full`}>
      <body className="h-full flex flex-col bg-slate-50 font-sans antialiased">
        <Navbar />
        {children}
      </body>
    </html>
  )
}
