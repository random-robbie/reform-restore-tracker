import requests
import time

BASE_MEMBERS = "https://members-api.parliament.uk/api"
BASE_VOTES   = "https://commonsvotes-api.parliament.uk/data"

PARTIES = {
    "Reform UK":       1036,
    "Restore Britain": 1117,
}


def _get(url: str, params: dict | None = None, retries: int = 3) -> any:
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params,
                             headers={"Accept": "application/json"}, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            if attempt == retries - 1:
                raise
            wait = 2 ** attempt
            print(f"  retrying {url} in {wait}s ({exc})")
            time.sleep(wait)


def get_all_mps() -> list[dict]:
    all_mps = []
    for party_name, party_id in PARTIES.items():
        skip = 0
        while True:
            data = _get(f"{BASE_MEMBERS}/Members/Search", {
                "PartyId": party_id,
                "House":   1,
                "IsCurrentMember": "true",
                "skip": skip,
                "take": 50,
            })
            items = data.get("items", [])
            for item in items:
                v = item.get("value", {})
                membership = v.get("latestHouseMembership", {})
                all_mps.append({
                    "member_id":    v.get("id"),
                    "name":         v.get("nameDisplayAs", ""),
                    "party":        party_name,
                    "party_id":     party_id,
                    "constituency": membership.get("membershipFrom", ""),
                    "thumbnail_url": v.get("thumbnailUrl", ""),
                })
            if len(items) < 50:
                break
            skip += 50
    return all_mps


_PAGE = 25  # API hard-caps responses at 25 regardless of take


def get_member_votes(member_id: int) -> list[dict]:
    votes = []
    skip  = 0
    while True:
        data = _get(f"{BASE_VOTES}/divisions.json/membervoting", {
            "queryParameters.memberId": member_id,
            "queryParameters.skip":     skip,
            "queryParameters.take":     _PAGE,
        })
        if not isinstance(data, list) or not data:
            break
        for v in data:
            div = v.get("PublishedDivision", {})
            date_raw = div.get("Date", "")
            votes.append({
                "member_id":  member_id,
                "voted_aye":  1 if v.get("MemberVotedAye")  else 0,
                "voted_no":   1 if v.get("MemberVotedNo")   else 0,
                "was_teller": 1 if v.get("MemberWasTeller") else 0,
                "division": {
                    "division_id": div.get("DivisionId"),
                    "date":        date_raw.split("T")[0] if date_raw else "",
                    "number":      div.get("Number"),
                    "title":       div.get("Title", ""),
                    "aye_count":   div.get("AyeCount") or 0,
                    "no_count":    div.get("NoCount")  or 0,
                    "is_deferred": 1 if div.get("IsDeferred") else 0,
                    "evel_type":   div.get("EVELType", ""),
                    "evel_country": div.get("EVELCountry", ""),
                },
            })
        if len(data) < _PAGE:
            break
        skip += _PAGE
        time.sleep(0.1)
    return votes
