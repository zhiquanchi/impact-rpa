# Impact Flow Analysis with go-mitmproxy

This document maps the current UI-RPA flow to a direct HTTP flow.

## 1) Current UI flow in this repo

From `ProposalSender._handle_proposal_modal()` in `legacy_main.py`, the business sequence is:

1. Open `Send Proposal` modal.
2. Select `Template Term`.
3. (Optional) Select category/tag by selected tab.
4. Select tomorrow's date.
5. Fill comment.
6. Submit and optionally confirm `"I understand"`.

For Creator Search mode (`send_proposals_creator_search`), there is one extra step:

1. Click target row in Creator Search list.
2. Open the creator side panel and click `Send Proposal`.
3. Execute the same modal flow above.

## 2) Capture the real HTTP chain

Use go-mitmproxy to capture one successful proposal send.

1. Start proxy:
   - `go-mitmproxy` (default proxy `:9080`, web UI `:9081`)
2. Configure browser proxy to `127.0.0.1:9080`.
3. Trust generated CA cert (for HTTPS decrypt).
4. In Impact UI, manually send one proposal successfully.
5. In go-mitmproxy web UI (`http://localhost:9081`), locate requests around that action:
   - creator search/list request
   - creator context/detail request (if any)
   - template/dropdown metadata request (if any)
   - final send proposal request
6. Copy each request's:
   - method + URL
   - headers (Cookie, CSRF, Origin, Referer, User-Agent)
   - JSON body

## 3) Replay by HTTP script

1. Copy `config/http_flow.example.json` to `config/http_flow.json`.
2. Replace placeholder endpoints and fields with captured real values.
3. Run:
   - `python scripts/send_proposals_via_http.py --config config/http_flow.json --max-count 10`

## 4) Mapping tips

- Keep `Cookie`, `X-CSRF-Token`, `Origin`, `Referer` aligned with captured traffic.
- If server rejects with 401/403, usually session token or CSRF mismatch.
- If server validates specific payload schema, replay exact key names/types from capture.
- The script supports placeholders like `{{psi}}`, `{{creator_name}}`, `{{tomorrow}}`.
- If discovery API is unstable, directly provide `creators` list in config.
