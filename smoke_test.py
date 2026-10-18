"""Check a RUNNING API (local or deployed).

  python smoke_test.py                                   # http://127.0.0.1:8000
  python smoke_test.py https://your-app.onrender.com owner@reviewpilot.com Owner@12345
"""
import sys

import httpx

base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
email = sys.argv[2] if len(sys.argv) > 2 else "owner@reviewpilot.com"
pw = sys.argv[3] if len(sys.argv) > 3 else "Owner@12345"
fails = 0


def check(name, ok, info=""):
    global fails
    fails += not ok
    print(("PASS" if ok else "FAIL"), "-", name, info)


c = httpx.Client(base_url=base, timeout=60)
r = c.get("/health")
check("health", r.status_code == 200, r.text)
r = c.post("/login", json={"email": email, "password": pw})
check("login", r.status_code == 200, f"role={r.json().get('role')}" if r.status_code == 200 else r.text)
if r.status_code != 200:
    sys.exit("Cannot continue without login")
h = {"Authorization": f"Bearer {r.json()['access_token']}"}
check("wrong password rejected", c.post("/login", json={"email": email, "password": "nope"}).status_code == 401)
check("no token rejected", c.get("/reviews").status_code == 401)

r = c.post("/reviews", headers=h, json={"text": "Khana thanda tha aur waiter bohat bad-tameez tha. Worst!", "rating": 1, "platform": "Foodpanda"})
check("POST /reviews", r.status_code == 201, "")
if r.status_code == 201:
    d = r.json()
    print("   sentiment:", d["sentiment"], "| category:", d["category"], "| urgent:", d["urgent"], "| source:", d["ai_source"])
    print("   reply:", d["suggested_reply"][:200])
    check("rating 1 => urgent", d["urgent"] is True)
    check("GET /reviews/{id}", c.get(f"/reviews/{d['id']}", headers=h).status_code == 200)
check("GET /reviews", c.get("/reviews", headers=h).status_code == 200)
check("GET /reviews?urgent=true", c.get("/reviews?urgent=true", headers=h).status_code == 200)
r = c.get("/stats", headers=h)
check("GET /stats", r.status_code == 200, str(r.json()) if r.status_code == 200 else "")
check("GET /policy", c.get("/policy", headers=h).status_code in (200, 404))
print("\nAll good!" if not fails else f"\n{fails} check(s) failed")
sys.exit(1 if fails else 0)
