// Cloudflare Pages Function — POST /api/contact
//
// Flow: verify Cloudflare Turnstile -> validate fields -> send (a) a notification
// to admin@gettessera.xyz and (b) a branded auto-reply to the submitter, both via
// Resend. Returns { ok: true } on success, 400 on bad input, 403 on failed
// Turnstile, 405 on wrong method, 502 if Resend fails.
//
// Secrets come from the Pages env binding — never hard-code them:
//   TURNSTILE_SECRET  Cloudflare Turnstile secret key
//   RESEND_API_KEY    Resend API key
//   CONTACT_TO        (optional) override notification recipient
//
// TODO: import shared templates from emails/ once that module exists
//       (e.g. `import { autoReplyHtml, notificationHtml } from "../../emails";`)
//       and drop the inline builders below.

interface Env {
  TURNSTILE_SECRET: string;
  RESEND_API_KEY: string;
  CONTACT_TO?: string;
}

// Minimal local shape for the Cloudflare Pages Functions handler signature, so
// this file type-checks without pulling in @cloudflare/workers-types. The Pages
// runtime supplies the real, richer context object at execution time.
type PagesFunction<E = unknown> = (context: {
  request: Request;
  env: E;
  next: (input?: Request | string) => Promise<Response>;
}) => Response | Promise<Response>;

// Brand / addressing constants.
const FROM = "Tessera <hello@gettessera.xyz>";
const REPLY_TO = "admin@gettessera.xyz";
const DEFAULT_TO = "admin@gettessera.xyz";

// Pigment palette (email-safe inline styles only).
const C = {
  bg: "#0a0b0d",
  panel: "#121419",
  hairline: "#262a32",
  text: "#eef0f4",
  muted: "#abb1bd",
  accent: "#2fd6a0",
  onAccent: "#04130d",
} as const;

// Schibsted Grotesk is NOT email-safe — fall back to a web-safe sans stack.
const FONT = "Helvetica,Arial,sans-serif";

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });

// Conservative RFC-5322-ish check — good enough to reject obvious garbage.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

interface ContactInput {
  name: string;
  email: string;
  message: string;
  token: string;
}

// Accept either JSON or classic form-encoded posts (no-JS fallback).
async function parseInput(request: Request): Promise<Partial<ContactInput>> {
  const ctype = request.headers.get("content-type") ?? "";
  if (ctype.includes("application/json")) {
    try {
      const body = (await request.json()) as Record<string, unknown>;
      return {
        name: typeof body.name === "string" ? body.name : undefined,
        email: typeof body.email === "string" ? body.email : undefined,
        message: typeof body.message === "string" ? body.message : undefined,
        token: typeof body["cf-turnstile-response"] === "string"
          ? (body["cf-turnstile-response"] as string)
          : typeof body.token === "string"
            ? (body.token as string)
            : undefined,
      };
    } catch {
      return {};
    }
  }
  // multipart/form-data or application/x-www-form-urlencoded
  const form = await request.formData();
  const str = (k: string): string | undefined => {
    const v = form.get(k);
    return typeof v === "string" ? v : undefined;
  };
  return {
    name: str("name"),
    email: str("email"),
    message: str("message"),
    token: str("cf-turnstile-response") ?? str("token"),
  };
}

async function verifyTurnstile(
  secret: string,
  token: string,
  ip: string | null,
): Promise<boolean> {
  const body = new FormData();
  body.append("secret", secret);
  body.append("response", token);
  if (ip) body.append("remoteip", ip);
  try {
    const res = await fetch(
      "https://challenges.cloudflare.com/turnstile/v0/siteverify",
      { method: "POST", body },
    );
    const data = (await res.json()) as { success?: boolean };
    return data.success === true;
  } catch {
    return false;
  }
}

async function sendEmail(
  apiKey: string,
  payload: Record<string, unknown>,
): Promise<boolean> {
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      authorization: `Bearer ${apiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return res.ok;
}

// --- Inline branded templates (TODO: move to emails/) -----------------------

function notificationHtml(name: string, email: string, message: string): string {
  const n = escapeHtml(name);
  const e = escapeHtml(email);
  const m = escapeHtml(message).replace(/\n/g, "<br>");
  return `<!doctype html><html><body style="margin:0;padding:0;background:${C.bg};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:${C.bg};">
    <tr><td align="center" style="padding:32px 16px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:${C.panel};border:1px solid ${C.hairline};border-radius:16px;">
        <tr><td style="padding:28px 28px 8px;font-family:${FONT};color:${C.text};font-size:18px;font-weight:bold;">New contact-form message</td></tr>
        <tr><td style="padding:0 28px 16px;font-family:${FONT};color:${C.muted};font-size:14px;line-height:1.5;">
          <strong style="color:${C.text};">From:</strong> ${n} &lt;${e}&gt;
        </td></tr>
        <tr><td style="padding:0 28px;"><hr style="border:0;border-top:1px solid ${C.hairline};margin:0;"></td></tr>
        <tr><td style="padding:16px 28px 28px;font-family:${FONT};color:${C.text};font-size:15px;line-height:1.6;">${m}</td></tr>
      </table>
    </td></tr>
  </table></body></html>`;
}

function autoReplyHtml(name: string): string {
  const n = escapeHtml(name);
  return `<!doctype html><html><body style="margin:0;padding:0;background:${C.bg};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:${C.bg};">
    <tr><td align="center" style="padding:32px 16px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:${C.panel};border:1px solid ${C.hairline};border-radius:16px;">
        <tr><td style="padding:28px 28px 0;font-family:${FONT};color:${C.accent};font-size:20px;font-weight:bold;">Tessera</td></tr>
        <tr><td style="padding:16px 28px 8px;font-family:${FONT};color:${C.text};font-size:16px;font-weight:bold;">Thanks for reaching out, ${n}.</td></tr>
        <tr><td style="padding:0 28px 20px;font-family:${FONT};color:${C.muted};font-size:15px;line-height:1.6;">
          We've received your message and will get back to you, usually within
          2&ndash;3 business days. This is an automated confirmation &mdash; no need to reply.
        </td></tr>
        <tr><td style="padding:0 28px 28px;">
          <a href="https://gettessera.xyz" style="display:inline-block;background:${C.accent};color:${C.onAccent};font-family:${FONT};font-size:14px;font-weight:bold;text-decoration:none;padding:10px 18px;border-radius:8px;">Visit gettessera.xyz</a>
        </td></tr>
        <tr><td style="padding:0 28px 24px;"><hr style="border:0;border-top:1px solid ${C.hairline};margin:0;"></td></tr>
        <tr><td style="padding:0 28px 28px;font-family:${FONT};color:${C.muted};font-size:12px;line-height:1.5;">
          Tessera &middot; private, local AI media library &middot; admin@gettessera.xyz
        </td></tr>
      </table>
    </td></tr>
  </table></body></html>`;
}

// --- Handler ----------------------------------------------------------------

// Single entry point. Reject non-POST cleanly; everything else is the contact flow.
export const onRequest: PagesFunction<Env> = async (ctx) => {
  if (ctx.request.method !== "POST") {
    return json({ ok: false, error: "method_not_allowed" }, 405);
  }
  return handlePost(ctx);
};

const handlePost: PagesFunction<Env> = async ({ request, env }) => {
  if (!env.TURNSTILE_SECRET || !env.RESEND_API_KEY) {
    return json({ ok: false, error: "server_misconfigured" }, 500);
  }

  const input = await parseInput(request);
  const name = (input.name ?? "").trim();
  const email = (input.email ?? "").trim();
  const message = (input.message ?? "").trim();
  const token = (input.token ?? "").trim();

  if (!token) {
    return json({ ok: false, error: "missing_turnstile_token" }, 403);
  }

  // Validate fields before spending a Turnstile verification round-trip on junk.
  if (
    name.length < 1 ||
    name.length > 100 ||
    !EMAIL_RE.test(email) ||
    email.length > 254 ||
    message.length < 1 ||
    message.length > 5000
  ) {
    return json({ ok: false, error: "invalid_input" }, 400);
  }

  const ip = request.headers.get("cf-connecting-ip");
  const passed = await verifyTurnstile(env.TURNSTILE_SECRET, token, ip);
  if (!passed) {
    return json({ ok: false, error: "turnstile_failed" }, 403);
  }

  const to = env.CONTACT_TO?.trim() || DEFAULT_TO;

  // Notification to the inbox — Reply-To set to the submitter so a reply
  // goes straight back to them.
  const notifyOk = await sendEmail(env.RESEND_API_KEY, {
    from: FROM,
    to: [to],
    reply_to: email,
    subject: `New contact message from ${name}`,
    html: notificationHtml(name, email, message),
  });

  // Auto-reply to the submitter.
  const replyOk = await sendEmail(env.RESEND_API_KEY, {
    from: FROM,
    to: [email],
    reply_to: REPLY_TO,
    subject: "We received your message — Tessera",
    html: autoReplyHtml(name),
  });

  if (!notifyOk) {
    return json({ ok: false, error: "send_failed" }, 502);
  }

  // Auto-reply is best-effort: if only it failed, the message still reached us.
  return json({ ok: true, autoReply: replyOk });
};
