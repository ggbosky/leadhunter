import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const dynamic = "force-dynamic";

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string; error?: string }> }) {
  const { next, error } = await searchParams;
  return (
    <div className="grid min-h-screen place-items-center bg-sidebar px-4">
      <form method="post" action="/auth/login" className="w-full max-w-sm space-y-4 rounded-xl bg-card p-8 shadow-xl">
        <div className="flex items-center gap-2">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-primary font-bold text-primary-foreground">P2</div>
          <div>
            <p className="font-semibold leading-tight">Project Two</p>
            <p className="text-xs text-muted-foreground">Lead Hunter</p>
          </div>
        </div>
        <input type="hidden" name="next" value={next ?? "/"} />
        <div className="space-y-1">
          <label htmlFor="password" className="text-xs font-medium text-muted-foreground">Heslo</label>
          <Input id="password" name="password" type="password" autoFocus required autoComplete="current-password" />
        </div>
        {error && (
          <p className="text-sm text-red-600">{error === "limit" ? "Příliš mnoho pokusů, zkuste to za 15 minut." : "Nesprávné heslo."}</p>
        )}
        <Button type="submit" className="w-full">Přihlásit</Button>
      </form>
    </div>
  );
}
