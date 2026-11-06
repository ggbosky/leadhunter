import { createHmac, timingSafeEqual } from "node:crypto";

export const SESSION_COOKIE = "lh_session";

/** Heslo aplikace. Pokud není nastavené, přihlášení je vypnuté (lokální provoz). */
export function appPassword(): string {
  return process.env.APP_PASSWORD || "";
}

export function sessionToken(password = appPassword()): string {
  return createHmac("sha256", password).update("leadhunter-session-v1").digest("hex");
}

export function safeEqual(a: string, b: string): boolean {
  const ba = Buffer.from(a);
  const bb = Buffer.from(b);
  return ba.length === bb.length && timingSafeEqual(ba, bb);
}

export function isAuthenticated(cookieValue: string | undefined): boolean {
  const pw = appPassword();
  if (!pw) return true;
  return !!cookieValue && safeEqual(cookieValue, sessionToken(pw));
}
