# Reference Files (05_reference)

**Purpose**: Store all third-party reference materials — SAP docs, robot specs, protocol standards, vendor manuals.

> ⚠️ **Not** for internal development docs (use `01_architecture/`) or runbooks (use `03_operations/`).

```
05_reference/
├── sap/                  # SAP EWM reference files
│   ├── odata/            # OData service definitions, metadata XML, $metadata exports
│   ├── rfc/              # RFC/BAPI function module specs, parameters
│   ├── idoc/             # IDoc types, segment definitions, sample XMLs
│   ├── ewm-api/          # SAP EWM-specific API docs (warehouse tasks, stock, etc.)
│   └── auth/             # Authentication docs (SSO, CSRF, SNC, certificates)
├── robots/               # Robot vendor reference files
│   ├── vda5050/          # VDA5050 protocol spec (official PDFs, version diffs)
│   ├── kuka/             # KUKA KMR iiwa — manuals, API refs, quirks
│   ├── mir/              # MiR250 — manuals, API refs, quirks
│   ├── otto/             # OTTO 1500 — manuals, API refs, quirks
│   └── manuals/          # Cross-brand manuals (safety, installation, maintenance)
├── protocols/            # Communication protocol specs
│   ├── mqtt/             # MQTT spec, QoS details, best practices
│   └── http/             # HTTP/REST conventions, status codes
├── external/             # External integrations
│   ├── vendor-apis/      # Third-party API docs (Feishu, WeCom, etc.)
│   └── tools/            # Tool docs (Dify, Node-RED, etc.)
├── network/              # Network topology, firewall rules, port lists
├── standards/            # Industry standards (ISO, DIN, VDI, safety regs)
└── README.md             # This file
```
