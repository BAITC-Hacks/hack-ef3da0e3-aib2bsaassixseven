import Link from "next/link";

const navigation = [
  { href: "/dashboard", label: "Обзор" },
  { href: "/meetings", label: "Совещания" },
  { href: "/tasks", label: "Поручения" },
  { href: "/settings", label: "Настройки" },
] as const;

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen md:grid md:grid-cols-[248px_1fr]">
      <aside className="border-b border-[var(--border)] bg-[var(--surface)] px-5 py-5 md:min-h-screen md:border-r md:border-b-0">
        <Link className="text-base font-semibold" href="/dashboard">
          Meeting Protocol
        </Link>
        <nav aria-label="Основная навигация" className="mt-8">
          <ul className="grid gap-1">
            {navigation.map((item) => (
              <li key={item.href}>
                <Link
                  className="block rounded-md px-3 py-2 text-sm text-[var(--text-muted)] transition-colors hover:bg-[var(--surface-muted)] hover:text-[var(--text)]"
                  href={item.href}
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </aside>
      <main className="min-w-0 px-5 py-8 md:px-8 lg:px-10">{children}</main>
    </div>
  );
}
