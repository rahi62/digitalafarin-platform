# DigitalAfarin Agency MCP

Minimal MCP connector intended to be used directly inside ChatGPT. ChatGPT is the reasoning engine; this server only exposes the DigitalAfarin specialist roster plus durable project context, decisions and tasks.

## Tools
- `agency_get_team`
- `agency_prepare_council`
- `agency_list_projects`
- `agency_get_project`
- `agency_upsert_project`
- `agency_add_note`
- `agency_record_decision`
- `agency_create_task`
- `agency_update_task`

## Local/VPS setup
```bash
cp .env.example .env
npm install
npm run check
npm run build
npm start
```
Health: `http://127.0.0.1:3050/health`
MCP: `http://127.0.0.1:3050/mcp`

## ChatGPT connection
Use the same Secure MCP Tunnel pattern as the existing DigitalAfarin WordPress connector, but point the new tunnel profile at:
`http://127.0.0.1:3050/mcp`

Suggested app name: `DigitalAfarin Agency`

Example prompts after connection:
- `@DigitalAfarin Agency تیم را نمایش بده و هیچ تغییری ایجاد نکن.`
- `@DigitalAfarin Agency پروژه‌های من را نمایش بده.`
- `@DigitalAfarin Agency برای پروژه X اتاق فکر SEO + UX + Product تشکیل بده و نتیجه را Chief of Staff جمع‌بندی کند.`
- `@DigitalAfarin Agency تصمیم نهایی این جلسه را در پروژه ثبت کن.`

## VPS deployment

Clone this repository on the VPS, then from the project root run:

```bash
sudo bash deploy/install-server.sh
```

The service binds only to `127.0.0.1:3050`. Expose it to ChatGPT only through the Secure MCP Tunnel. The installer creates `/etc/digitalafarin-agency-mcp.env` with an empty optional bearer token.

### Preferred Git deployment

```bash
sudo mkdir -p /var/www/digitalafarin-agency-mcp
sudo chown deploy:deploy /var/www/digitalafarin-agency-mcp
sudo -u deploy git clone git@github.com:rahi62/digitalafarin-agency-mcp.git /var/www/digitalafarin-agency-mcp
cd /var/www/digitalafarin-agency-mcp
sudo bash deploy/install-server.sh
```

For later updates:

```bash
cd /var/www/digitalafarin-agency-mcp
sudo -u deploy git pull --ff-only origin main
sudo bash deploy/install-server.sh
```
