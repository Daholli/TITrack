// Ko-fi webhook receiver: records payments in kofi_donations so the app can
// show monthly progress toward the server-cost goal.
//
// Ko-fi POSTs application/x-www-form-urlencoded with a single "data" field
// holding the JSON payload, and retries until it gets a 200.
//
// Deploy with JWT verification off (Ko-fi cannot send a Supabase JWT; the
// payload's verification_token authenticates it instead):
//   supabase functions deploy kofi-webhook --no-verify-jwt
// Required secret (Ko-fi > Settings > API > Webhooks):
//   supabase secrets set KOFI_VERIFICATION_TOKEN=<token>

import { createClient } from "jsr:@supabase/supabase-js@2";

// Transaction id used by Ko-fi's sample/test webhook payloads
const KOFI_TEST_TRANSACTION_ID = "00000000-1111-2222-3333-444444444444";

Deno.serve(async (req) => {
  if (req.method !== "POST") {
    return new Response("Method not allowed", { status: 405 });
  }

  let payload: Record<string, unknown>;
  try {
    const form = await req.formData();
    payload = JSON.parse(String(form.get("data") ?? ""));
  } catch {
    return new Response("Bad request", { status: 400 });
  }

  // Trimmed: a token pasted into the secret with a stray space/newline otherwise never matches
  const expectedToken = Deno.env.get("KOFI_VERIFICATION_TOKEN")?.trim();
  const receivedToken =
    typeof payload.verification_token === "string" ? payload.verification_token.trim() : "";
  if (!expectedToken || receivedToken !== expectedToken) {
    // Lengths only (never token values), to tell a missing secret from a mismatched one
    console.warn(
      `Rejected webhook: secret ${expectedToken ? `set (${expectedToken.length} chars)` : "MISSING"}, ` +
        `payload token ${receivedToken.length} chars`,
    );
    return new Response("Unauthorized", { status: 401 });
  }

  const transactionId = payload.kofi_transaction_id;
  const amount = Number.parseFloat(String(payload.amount));
  if (typeof transactionId !== "string" || !transactionId || !Number.isFinite(amount)) {
    return new Response("Bad request", { status: 400 });
  }

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  // Only what the goal bar needs: no donor name, email, or message is stored.
  const { error } = await supabase.from("kofi_donations").upsert(
    {
      kofi_transaction_id: transactionId,
      amount,
      currency: typeof payload.currency === "string" ? payload.currency : "USD",
      payment_type: typeof payload.type === "string" ? payload.type : "Donation",
      is_subscription_payment: payload.is_subscription_payment === true,
      is_test: transactionId === KOFI_TEST_TRANSACTION_ID,
      paid_at: typeof payload.timestamp === "string" ? payload.timestamp : new Date().toISOString(),
    },
    // Ko-fi retries deliveries; a repeat of a stored transaction is a no-op
    { onConflict: "kofi_transaction_id", ignoreDuplicates: true },
  );

  if (error) {
    console.error("kofi_donations insert failed:", error);
    // Non-200 makes Ko-fi retry later
    return new Response("Storage error", { status: 500 });
  }

  return new Response("OK", { status: 200 });
});
