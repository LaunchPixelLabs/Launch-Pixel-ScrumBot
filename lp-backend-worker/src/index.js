import { Client } from '@neondatabase/serverless';

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    
    // Quick routing for verification and health checks
    if (request.method === "GET" && url.pathname === "/") {
      return new Response("🚀 Launch Pixel Cloudflare Edge API Online", { status: 200 });
    }

    // Initialize Neon database client
    const client = new Client(env.DATABASE_URL);
    await client.connect();

    try {
      // 1. WhatsApp GET Webhook Verification
      if (request.method === "GET" && url.pathname === "/webhook") {
        const mode = url.searchParams.get("hub.mode");
        const token = url.searchParams.get("hub.verify_token");
        const challenge = url.searchParams.get("hub.challenge");

        if (mode && token) {
          if (mode === "subscribe" && token === env.WHATSAPP_VERIFY_TOKEN) {
            console.log("🟢 WhatsApp Webhook verification successful.");
            return new Response(challenge, { status: 200 });
          }
          return new Response("Forbidden: Verification Token Mismatch", { status: 403 });
        }
        return new Response("Bad Request: Missing hub parameters", { status: 400 });
      }

      // 2. WhatsApp POST Webhook Message Reception
      if (request.method === "POST" && url.pathname === "/webhook") {
        const data = await request.json();
        console.log("📨 Received WhatsApp Webhook payload:", JSON.stringify(data));

        if (data.object === "whatsapp_business_account") {
          for (const entry of data.entry || []) {
            for (const change of entry.changes || []) {
              const value = change.value || {};
              const messages = value.messages || [];
              const contacts = value.contacts || [];

              if (messages.length > 0) {
                const msg = messages[0];
                const sender_phone = msg.from || "Unknown";
                const msg_type = msg.type || "text";
                
                let sender_name = sender_phone;
                if (contacts.length > 0) {
                  sender_name = contacts[0].profile?.name || sender_phone;
                }

                let body = "";
                if (msg_type === "text") {
                  body = msg.text?.body || "";
                } else if (msg_type === "button") {
                  body = msg.button?.text || "[Button Click]";
                } else {
                  body = `[${msg_type.toUpperCase()} Media Message]`;
                }

                console.log(`💬 Message from ${sender_name} (${sender_phone}): ${body}`);

                // Direct routing to Discord via Webhook to bypass intermediate latency lag!
                if (env.DISCORD_WHATSAPP_WEBHOOK_URL) {
                  const discordResponse = await fetch(env.DISCORD_WHATSAPP_WEBHOOK_URL, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      embeds: [{
                        title: "💬 WhatsApp Chat Sync (Edge)",
                        description: body,
                        color: 3066993, // Green
                        fields: [
                          { name: "From", value: sender_name, inline: true },
                          { name: "Phone", value: sender_phone, inline: true }
                        ],
                        footer: { text: "Synced via Cloudflare Workers Edge Node" }
                      }]
                    })
                  });
                  console.log("📨 Routed to Discord Webhook. Status:", discordResponse.status);
                }
              }
            }
          }
        }
        return new Response(JSON.stringify({ status: "success" }), {
          status: 200,
          headers: { "Content-Type": "application/json" }
        });
      }

      // 3. API: Fetch active tickets (GET /tickets)
      if (request.method === "GET" && url.pathname === "/tickets") {
        const { rows } = await client.query("SELECT * FROM tickets WHERE status != 'Closed' ORDER BY id ASC;");
        return new Response(JSON.stringify(rows), {
          status: 200,
          headers: { 
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*" 
          }
        });
      }

      // 4. API: Log a comment (POST /comments)
      if (request.method === "POST" && url.pathname === "/comments") {
        const { ticket_id, author_id, author_name, comment_text } = await request.json();
        await client.query(
          "INSERT INTO comments (ticket_id, author_id, author_name, comment_text) VALUES ($1, $2, $3, $4);",
          [ticket_id, author_id, author_name, comment_text]
        );
        return new Response(JSON.stringify({ status: "comment logged" }), { 
          status: 201,
          headers: { "Content-Type": "application/json" }
        });
      }

      // 5. API: Log an attachment (POST /attachments)
      if (request.method === "POST" && url.pathname === "/attachments") {
        const { ticket_id, file_name, file_url } = await request.json();
        await client.query(
          "INSERT INTO attachments (ticket_id, file_name, file_url) VALUES ($1, $2, $3);",
          [ticket_id, file_name, file_url]
        );
        return new Response(JSON.stringify({ status: "attachment logged" }), { 
          status: 201,
          headers: { "Content-Type": "application/json" }
        });
      }

      return new Response("Not Found", { status: 404 });
    } catch (err) {
      console.error("❌ Worker execution failed:", err);
      return new Response(JSON.stringify({ error: err.message }), {
        status: 500,
        headers: { "Content-Type": "application/json" }
      });
    } finally {
      // Clean up database connection
      ctx.waitUntil(client.end());
    }
  }
};
