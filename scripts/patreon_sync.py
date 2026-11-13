"""Pull active Patreon members and write members.txt for the Penthouse supporter board and suite doors.

Output, one member per line, highest tier first, then alphabetical:
    patron|VRChatName
    supporter|VRChatName
    vip|VRChatName

Names are VRChat display names. Patreon only knows Patreon names, so links.json maps
Patreon user id -> VRChat display name. Members without a link are listed in
unlinked.txt (Patreon name and id only, never e-mail) so the owner can add them.

Env: PATREON_TOKEN (creator access token), PATREON_CAMPAIGN_ID (optional; first campaign if unset).
Stdlib only, runs in GitHub Actions without installs.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

API = "https://www.patreon.com/api/oauth2/v2"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Tier by monthly amount actually pledged (cents), so renamed tiers and custom amounts still map.
TIERS = [("patron", 5000), ("supporter", 2000), ("vip", 700)]
ORDER = {name: i for i, (name, _) in enumerate(TIERS)}


def get(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "User-Agent": "penthouse-patreon-sync"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def campaign_id(token):
    cid = os.environ.get("PATREON_CAMPAIGN_ID")
    if cid:
        return cid
    data = get(f"{API}/campaigns", token)["data"]
    if not data:
        sys.exit("no campaign on this token")
    return data[0]["id"]


def members(token, cid):
    q = {
        "include": "user,currently_entitled_tiers",
        "fields[member]": "full_name,patron_status,currently_entitled_amount_cents",
        "fields[tier]": "amount_cents,title",
        "page[count]": "500",
    }
    url = f"{API}/campaigns/{cid}/members?{urllib.parse.urlencode(q)}"
    while url:
        page = get(url, token)
        tiers = {t["id"]: t["attributes"].get("amount_cents") or 0 for t in page.get("included", []) if t["type"] == "tier"}
        for m in page["data"]:
            a = m["attributes"]
            if a.get("patron_status") != "active_patron":
                continue
            cents = a.get("currently_entitled_amount_cents") or 0
            for t in m["relationships"]["currently_entitled_tiers"]["data"]:
                cents = max(cents, tiers.get(t["id"], 0))
            uid = (m["relationships"].get("user") or {}).get("data", {}) or {}
            yield uid.get("id", ""), a.get("full_name") or "", cents
        url = page.get("links", {}).get("next")


def tier_for(cents):
    for name, floor in TIERS:
        if cents >= floor:
            return name
    return None


def main():
    token = os.environ.get("PATREON_TOKEN")
    if not token:
        sys.exit("PATREON_TOKEN not set")
    with open(os.path.join(ROOT, "links.json"), encoding="utf-8") as f:
        links = {k: v for k, v in json.load(f).items() if not k.startswith("_")}

    rows, unlinked = {}, []
    for uid, pname, cents in members(token, campaign_id(token)):
        tier = tier_for(cents)
        if not tier:
            continue
        vrc = links.get(uid)
        if not vrc:
            unlinked.append(f"{tier}\t{pname}\t{uid}")
            continue
        if vrc not in rows or ORDER[tier] < ORDER[rows[vrc]]:
            rows[vrc] = tier

    lines = sorted((ORDER[t], n.casefold(), f"{t}|{n}") for n, t in rows.items())
    write(os.path.join(ROOT, "members.txt"), "".join(l[2] + "\n" for l in lines))
    write(os.path.join(ROOT, "unlinked.txt"), "".join(u + "\n" for u in sorted(unlinked)))
    print(f"{len(lines)} linked, {len(unlinked)} unlinked")


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


if __name__ == "__main__":
    main()
