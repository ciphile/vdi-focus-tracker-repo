"""Ngày lễ Singapore: lịch có sẵn, file timesheet, cache riêng, ngày nghỉ tự khai, cuối tuần, /off.
Lịch từ trang MOM: đọc HTML (bản lưu giả lập, KHÔNG gọi mạng thật), kiểm năm, cache theo năm, thử lại 1 lần/ngày,
nghỉ bù lễ rơi Chủ nhật (kể cả dây chuyền sang thứ Ba)."""
import datetime as dt
import json
import os
import urllib.error
import unittest
from unittest import mock

from focus import holidays
from focus.analysis import off_day
from focus.storage import db_path, open_db, save_note
from tests.helpers import TempCase, make_cfg


class HolidaysTest(TempCase):
    def own(self, year):
        return os.path.join(self.cfg["data_dir"], f"holidays_{year}.json")

    def write_timesheet(self, year, content):
        os.makedirs(self.cfg["timesheet_data_dir"], exist_ok=True)
        with open(os.path.join(self.cfg["timesheet_data_dir"], f"sg_holidays_{year}.json"), "w",
                  encoding="utf-8") as f:
            f.write(content if isinstance(content, str) else json.dumps(content))

    def test_builtin_2026(self):
        h = holidays.holidays(self.cfg, 2026)
        self.assertEqual(len(h), 11)
        self.assertEqual(holidays.off_reason(self.cfg, "2026-08-10"), "nghỉ bù National Day")  # lễ rơi CN
        self.assertEqual(holidays.off_reason(self.cfg, "2026-12-25"), "Christmas Day")
        self.assertEqual(holidays.off_reason(self.cfg, dt.date(2026, 5, 1)), "Labour Day")
        self.assertIsNone(holidays.off_reason(self.cfg, "2026-10-14"))
        # Bảng có sẵn KHÔNG ghi vào cache riêng: để việc nền vẫn lấy bản MOM (ưu tiên hơn bảng có sẵn).
        self.assertFalse(os.path.exists(self.own(2026)))

    def test_saturday_holiday_no_auto_monday(self):
        self.write_timesheet(2027, ["2027-01-02"])  # thứ Bảy
        self.assertEqual(holidays.off_reason(self.cfg, "2027-01-02"), "cuối tuần")
        self.assertIsNone(holidays.off_reason(self.cfg, "2027-01-04"))

    def test_weekends(self):
        self.assertEqual(holidays.off_reason(self.cfg, "2026-10-17"), "cuối tuần")
        self.assertEqual(holidays.off_reason(self.cfg, "2026-10-18"), "cuối tuần")
        self.assertIsNone(holidays.off_reason(self.cfg, "2026-10-16"))

    def test_extra_off_days(self):
        cfg = make_cfg(self.tmp, extra_off_days=["2026-12-24"])
        self.assertEqual(holidays.off_reason(cfg, "2026-12-24"), "ngày nghỉ bạn khai trong config")
        self.assertIsNone(holidays.off_reason(self.cfg, "2026-12-24"))

    def test_timesheet_file(self):
        self.write_timesheet(2027, {"holidays": [{"date": "2027-01-01", "name": "NY"},
                                                 {"date": "2027-02-08"}, {"date": "2026-12-25"}],
                                    "generated": "2026-11-30"})
        h = holidays.holidays(self.cfg, 2027)
        self.assertEqual(sorted(h), ["2027-01-01", "2027-02-08"])  # bỏ ngày lệch năm
        self.assertEqual(holidays.off_reason(self.cfg, "2027-02-08"), "Public Holiday")
        with open(self.own(2027), encoding="utf-8") as f:
            self.assertEqual(sorted(json.load(f)["dates"]), ["2027-01-01", "2027-02-08"])

    def test_timesheet_overrides_builtin_once_cached_own_wins(self):
        self.write_timesheet(2026, ["2026-10-14"])
        self.assertEqual(holidays.off_reason(self.cfg, "2026-10-14"), "Public Holiday")
        self.write_timesheet(2026, ["2026-10-15"])
        holidays.clear_memo()
        self.assertEqual(holidays.off_reason(self.cfg, "2026-10-14"), "Public Holiday")  # cache riêng đọc trước

    def test_bad_files_tolerated(self):
        self.write_timesheet(2028, "{hỏng json, không có ngày nào")
        self.assertEqual(holidays.holidays(self.cfg, 2028), {})
        self.assertTrue(any("HOLIDAYS_MISSING" in l for l in self.audit_lines()))
        holidays.clear_memo()
        self.write_timesheet(2028, "{hỏng json nhưng có 2028-03-03 và 2027-01-01")
        self.assertEqual(holidays.holidays(self.cfg, 2028), {"2028-03-03": "Public Holiday"})

    def test_bad_own_cache_tolerated(self):
        for junk in ("{hỏng", "[1, 2]", '"chuỗi"', '{"year": 2026, "dates": ["2026-10-14"]}',
                     '{"year": 2025, "dates": {"2026-10-14": "x"}}', '{"year": 2026, "dates": {"2025-01-01": "x"}}'):
            holidays.clear_memo()
            with open(self.own(2026), "w", encoding="utf-8") as f:
                f.write(junk)
            self.assertIsNone(holidays.off_reason(self.cfg, "2026-10-14"), junk)
            self.assertEqual(holidays.off_reason(self.cfg, "2026-12-25"), "Christmas Day", junk)  # về lịch có sẵn

    def test_missing_year_empty(self):
        cfg = make_cfg(self.tmp, timesheet_data_dir="")
        self.assertEqual(holidays.holidays(cfg, 2031), {})
        self.assertIsNone(holidays.off_reason(cfg, "2031-01-01"))
        self.assertFalse(os.path.exists(self.own(2031)))

    def test_next_year_missing(self):
        self.assertFalse(holidays.next_year_missing(self.cfg, dt.date(2026, 12, 14)))
        self.assertTrue(holidays.next_year_missing(self.cfg, dt.date(2026, 12, 15)))
        self.write_timesheet(2027, ["2027-01-01"])
        self.assertFalse(holidays.next_year_missing(self.cfg, dt.date(2026, 12, 20)))

    def test_next_year_missing_checks_once_per_day(self):
        day = dt.date(2026, 12, 16)
        for _ in range(5):  # tracker hỏi mỗi 30 giây
            self.assertTrue(holidays.next_year_missing(self.cfg, day))
        self.assertEqual(sum("HOLIDAYS_MISSING" in l for l in self.audit_lines()), 1)
        self.write_timesheet(2027, ["2027-01-01"])
        self.assertTrue(holidays.next_year_missing(self.cfg, day))  # cùng ngày: dùng kết quả đã nhớ
        self.assertFalse(holidays.next_year_missing(self.cfg, dt.date(2026, 12, 17)))  # ngày mới: kiểm lại

    def test_off_day_note_wins(self):
        db = open_db(db_path(self.cfg))
        self.addCleanup(db.close)
        self.assertIsNone(off_day(db, self.cfg, "2026-10-14"))
        save_note(db, "2026-10-14", {"day_off": "nghỉ phép"})
        self.assertEqual(off_day(db, self.cfg, "2026-10-14"), "nghỉ phép")
        self.assertEqual(off_day(db, self.cfg, "2026-12-25"), "Christmas Day")
        save_note(db, "2026-10-14", {"day_off": None})  # /on
        self.assertIsNone(off_day(db, self.cfg, "2026-10-14"))


# ------------------------------------------------------------ trang MOM

ROWS_2026 = [("New Year's Day", "1 Jan 2026", "Thursday"),
             ("Chinese New Year", "17 &amp; 18 Feb 2026", "Tuesday &amp; Wednesday"),
             ("Hari Raya Puasa", "21 March 2026", "Saturday"),
             ("Good Friday", "3 Apr 2026", "Friday"),
             ("Labour Day", "1 May 2026", "Friday"),
             ("Hari Raya Haji", "27 May 2026", "Wednesday"),
             ("Vesak Day*", "31 May 2026", "Sunday"),
             ("National Day*", "9 August 2026", "Sunday"),
             ("Deepavali*", "8 Nov 2026", "Sunday"),
             ("Christmas Day", "25 Dec 2026", "Friday")]
# Năm 2027 trong bản lưu giả lập (không phải lịch thật): đủ kiểu viết ngày.
ROWS_2027 = [("New Year's Day", "1 January 2027", "Friday"),
             ("Chinese New Year", "6 and 7 Feb 2027", "Saturday and Sunday"),
             ("Hari Raya Puasa", "10 Mar 2027", "Wednesday"),
             ("Good Friday", "26 Mar 2027", "Friday"),
             ("Labour Day", "1 May 2027", "Saturday"),
             ("Vesak Day", "20 May 2027", "Thursday"),
             ("National Day", "9 Aug 2027", "Monday"),
             ("Deepavali", "28 Oct 2027", "Thursday"),
             ("Christmas Day", "25 Dec 2027", "Saturday")]


def table(rows, header=True):
    head = "<thead><tr><th>Holiday</th><th>Date</th><th>Day</th></tr></thead>" if header else ""
    body = "".join(f"<tr><td>{n}</td><td>{d}</td><td>{w}</td></tr>" for n, d, w in rows)
    return f"<div class='table-responsive'><table class='table'>{head}<tbody>{body}</tbody></table></div>"


def page(*sections, intro=True):
    """Trang giống MOM: menu, script, tiêu đề chung có 2 năm, ghi chú có ngày, rồi từng năm một bảng."""
    parts = ["<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'><title>Public holidays</title>",
             "<script>var cfg = {year: '2025', note: '<table><tr><td>1 Jan 2025</td></tr></table>'};</script>",
             "<style>h2{color:red}</style></head><body>",
             "<nav><ul><li><a href='/'>Home</a></li><li><a href='/ep'>Employment practices</a></li></ul></nav>",
             "<main><h1>Public holidays for 2026 and 2027</h1>" if intro else "<main>",
             "<p>Last updated: 1 Dec 2026</p>"]
    for heading, rows in sections:
        parts.append(f"<h2 class='title'><span>Public holidays {heading}</span></h2>" + table(rows))
        parts.append("<p>* The following Monday will be a public holiday.</p>")
    parts.append("</main><footer>© 2026 Ministry of Manpower</footer></body></html>")
    return "".join(parts)


PAGE = page(("2026", ROWS_2026), ("2027", ROWS_2027))


class ParseTest(TempCase):
    def test_parse_dates_formats(self):
        p = holidays.parse_dates
        self.assertEqual(p("1 Jan 2026"), [dt.date(2026, 1, 1)])
        self.assertEqual(p("1 January 2026"), [dt.date(2026, 1, 1)])
        self.assertEqual(p("17 & 18 Feb 2026"), [dt.date(2026, 2, 17), dt.date(2026, 2, 18)])
        self.assertEqual(p("6 and 7 February 2027"), [dt.date(2027, 2, 6), dt.date(2027, 2, 7)])
        self.assertEqual(p("Jan 1, 2026"), [dt.date(2026, 1, 1)])
        self.assertEqual(p("Thursday, 1 Jan", 2026), [dt.date(2026, 1, 1)])
        self.assertEqual(p("31 Jan & 1 Feb 2027"), [dt.date(2027, 1, 31), dt.date(2027, 2, 1)])
        self.assertEqual(p("10 Aug 2026*"), [dt.date(2026, 8, 10)])
        self.assertEqual(p("Monday"), [])
        self.assertEqual(p("1 Jan"), [], "thiếu năm, không có năm mặc định")
        with self.assertRaises(ValueError):
            p("31 Feb 2026")

    def test_parse_two_years(self):
        years, rejected = holidays.parse_mom(PAGE)
        self.assertEqual(rejected, {})
        self.assertEqual(sorted(years), [2026, 2027])
        self.assertEqual(years[2026], holidays.BUILTIN[2026], "đọc đúng y như lịch MOM 2026")
        self.assertEqual(years[2027]["2027-02-07"], "Chinese New Year")
        self.assertEqual(len(years[2027]), 10)

    def test_year_with_wrong_date_rejected_other_kept(self):
        bad = ROWS_2027 + [("Christmas Day", "25 Dec 2026", "Friday")]  # lệch năm trong bảng 2027
        years, rejected = holidays.parse_mom(page(("2026", ROWS_2026), ("2027", bad)))
        self.assertEqual(sorted(years), [2026])
        self.assertIn(2027, rejected)
        self.assertIn("2026-12-25", rejected[2027])

    def test_tab_strip_layout(self):
        html = ("<html><body><ul class='tabs'><li><a href='#t1'>2026</a></li><li><a href='#t2'>2027</a></li></ul>"
                f"<div id='t1'>{table(ROWS_2026)}</div><div id='t2'>{table(ROWS_2027)}</div></body></html>")
        years, _ = holidays.parse_mom(html)
        self.assertEqual(sorted(years), [2026, 2027])

    def test_caption_and_headerless_table(self):
        rows = "".join(f"<tr><td>{d}</td><td>{w}</td><td>{n}</td></tr>" for n, d, w in ROWS_2026)
        html = f"<table><caption>Public Holidays 2026</caption>{rows}</table>"
        years, _ = holidays.parse_mom(html)
        self.assertEqual(years[2026]["2026-08-09"], "National Day")

    def test_html_changed_gives_nothing(self):
        for html in ("", "<html><body><p>Site under maintenance</p></body></html>",
                     "<table><tr><td>a</td></tr></table>", "<h2>2026</h2><table><tr><td>x</td><td>1 Jan 2026</td></tr></table>",
                     "<<<>>> not html at all 2026 & 2027", "<h2>2026</h2><table><tr><td>X</td><td>31 Feb 2026</td></tr></table>"):
            with self.subTest(html=html[:40]):
                years, _ = holidays.parse_mom(html)
                self.assertEqual(years, {})


class FetchTest(TempCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.html = PAGE
        p = mock.patch.object(holidays, "_download", side_effect=self.fake_download)
        p.start()
        self.addCleanup(p.stop)

    def fake_download(self, url, timeout=None):
        self.calls.append((url, timeout))
        if isinstance(self.html, Exception):
            raise self.html
        return self.html

    def own(self, year):
        return os.path.join(self.cfg["data_dir"], f"holidays_{year}.json")

    def test_fetch_saves_one_file_per_year(self):
        self.assertTrue(holidays.ensure_year(self.cfg, 2027, dt.date(2026, 12, 1)))
        self.assertEqual(self.calls, [(holidays.MOM_URL, 20)])
        for year in (2026, 2027):
            with open(self.own(year), encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual((data["year"], data["source"]), (year, "mom"))
            self.assertTrue(all(d.startswith(str(year)) for d in data["dates"]))
            self.assertIn("fetched_at", data)
        self.assertEqual(holidays.off_reason(self.cfg, "2027-02-08"), "nghỉ bù Chinese New Year")  # 7/2 CN
        self.assertTrue(any("HOLIDAYS_FETCHED" in l for l in self.audit_lines()))

    def test_cache_hit_never_hits_network(self):
        holidays.ensure_year(self.cfg, 2027, dt.date(2026, 12, 1))
        self.calls.clear()
        for day in (dt.date(2026, 12, 2), dt.date(2026, 12, 20)):
            self.assertTrue(holidays.ensure_year(self.cfg, 2027, day))
            self.assertTrue(holidays.ensure_next_year_cached(self.cfg, day))
        holidays.background_check(self.cfg, dt.date(2026, 12, 3))  # 2026 cũng đã có cache từ lần tải trước
        self.assertEqual(self.calls, [])

    def test_failure_retries_at_most_once_per_day(self):
        self.html = urllib.error.URLError("no route")
        day = dt.date(2026, 12, 2)
        for _ in range(3):  # tracker khởi động lại nhiều lần trong ngày
            self.assertFalse(holidays.ensure_next_year_cached(self.cfg, day))
        self.assertEqual(len(self.calls), 1)
        self.assertFalse(os.path.exists(self.own(2027)))
        self.assertTrue(any("HOLIDAYS_FETCH_FAIL" in l for l in self.audit_lines()))
        self.html = PAGE
        self.assertTrue(holidays.ensure_next_year_cached(self.cfg, dt.date(2026, 12, 3)))  # hôm sau thử lại
        self.assertEqual(len(self.calls), 2)

    def test_changed_html_saves_nothing(self):
        self.html = "<html><body>New design, no tables</body></html>"
        self.assertFalse(holidays.ensure_year(self.cfg, 2027, dt.date(2026, 12, 5)))
        self.assertEqual([f for f in os.listdir(self.cfg["data_dir"]) if f.startswith("holidays_")], [])
        self.assertTrue(any("HOLIDAYS_FETCH_FAIL" in l for l in self.audit_lines()))

    def test_page_without_requested_year(self):
        self.html = page(("2026", ROWS_2026))
        self.assertFalse(holidays.ensure_year(self.cfg, 2027, dt.date(2026, 12, 5)))
        self.assertTrue(os.path.exists(self.own(2026)), "năm khác hợp lệ vẫn được lưu")
        self.assertFalse(os.path.exists(self.own(2027)))

    def test_wrong_year_rejected_not_saved(self):
        bad = ROWS_2027 + [("X", "3 Mar 2026", "Tuesday")]
        self.html = page(("2026", ROWS_2026), ("2027", bad))
        self.assertFalse(holidays.ensure_year(self.cfg, 2027, dt.date(2026, 12, 5)))
        self.assertFalse(os.path.exists(self.own(2027)))
        self.assertTrue(any("HOLIDAYS_REJECTED" in l for l in self.audit_lines()))

    def test_next_year_only_in_december(self):
        self.assertFalse(holidays.ensure_next_year_cached(self.cfg, dt.date(2026, 11, 30)))
        self.assertEqual(self.calls, [])
        self.assertTrue(holidays.ensure_next_year_cached(self.cfg, dt.date(2026, 12, 1)))

    def test_background_check_prefers_mom_over_builtin_and_never_raises(self):
        holidays.background_check(self.cfg, dt.date(2026, 10, 14))  # 2026: chỉ có bảng có sẵn -> lấy bản MOM
        self.assertEqual(len(self.calls), 1)
        with open(self.own(2026), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["source"], "mom")
        self.html = RuntimeError("lỗi lạ")
        holidays.background_check(self.cfg, dt.date(2026, 12, 14))  # thiếu 2027, tải lỗi: không raise
        with mock.patch.object(holidays, "_read_own", side_effect=OSError("disk")):
            holidays.background_check(self.cfg, dt.date(2026, 12, 15))

    def test_timesheet_file_counts_as_cache(self):
        os.makedirs(self.cfg["timesheet_data_dir"], exist_ok=True)
        with open(os.path.join(self.cfg["timesheet_data_dir"], "sg_holidays_2026.json"), "w") as f:
            json.dump(["2026-01-01"], f)
        holidays.holidays(self.cfg, 2026)  # đọc lúc khởi động -> chép vào cache riêng
        holidays.background_check(self.cfg, dt.date(2026, 10, 14))
        self.assertEqual(self.calls, [], "đã có file timesheet: không tải MOM")

    def test_disabled_by_config(self):
        cfg = dict(self.cfg, holiday_fetch_enabled=False)
        self.assertFalse(holidays.ensure_year(cfg, 2027, dt.date(2026, 12, 5)))
        self.assertEqual(self.calls, [])

    def test_today_known_fetches_only_when_year_has_nothing(self):
        self.assertTrue(holidays.ensure_today_known(self.cfg, dt.date(2026, 10, 14)))  # bảng có sẵn
        self.assertEqual(self.calls, [])
        self.html = page(("2031", [(n, d.replace("2026", "2031"), w) for n, d, w in ROWS_2026]))
        self.assertTrue(holidays.ensure_today_known(self.cfg, dt.date(2031, 1, 1)))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(holidays.off_reason(self.cfg, "2031-05-01"), "Labour Day")

    def test_bad_cache_files_ignored(self):
        for junk in ({"year": 2027, "dates": {"2026-12-25": "x"}}, {"year": 2026, "dates": {"2027-01-01": "x"}}):
            with open(self.own(2027), "w", encoding="utf-8") as f:
                json.dump(junk, f)
            self.assertIsNone(holidays._read_own(self.cfg, 2027))

    def test_download_sets_user_agent_and_timeout(self):
        seen = {}

        class Resp:
            headers = mock.Mock(get_content_charset=lambda: "utf-8")

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                return b"<html></html>"

        def urlopen(req, timeout, **kw):
            seen["ua"], seen["timeout"] = req.get_header("User-agent"), timeout
            return Resp()
        mock.patch.stopall()
        with mock.patch("urllib.request.urlopen", urlopen):
            self.assertEqual(holidays._download(holidays.MOM_URL), "<html></html>")
        self.assertTrue(seen["ua"])
        self.assertEqual(seen["timeout"], 20)


class ObservedTest(TempCase):
    def write_own(self, year, dates):
        with open(os.path.join(self.cfg["data_dir"], f"holidays_{year}.json"), "w", encoding="utf-8") as f:
            json.dump({"year": year, "dates": dates, "source": "mom"}, f)

    def test_sunday_to_monday_builtin_2026(self):
        self.assertEqual(holidays.off_reason(self.cfg, "2026-06-01"), "nghỉ bù Vesak Day")
        self.assertEqual(holidays.off_reason(self.cfg, "2026-08-10"), "nghỉ bù National Day")
        self.assertEqual(holidays.off_reason(self.cfg, "2026-11-09"), "nghỉ bù Deepavali")
        self.assertIsNone(holidays.off_reason(self.cfg, "2026-03-23"), "lễ thứ Bảy: không tự nghỉ thứ Hai")
        self.assertEqual(holidays.off_detail(self.cfg, "2026-08-10")[0], "observed")

    def test_cascade_when_monday_is_also_holiday(self):
        # 2028-01-02 là Chủ nhật, 2028-01-03 (thứ Hai) cũng là lễ -> nghỉ bù thứ Ba 04/01.
        self.write_own(2028, {"2028-01-02": "Lễ A", "2028-01-03": "Lễ B", "2028-02-06": "Lễ C"})
        self.assertEqual(holidays.off_reason(self.cfg, "2028-01-03"), "Lễ B")
        self.assertEqual(holidays.off_reason(self.cfg, "2028-01-04"), "nghỉ bù Lễ A")
        self.assertIsNone(holidays.off_reason(self.cfg, "2028-01-05"))
        self.assertEqual(holidays.off_reason(self.cfg, "2028-02-07"), "nghỉ bù Lễ C")

    def test_two_sundays_in_a_row_chain(self):
        # Lễ CN 2028-02-06, thứ Hai 07 + thứ Ba 08 cũng là lễ: nghỉ bù thứ Tư 09.
        self.write_own(2028, {"2028-02-06": "X", "2028-02-07": "Y", "2028-02-08": "Z"})
        self.assertEqual(holidays.off_reason(self.cfg, "2028-02-09"), "nghỉ bù X")

    def test_next_holiday_and_source(self):
        self.assertEqual(holidays.next_holiday(self.cfg, "2026-11-02"), (dt.date(2026, 11, 8), "Deepavali"))
        self.assertIn("có sẵn", holidays.source_label(self.cfg, 2026))
        self.write_own(2027, {"2027-01-01": "NY"})
        self.assertEqual(holidays.source_label(self.cfg, 2027), "trang MOM")
        cfg = make_cfg(self.tmp, timesheet_data_dir="")
        self.assertIn("CHƯA CÓ", holidays.source_label(cfg, 2033))


class RealMomLayoutTest(unittest.TestCase):
    """Bố cục trang MOM thật (xem 14/10/2026): tab năm, <div id="Year-2026">, cột Date | Day | Holiday image |
    Holiday name, 2 ngày trong một ô, ô tên lặp lại ngày + ghi chú nghỉ bù, dòng "Add 2025 public holidays..." sau bảng."""

    def test_real_layout(self):
        from tests.fixtures.mom_page import page
        for headings in (False, True):
            years, rejected = holidays.parse_mom(page(headings))
            self.assertEqual(rejected, {})
            self.assertEqual({y: len(d) for y, d in years.items()}, {2025: 12, 2026: 11, 2027: 11})
            self.assertEqual(years[2026], holidays.BUILTIN[2026], "khớp bảng 2026 có sẵn")
            self.assertEqual(years[2027]["2027-02-07"], "Chinese New Year")
            self.assertNotIn("2026-06-01", years[2026], "ngày trong ghi chú không phải ngày lễ gốc")
