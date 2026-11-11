#!/usr/bin/env python3
"""Generate offline test fixtures: a fake PIB feed plus one HTML page per release.

Every title starts with [SAMPLE] and the body says so. The text is written only to
exercise the parser, the tagging rules and the site layout. It is not real PIB content,
and the PRIDs are made up.
"""
from __future__ import annotations

import html
from pathlib import Path

OUT = Path(__file__).resolve().parent / "fixtures"

NOTE = "Sample text for layout testing only. This is not a real PIB release."

# (prid, day, time, ministry, title, extra body sentences, office)
ITEMS = [
    (9000001, "07", "10:42AM", "Cabinet",
     "[SAMPLE] Cabinet approves national mission for critical minerals recycling",
     "The Union Cabinet approved a mission with an outlay of Rs 1,500 crore over five years. Salient features include a recycling incentive and a National Critical Mineral Mission portal. The Ministry of Mines will be the nodal ministry.", "PIB Delhi"),
    (9000002, "07", "11:05AM", "Ministry of Defence",
     "[SAMPLE] India and a partner navy begin first joint maritime exercise 'Sagar Mitra'",
     "The joint exercise is the first of its kind between the two navies and includes harbour and sea phases. It is held in the Bay of Bengal off Visakhapatnam.", "PIB Delhi"),
    (9000003, "07", "09:20AM", "Ministry of Electronics & IT",
     "[SAMPLE] Ministry launches web portal for component manufacturing scheme applicants",
     "The portal lets applicants track approvals under the Electronics Components Manufacturing Scheme (ECMS). Twelve applicants were announced as approved.", "PIB Delhi"),
    (9000004, "07", "08:55AM", "Ministry of Road Transport & Highways",
     "[SAMPLE] NHAI issues guidelines to standardise multi-lane free flow tolling",
     "The guidelines apply to national highways with four or more lanes and set design and infrastructure standards for barrier-free tolling.", "PIB Delhi"),
    (9000005, "07", "11:20AM", "President's Secretariat",
     "[SAMPLE] Ambassadors of four countries present credentials to the President",
     "The ambassadors presented their credentials at Rashtrapati Bhavan in a ceremony.", "PIB Delhi"),
    (9000006, "07", "10:10AM", "Ministry of Railways",
     "[SAMPLE] Union Minister inspects passenger facilities and visits station",
     "The Minister reviewed passenger amenities and security arrangements during a visit.", "PIB Delhi"),
    (9000007, "07", "09:45AM", "Ministry of Finance",
     "[SAMPLE] Department of Revenue concludes Special Campaign 6.0 on pending matters",
     "The department reported disposal of pending references during the Special Campaign.", "PIB Delhi"),
    (9000008, "07", "08:30AM", "Ministry of Finance",
     "[SAMPLE] Limited departmental competitive examination for stenographers: notice",
     "The notice lists the schedule of the limited departmental competitive examination, 2019, 2020 and 2021.", "PIB Delhi"),
    (9000009, "07", "10:55AM", "Ministry of Communications",
     "[SAMPLE] Agreement signed to implement amended BharatNet programme in a state",
     "An agreement was signed between the Digital Bharat Nidhi, the Department of Telecommunications and the state government for broadband rollout under BharatNet.", "PIB Delhi"),
    (9000010, "07", "09:05AM", "Ministry of Home Affairs",
     "[SAMPLE] Central Narcotics Bureau celebrates foundation day",
     "The bureau marked its foundation day with an enforcement review.", "PIB Delhi"),
    (9000011, "07", "11:30AM", "Ministry of Commerce & Industry",
     "[SAMPLE] Geographical Indication tag granted to a traditional craft from Andhra Pradesh",
     "The Geographical Indications Registry recognised a traditional craft from Kondapalli in Krishna district of Andhra Pradesh. GI tag holders gain legal protection against misuse of the name.", "PIB Vijayawada"),
    (9000012, "07", "10:25AM", "Department of Space",
     "[SAMPLE] ISRO schedules launch of earth observation satellite from Sriharikota",
     "The launch vehicle will lift off from the Satish Dhawan Space Centre, Sriharikota. The satellite will support agriculture and disaster management.", "PIB Delhi"),
    (9000013, "06", "17:10PM", "Ministry of Statistics & Programme Implementation",
     "[SAMPLE] Periodic Labour Force Survey report released for the quarter",
     "The report shows the unemployment rate at 5.2 per cent in urban areas. It is released by the National Statistics Office.", "PIB Delhi"),
    (9000014, "06", "15:30PM", "Ministry of Jal Shakti",
     "[SAMPLE] Centre approves funds for Polavaram project components",
     "The Polavaram irrigation project on the Godavari river in Andhra Pradesh received an approved central release of Rs 2,000 crore.", "PIB Delhi"),
    (9000015, "06", "12:40PM", "Ministry of Environment, Forest and Climate Change",
     "[SAMPLE] Government notifies rules under the Biological Diversity framework",
     "The notification sets out benefit-sharing norms for biological resources and was issued in the Gazette.", "PIB Delhi"),
    (9000016, "06", "11:15AM", "Ministry of External Affairs",
     "[SAMPLE] India and a partner country sign joint statement on strategic partnership",
     "A joint statement and an MoU on digital cooperation were signed during the bilateral visit.", "PIB Delhi"),
    (9000017, "06", "09:50AM", "Ministry of Agriculture & Farmers Welfare",
     "[SAMPLE] Union Minister meets farmer groups and addresses a state workshop",
     "The Minister interacted with farmers and addressed a workshop.", "PIB Delhi"),
    (9000018, "05", "16:00PM", "Ministry of Health and Family Welfare",
     "[SAMPLE] National programme for tuberculosis elimination launches new diagnostic initiative",
     "The initiative under the National Tuberculosis Elimination Programme introduces new molecular diagnostics at the district level.", "PIB Delhi"),
    (9000019, "05", "13:20PM", "Ministry of Culture",
     "[SAMPLE] UNESCO inscribes a festival on its list of intangible cultural heritage",
     "The inscription was announced at the UNESCO committee session.", "PIB Delhi"),
    (9000020, "05", "10:05AM", "Prime Minister's Office",
     "[SAMPLE] PM greets citizens on a festival",
     "The Prime Minister extended greetings to the nation.", "PIB Delhi"),
]

MONTH = "NOV"


def page(prid, day, time_, ministry, title, extra, office) -> str:
    hh, rest = time_.split(":")
    mm, ap = rest[:2], rest[2:]
    # fixtures use 24h for the afternoon on purpose in the source tuple; normalise to 12h with AM/PM
    h = int(hh)
    if ap == "PM" and h > 12:
        h -= 12
    stamp = f"{day} {MONTH} 2026 {h}:{mm}{ap}"
    paras = "".join(f"<p>{html.escape(s.strip())}.</p>" for s in (NOTE + " " + extra).split(".") if s.strip())
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>PIB</title></head><body>
<div class="header"><a href="/">Home</a></div>
<div class="innner-page-main-about-us-content-right-part">
  <div class="MinistryNameSubhead"><h3>{html.escape(ministry)}</h3></div>
  <h2>{html.escape(title)}</h2>
  <div class="ReleaseDateSubHeaddateTime text-center">Posted On: {stamp} by {office}</div>
  <div class="contentdiv">{paras}<p>***</p><p>AB/CD/{prid}</p></div>
</div>
<div class="footer">Provide suggestions / comments</div>
</body></html>"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    feed_items = []
    for prid, day, time_, ministry, title, extra, office in ITEMS:
        (OUT / f"{prid}.html").write_text(page(prid, day, time_, ministry, title, extra, office), encoding="utf-8")
        feed_items.append(
            f"<item><title>{html.escape(title)}</title>"
            f"<link>https://pib.gov.in/PressReleaseIframePage.aspx?PRID={prid}</link></item>"
        )
    # the real feed repeats items now and then; mirror that
    feed_items.append(feed_items[0])
    xml = (
        '﻿<?xml version="1.0" encoding="utf-8"?><rss version="2.0"><channel>'
        "<title>Press Information Bureau (sample)</title><description>sample</description>"
        + "".join(feed_items)
        + "</channel></rss>"
    )
    (OUT / "feed.xml").write_text(xml, encoding="utf-8")
    print(f"wrote {len(ITEMS)} fixture pages and feed.xml to {OUT}")


if __name__ == "__main__":
    main()
