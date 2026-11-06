import { MobileNav, Sidebar } from "@/components/sidebar";
import { MetaProvider } from "@/components/meta-provider";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <MetaProvider>
      <div className="flex min-h-screen">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <MobileNav />
          <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 md:px-8">{children}</main>
        </div>
      </div>
    </MetaProvider>
  );
}
