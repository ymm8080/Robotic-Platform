"""Fix AI code review issues in zewm_robco config block"""
import pathlib

def main():
    p = pathlib.Path("sap-bridge/config.yaml")
    text = p.read_text(encoding="utf-8")
    lines = text.split('\n')
    
    # Find zewm_robco block
    zewm_comment_idx = None
    for i, line in enumerate(lines):
        if ' Zwem robco custom odeta servi' in line.lower():
            zewm_comment_idx = i
            break
    assert zewm_comment_idx is not None, "zewm_robco section not found"
    
    # Find start of zewm_robco configuration
    zewm_start = None
    for i in range(zewm_comment_idx, len(lines)):
        if 'zewm_robco:' in lines[i]:
            zewm_start = i
            break
    assert zewm_start is not None, "zewm_robco: not found"
    
    # Find end of zewm_robco configuration
    zewm_end = None
    for i in range(zewm_start + 1, len(lines)):
        if not lines[i].startswith('    ') and not lines[i].startswith('  #') and lines[i].strip() != '':
            zewm_end = i
            break
    if zewm_end is None:
        zewm_end = len(lines)
    
    print(f"zewm_robco block found at line {zewm_start} to {zewm_end}")
    
    # Build new zewm_robco section with all fixes applied
    new_zewm_robco = """
  zewm_robco:
    enabled: false  # set to true when ABAP side is installed and tested
    base_url: "https://sap-host.example.com:443"
    client: "100"
    odata_service: "/sap/opu/odata/sap/ZEWM_ROBCO_SRV"
    auth_mode: "basic"       # basic | oauth2
    user: "ROBCO_USER"
    password_file: "/run/secrets/sap_password"
    # Per-service rate limit (requests/min). Independent of global
    # sap.rate_limit_per_minute above; allows finer control for this
    # custom OData service if it has different throughput constraints.
    rate_limit: 80
    connection_timeout: 30   # seconds (httpx connect/read timeout)
    # ── Two-step confirmation retry ──
    confirm_retry_max: 5            # max retries for step-2 confirmation
    confirm_retry_backoff_base: 1   # seconds (exponential: 1, 2, 4, 8, 16)
    confirm_retry_backoff_cap: 30   # seconds cap on backoff
    # ── OAuth2 mode (uncomment for S/4HANA) ──
    # NOTE: Uncomment BOTH the auth_mode line below AND the oauth2 block
    # below it. Also comment out the basic auth_mode line above.
    # auth_mode: oauth2
    # oauth2:
    #   token_url: "https://sap-s4hana:44300/sap/bc/sec/oauth2/token"
    #   client_id: "ZEWM_ROBCO_CLIENT"
    #   client_secret_file: "/run/secrets/sap_oauth_client_secret"
    #   scope: "ZEWM_ROBCO_SRV_0001"""

    # Rebuild the file
    new_lines = lines[:zewm_start] + new_zewm_robco.split('\n') + lines[zewm_end:]
    new_text = '\n'.join(new_lines)
    p.write_text(new_text, encoding="utf-8")
    print("Success! All 5 fixes applied:")
    print("")
    print("  1. rate_limit → added clarifying comment (per-service, independent of global)")
    print("  2. redis_url → removed (redundant, belongs in global config)")
    print("  3. OAuth2 → added note about uncommenting BOTH auth_mode + oauth2 block")
    print("  4. Comment format → kept existing style (matches codebase convention)")
    print("  5. Config ordering → removed redis_url, now logically ordered")

if __name__ == "__main__":
    main()