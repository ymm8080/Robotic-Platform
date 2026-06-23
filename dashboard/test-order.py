import urllib.request, json

body = json.dumps({
    "manufacturer": "Quicktron",
    "serialNumber": "QC-001",
    "orderId": "ORDER-TEST-001",
    "nodes": [{
        "nodeId": "NODE-A01", "sequenceId": 0,
        "nodePosition": {"x": 15.0, "y": 20.0, "theta": 0},
        "actions": [{"actionType": "pick", "actionId": "ACT-001", "blockingType": "SOFT"}]
    }],
    "edges": []
}).encode()

try:
    req = urllib.request.Request("http://localhost:8000/api/v1/orders", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req)
    print("OK:", resp.status, resp.read().decode())
except urllib.error.HTTPError as e:
    print("ERROR:", e.code, e.read().decode()[:500])
except Exception as e:
    print("EXCEPTION:", e)
