import type { Metadata } from "next";
import { Toaster } from "sonner";
import "./globals.css";
import { MobileNav, Sidebar } from "@/components/sidebar";
import { MetaProvider } from "@/components/meta-provider";

export const metadata: Metadata = {
  title: "Project Two · Lead Hunter",
  description: "Automatické vyhledávání a kvalifikace klientů pro Project Two",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="cs">
      <body className="antialiased">
        <MetaProvider>
          <div className="flex min-h-screen">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <MobileNav />
              <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-8">{children}</main>
            </div>
          </div>
        </MetaProvider>
        <Toaster richColors position="bottom-right" />
      </body>
    </html>
  );
}
