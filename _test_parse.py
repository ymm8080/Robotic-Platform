import sys

sys.path.append("sap-bridge")
from unittest.mock import MagicMock

from clients.zewm_robco_client import ZewmRobcoClient

resp = MagicMock()
resp.json.return_value = {"d": {"results": [{"Who": "W1"}, {"Who": "W2"}]}}
result = ZewmRobcoClient.parse_response(resp)
print("Result type:", type(result))
print("Result:", result)
print("Has results key:", "results" in result)
