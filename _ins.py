#!/usr/bin/python
txt = open('sap-bridge/config.yaml', encoding='utf-8').read()
idx = txt.find('  default_warehouse: "WM01"')
print('Found at', idx)
m = '''  # -- ZEWM ROBCO Custom OData Service --
  # Robot-specific warehouse order operations (assignment, confirmation, status management)
  zewm_robco:
    enabled: false
    base_url: "https://sap-host.example.com:443"
    client: "100"
    odata_service: "/sap/opu/odata/sap/ZEWM_ROBCO_SRV"
    auth_mode: "basic"
    user: "ROBCO_USER"
    password_file: "/run/secrets/sap_password"
    # Per-service rate limit (requests/min). Independent of global sap.rate_limit_per_minute
    rate_limit: 80
    connection_timeout: 30
    # -- Two-step confirmation retry --
    confirm_retry_max: 5
    confirm_retry_backoff_base: 1
    confirm_retry_backoff_cap: 30
    # -- OAuth2 mode (uncomment for S/4HANA) --
    # NOTE: Uncomment BOTH the auth_mode line below AND the oauth2 block
    # below it. Also comment out the basic auth_mode line above.
    # auth_mode: oauth2
    # oauth2:
    #   token_url: "https://sap-s4hana:44300/sap/bc/sec/oauth2/token"
    #   client_id: "ZEWM_ROBCO_CLIENT"
    #   client_secret_file: "/run/secrets/sap_oauth_client_secret"
    #   scope: "ZEWM_ROBCO_SRV_0001"

'''
with open('sap-bridge/config.yaml', 'w', encoding='utf-8') as f:
    f.write(txt[:idx] + m + txt[idx:])
print('INSERTED, verifying...')
s = open('sap-bridge/config.yaml', encoding='utf-8').read();print('1:', 'Per-service rate limit' in s);print('2:', 'redis_url' not in s);print('3:', 'Uncomment BOTH' in s)
