# Yahoo API access

Yahoo gated the Fantasy Sports API behind an application. It is free and
read-only, but it is reviewed by a human, there is no published turnaround,
and the form says plainly:

> incomplete or insufficiently detailed submissions cannot be evaluated and
> will be closed without further correspondence

So the application is worth filling in properly the first time. Apply at
<https://sports.yahoo.com/developer/access/>. Leave Client ID blank if you have
no Yahoo Developer account; they provision one on approval.

Answers below, ready to paste.

---

**What product are you building?**

A private weekly recap generator for my own fantasy football leagues. It pulls
the completed week from the league API, computes the statistics in code, and
uses those computed figures to write a plain-text summary that I paste into my
league's group chat. It is a personal hobby project, not a product, not
monetized, and not distributed. Source: https://github.com/tfadp/fantasy-recap

**What Yahoo Fantasy Sports data do you need?**

Read-only, for a single league I am a member of:

- league metadata (name, season, current week, roster positions)
- weekly scoreboard: matchups and team scores
- team rosters for the completed week, with per-player points and lineup slot
- standings: wins, losses, points for and against
- league transactions for the week (adds, drops, FAAB bids)

No write access. No player or user data beyond my own league's twelve managers.

**Who is the intended user base?**

One user: me. The output goes to a twelve-person group chat of friends. It is
limited to the single league I play in and there is no sign-up, no public
interface and no way for anyone else to use it. Access is limited to personal,
single-league use.

**Estimated number of users**

One. Twelve people read the resulting text in a private group chat, but only my
own account ever authenticates against the API.

**Request volume**

Roughly one authenticated run per week during the NFL season, fetching a single
league's completed week: on the order of ten requests weekly, under two hundred
for a full season.

---

## Once approved

```bash
export YAHOO_CLIENT_ID=...
export YAHOO_CLIENT_SECRET=...
python3 setup_yahoo.py            # writes oauth2.json
python3 setup_yahoo.py --leagues  # prints your league key, e.g. 461.l.123456
```

Put the league key into `leagues.json` as `league_id`, set the `yahoo-api`
league to `"enabled": true`, and add `oauth2.json`'s contents as the
`YAHOO_OAUTH_JSON` repository secret so the scheduled run can authenticate.
