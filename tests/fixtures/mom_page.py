def row(dates, days, name, note=""):
    d = "<br>".join(dates); dy = "<br>".join(days)
    n = f'<p class="note"><em>{note}</em></p>' if note else ""
    return (f'<tr><td>{d}</td><td>{dy}</td><td><img alt="{name}"></td>'
            f'<td><strong>{name}</strong><span class="sr">{dates[0]}, {days[0]}</span>{n}</td></tr>')

def table(year, rows):
    return (f'<div id="Year-{year}" class="tab-pane"><table><thead><tr><th>Date</th><th>Day</th><th>Holiday image</th>'
            f'<th>Holiday name</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
            f'<a href="/files/ph{year}.ics">Add {year} public holidays to your calendar</a></div>')

Y2025 = [row(["1 January 2025"],["Wednesday"],"New Year's Day"), row(["29 January 2025","30 January 2025"],["Wednesday","Thursday"],"Chinese New Year"),
 row(["31 March 2025"],["Monday"],"Hari Raya Puasa"), row(["18 April 2025"],["Friday"],"Good Friday"), row(["1 May 2025"],["Thursday"],"Labour Day"),
 row(["3 May 2025"],["Saturday"],"Polling Day"), row(["12 May 2025"],["Monday"],"Vesak Day"), row(["7 June 2025"],["Saturday"],"Hari Raya Haji"),
 row(["9 August 2025"],["Saturday"],"National Day"), row(["20 October 2025"],["Monday"],"Deepavali"), row(["25 December 2025"],["Thursday"],"Christmas Day")]
Y2026 = [row(["1 January 2026"],["Thursday"],"New Year's Day"), row(["17 February 2026","18 February 2026"],["Tuesday","Wednesday"],"Chinese New Year"),
 row(["21 March 2026"],["Saturday"],"Hari Raya Puasa"), row(["3 April 2026"],["Friday"],"Good Friday"), row(["1 May 2026"],["Friday"],"Labour Day"),
 row(["27 May 2026"],["Wednesday"],"Hari Raya Haji"),
 row(["31 May 2026"],["Sunday"],"Vesak Day","Monday, 1 June 2026, will be a public holiday if your rest day falls on 31 May 2026."),
 row(["9 August 2026"],["Sunday"],"National Day","Monday, 10 August 2026, will be a public holiday if your rest day falls on 9 August 2026."),
 row(["8 November 2026"],["Sunday"],"Deepavali","Monday, 9 November 2026, will be a public holiday if your rest day falls on 8 November 2026."),
 row(["25 December 2026"],["Friday"],"Christmas Day")]
Y2027 = [row(["1 January 2027"],["Friday"],"New Year's Day"), row(["6 February 2027","7 February 2027"],["Saturday","Sunday"],"Chinese New Year","Monday, 8 February 2027, will be a public holiday if your rest day falls on 7 February 2027."),
 row(["10 March 2027"],["Wednesday"],"Hari Raya Puasa"), row(["26 March 2027"],["Friday"],"Good Friday"), row(["1 May 2027"],["Saturday"],"Labour Day"),
 row(["17 May 2027"],["Monday"],"Hari Raya Haji"), row(["20 May 2027"],["Thursday"],"Vesak Day"), row(["9 August 2027"],["Monday"],"National Day"),
 row(["28 October 2027"],["Thursday"],"Deepavali"), row(["25 December 2027"],["Saturday"],"Christmas Day")]

def page(headings=False):
    tabs = '<ul class="tabs"><li><a href="#Year-2025">2025</a></li><li><a href="#Year-2026">2026</a></li><li><a href="#Year-2027">2027</a></li></ul>'
    banner = '<div class="next"><p>Next public holiday</p><p>8 November, Sunday</p><p>Deepavali</p></div>'
    body = "".join((f"<h3>{y}</h3>" if headings else "") + table(y, r) for y, r in ((2025, Y2025), (2026, Y2026), (2027, Y2027)))
    return f"<html><body><h1>Public holidays for 2025, 2026 and 2027</h1>{banner}{tabs}{body}<p>Last updated: 19 June 2026</p></body></html>"
