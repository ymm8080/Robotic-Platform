new_block = '''  zewm_robco:
    enabled: false  # set to true when ABAP side is installed and tested
    base_url: 'https://sap-host.example.com:443'
    client: '100'
    odata_service: '/sap/opu/odata/sap/ZEWM_ROBCO_SRV'
    auth_mode: 'basic'       # basic | oauth2
    user: 'ROBCO_USER'
    password_file: '/run/secrets/sap_password'
    # Per-service rate limit (requests/min). Independent of global
    # sap.rate_limit_per_minute above; allows finer control for this
    # custom OData service if it has different throughput constraints.
    rate_limit: 80
    connection_timeout: 30   # seconds (httpx connect/read timeout)
    # -- Two-step confirmation retry --
    confirm_retry_max: 5            # max retries for step-2 confirmation
    confirm_retry_backoff_base: 1   # seconds (exponential: 1, 2, 4, 8, 16)
    confirm_retry_backoff_cap: 30   # seconds cap on backoff
    # -- OAuth2 mode (uncomment for S/4HANA) --
    # NOTE: Uncomment BOTH the auth_mode line below AND the oauth2 block
    # below it. Also comment out the basic auth_mode line above.
    # auth_mode: oauth2
    # oauth2:
    #   token_url: 'https://sap-s4hana:44300/sap/bc/sec/oauth2/token'
    #   client_id: 'ZEWM_ROBCO_CLIENT'
    #   client_secret_file: '/run/secrets/sap_oauth_client_secret'
    #   scope: 'ZEWM_ROBCO_SRV_0001'
'''
with open('sap-bridge/config.yaml', 'r') as f:
    lines = list(f)
h = next(i for i, l in enumerate(lines) if 'zwem_robco:' in l)
print(f'Start {h}')
t = len(lines)
for i in range(h+1, len(lines)):
    if lines[i].strip() != '' and not (lines[i].strip().startswith('#') or lines[i].startswith('    ')):
        t = i
        break
print(f'End {t}')
with open('sap-bridge/config.yaml', 'w') as f:
    f.writelines(lines[:h])
    f.write(new_block)
    f.writelines(lines[t:])
print('Written')
import pathlib as p
s=p.Path('sap-bridge/config.yaml').read_text();print('1:', 'Per-service rate limit' in s);print('2:', 'redis_url' not in s);print('3:', 'Uncomment BOTH' in s)
