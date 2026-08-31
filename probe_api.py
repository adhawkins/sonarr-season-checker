
import requests
base = "https://sonarr.gently.org.uk:7000"
key = "e6000cd6f6a64609b3225e102bf948a2"
r = requests.get(base + "/api/v3/series", params={"tvdbIds": "73762"}, headers={"X-Api-Key": key}, timeout=15)
print("v3 series status:", r.status_code)
print(r.text[:1500])
