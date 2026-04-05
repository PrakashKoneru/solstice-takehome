import Link from 'next/link'

const cards = [
  {
    href: '/design-system',
    title: 'Design System',
    description: 'Upload brand style guides. The AI extracts design tokens — colors, fonts, spacing — to apply to all generated content.',
    icon: (
      <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 5a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1V5zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1V5zM4 15a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1H5a1 1 0 01-1-1v-4zm10 0a1 1 0 011-1h4a1 1 0 011 1v4a1 1 0 01-1 1h-4a1 1 0 01-1-1v-4z" />
      </svg>
    ),
  },
  {
    href: '/knowledge-base',
    title: 'Knowledge Base',
    description: 'Upload approved clinical documents — claims, research papers, prescribing info. These become the only source of truth for content generation.',
    icon: (
      <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    href: '/create',
    title: 'Create Content',
    description: 'Select your knowledge sources, chat with the AI, and generate compliant marketing content. Edit and iterate until it is ready.',
    icon: (
      <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
      </svg>
    ),
  },
]

export default function Home() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[calc(100vh-8rem)]">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-slate-900 tracking-tight sm:text-5xl">
          Pharma Content, <span className="text-indigo-600">Compliant by Design</span>
        </h1>
        <p className="mt-4 text-lg text-slate-500 max-w-xl mx-auto">
          AI-assisted content creation that stays within approved claims — every time.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 w-full max-w-5xl">
        {cards.map((card) => (
          <Link
            key={card.href}
            href={card.href}
            className="group relative flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm hover:shadow-md hover:border-indigo-200 transition-all"
          >
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600 group-hover:bg-indigo-100 transition-colors">
              {card.icon}
            </div>
            <div>
              <h2 className="text-base font-semibold text-slate-900">{card.title}</h2>
              <p className="mt-1 text-sm text-slate-500 leading-relaxed">{card.description}</p>
            </div>
            <div className="mt-auto flex items-center text-sm font-medium text-indigo-600 group-hover:gap-2 gap-1 transition-all">
              Get started
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
