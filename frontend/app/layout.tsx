import "./globals.css";
import Link from "next/link";

export const metadata = { title: "Paper-Trading Exchange", description: "CS F212 Database Systems, Group 9" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="topbar">
          <strong>Paper-Trading Exchange</strong>
          <nav>
            <Link href="/">Trade</Link>
            <Link href="/integrity">Database health</Link>
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
