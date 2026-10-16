"""Dọn dẹp hằng ngày: sao lưu DB nén zip xoay vòng, cắt log launcher/launchd, checkpoint WAL, .pyc mồ côi, xoá mẫu cũ (giữ daily_stats), ai_cache, báo cáo, audit.log, VACUUM."""
import datetime as dt
import glob
import os
import sqlite3
import sys
import threading
import time
import types
import zipfile
from unittest import mock

from focus import housekeeping, logs
from focus.storage import db_path, open_db
from tests.helpers import TempCase, insert_run, make_cfg


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def fake_dt(today):
    class FakeDate(dt.date):
        @classmethod
        def today(cls):
            return today
    return types.SimpleNamespace(date=FakeDate, datetime=dt.datetime, timedelta=dt.timedelta, time=dt.time)


class HousekeepingTest(TempCase):
    def setUp(self):
        super().setUp()
        self.db = open_db(db_path(self.cfg))
        self.addCleanup(self.db.close)
        self.today = dt.date.today()

    def backups(self):
        return sorted(os.path.basename(p) for p in glob.glob(os.path.join(self.cfg["data_dir"], "backup", "*")))

    def test_backup_zipped_and_rotates(self):
        cfg = make_cfg(self.tmp, keep_db_backups=3)
        folder = os.path.join(cfg["data_dir"], "backup")
        os.makedirs(folder)
        for d in range(1, 7):  # bản .db cũ (trước khi nén) và .zip trộn lẫn: xoay vòng tính chung
            ext = "db.zip" if d % 2 else "db"
            open(os.path.join(folder, f"focus-2020-01-0{d}.{ext}"), "w").close()
        open(os.path.join(folder, "ghi-chu-cua-toi.txt"), "w").close()  # file lạ: không đụng
        insert_run(self.db, self.today, "09:00", 5)
        out = housekeeping.backup_db(cfg, self.db)
        names = self.backups()
        self.assertEqual(names, ["focus-2020-01-05.db.zip", "focus-2020-01-06.db", f"focus-{self.today}.db.zip",
                                 "ghi-chu-cua-toi.txt"])
        self.assertIn("giữ 3 bản", out)
        # giải nén ra đọc được, đúng dữ liệu (cách khôi phục ghi trong docstring)
        with zipfile.ZipFile(os.path.join(folder, f"focus-{self.today}.db.zip")) as z:
            self.assertEqual(z.namelist(), ["focus.db"])
            self.assertEqual(z.getinfo("focus.db").compress_type, zipfile.ZIP_DEFLATED)
            z.extract("focus.db", os.path.join(self.tmp, "restore"))
        copy = sqlite3.connect(os.path.join(self.tmp, "restore", "focus.db"))
        self.assertEqual(copy.execute("SELECT COUNT(*) FROM samples").fetchone()[0], 60)
        copy.close()
        # chạy lại cùng ngày: ghi đè bản hôm nay, không sinh thêm, không để file tạm
        housekeeping.backup_db(cfg, self.db)
        self.assertEqual(len(self.backups()), 4)
        self.assertFalse(any(n.endswith(".tmp") for n in self.backups()))

    def test_backup_same_day_db_and_zip_keeps_zip(self):
        folder = os.path.join(self.cfg["data_dir"], "backup")
        os.makedirs(folder)
        open(os.path.join(folder, f"focus-{self.today}.db"), "w").close()
        housekeeping.backup_db(self.cfg, self.db)
        self.assertEqual(self.backups(), [f"focus-{self.today}.db.zip"])

    def test_backup_failure_leaves_no_temp(self):
        folder = os.path.join(self.cfg["data_dir"], "backup")
        with mock.patch.object(housekeeping.zipfile, "ZipFile", side_effect=OSError("đầy đĩa")):
            with self.assertRaises(OSError):
                housekeeping.backup_db(self.cfg, self.db)
        self.assertEqual(os.listdir(folder), [])

    def test_prune_samples_keeps_daily_stats(self):
        cfg = make_cfg(self.tmp, keep_samples_days=10)
        old = self.today - dt.timedelta(days=30)
        recent = self.today - dt.timedelta(days=2)
        insert_run(self.db, old, "09:00", 60)
        insert_run(self.db, recent, "09:00", 30)
        n = housekeeping.prune_samples(cfg, self.db)
        self.assertEqual(n, 720)
        cutoff = dt.datetime.combine(self.today - dt.timedelta(days=10), dt.time()).timestamp()
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM samples WHERE ts < ?", (cutoff,)).fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM samples").fetchone()[0], 360)
        row = self.db.execute("SELECT data FROM daily_stats WHERE day=?", (old.isoformat(),)).fetchone()
        self.assertIsNotNone(row)  # số liệu ngày cũ được chốt trước khi xoá mẫu thô
        self.assertIn('"deep"', row[0])
        self.assertEqual(housekeeping.prune_samples(cfg, self.db), 0)  # không còn gì để xoá
        self.assertIsNotNone(self.db.execute("SELECT 1 FROM daily_stats WHERE day=?", (old.isoformat(),)).fetchone())

    def test_prune_tables(self):
        now = time.time()
        with self.db:
            self.db.executemany("INSERT INTO ai_cache VALUES (?,?,?)",
                                [("cũ", now - 61 * 86400, "x"), ("mới", now - 59 * 86400, "y")])
            self.db.executemany("INSERT INTO quotes VALUES (?,?,?)",
                                [(now - 91 * 86400, "bible", "a"), (now - 89 * 86400, "bible", "b")])
            self.db.executemany("INSERT INTO sent_log VALUES (?,?,?)",
                                [("2020-01-01", "k", now - 31 * 86400), ("2020-01-02", "k", now - 29 * 86400)])
        out = housekeeping.prune_tables(self.db)
        self.assertEqual(out, {"ai_cache": 1, "quotes": 1, "sent_log": 1})
        self.assertEqual([r[0] for r in self.db.execute("SELECT key FROM ai_cache")], ["mới"])
        self.assertEqual([r[0] for r in self.db.execute("SELECT text FROM quotes")], ["b"])

    def test_prune_reports(self):
        cfg = make_cfg(self.tmp, keep_reports_days=5)
        now = time.time()
        for name, age in (("old.html", 6), ("new.html", 4), ("old.txt", 100)):
            p = os.path.join(cfg["report_dir"], name)
            open(p, "w").close()
            os.utime(p, (now - age * 86400, now - age * 86400))
        pattern = os.path.join(cfg["report_dir"], "*.html")
        self.assertEqual(housekeeping.prune_files(pattern, cfg["keep_reports_days"]), 1)
        self.assertEqual(sorted(os.listdir(cfg["report_dir"])), ["new.html", "old.txt"])

    def test_trim_audit(self):
        path = os.path.join(self.cfg["data_dir"], "audit.log")
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(f"dòng {i}\n" for i in range(30))
        self.assertEqual(housekeeping.trim_audit(self.cfg, max_lines=40, keep=10), 0)  # chưa quá ngưỡng
        self.assertEqual(housekeeping.trim_audit(self.cfg, max_lines=20, keep=10), 20)
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        self.assertEqual(lines, [f"dòng {i}" for i in range(20, 30)])
        self.assertFalse(os.path.exists(path + ".tmp"))
        os.remove(path)
        self.assertEqual(housekeeping.trim_audit(self.cfg), 0)  # không có file: không lỗi

    def test_trim_audit_does_not_lose_concurrent_lines(self):
        path = os.path.join(self.cfg["data_dir"], "audit.log")
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(f"dòng {i}\n" for i in range(30))
        real_replace = os.replace
        writers = []

        def replace(src, dst):
            # Đúng lúc cắt file đã đọc xong và sắp thay file: một thread khác ghi audit.
            t = threading.Thread(target=logs.audit, args=("DONG_MOI", "x"))
            t.start()
            t.join(0.2)
            writers.append(t)
            real_replace(src, dst)
        with mock.patch.object(housekeeping.os, "replace", replace):
            self.assertEqual(housekeeping.trim_audit(self.cfg, 20, 10), 20)
        for t in writers:
            t.join(5)
        with open(path, encoding="utf-8") as f:
            self.assertIn("DONG_MOI", f.read())  # dòng ghi lúc đang cắt không bị mất

    def test_run_once_per_day(self):
        r1 = housekeeping.run(self.cfg)
        self.assertNotIn("skipped", r1)
        for key in ("db_backup", "samples", "tables", "reports", "audit_log", "holiday_caches", "tmp_files",
                    "text_logs", "bytecode", "wal", "freed_bytes"):
            self.assertIn(key, r1)
            self.assertFalse(str(r1[key]).startswith("lỗi"), (key, r1[key]))
        with open(os.path.join(self.cfg["data_dir"], "housekeeping_last_run.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), self.today.isoformat())
        self.assertEqual(housekeeping.run(self.cfg), {"skipped": "đã dọn hôm nay"})
        self.assertNotIn("skipped", housekeeping.run(self.cfg, force=True))
        self.assertTrue(any("HOUSEKEEPING" in l for l in self.audit_lines()))

    def test_step_error_does_not_stop_others(self):
        with mock.patch.object(housekeeping, "prune_tables", side_effect=RuntimeError("hỏng")):
            r = housekeeping.run(self.cfg)
        self.assertEqual(r["tables"], "lỗi: hỏng")
        self.assertIn("giữ", r["db_backup"])

    def test_tmp_and_old_holiday_files_pruned(self):
        old = time.time() - 3 * 86400
        stale = os.path.join(self.cfg["data_dir"], "ai_model.json.123.tmp")
        open(stale, "w").close()
        os.utime(stale, (old, old))
        fresh = os.path.join(self.cfg["data_dir"], "fresh.tmp")
        open(fresh, "w").close()
        y = self.today.year
        for year in (y - 3, y - 2, y, y + 1):
            open(os.path.join(self.cfg["data_dir"], f"holidays_{year}.json"), "w").close()
        r = housekeeping.run(self.cfg)
        self.assertEqual(r["tmp_files"], 1)
        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.exists(fresh))  # file tạm mới (đang ghi dở) không bị xoá
        self.assertEqual(r["holiday_caches"], [f"holidays_{y - 3}.json"])

    def test_vacuum_on_first_of_month_with_open_wal_db(self):
        other = open_db(db_path(self.cfg))  # tracker vẫn đang mở DB
        self.addCleanup(other.close)
        insert_run(other, self.today, "09:00", 10)
        first = dt.date(self.today.year, self.today.month, 1)
        with mock.patch.object(housekeeping, "dt", fake_dt(first)):
            r = housekeeping.run(self.cfg)
        self.assertEqual(r["vacuum"], "ok")
        self.assertEqual(other.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        insert_run(other, self.today, "10:00", 1)  # vẫn ghi tiếp được
        self.assertEqual(other.execute("SELECT COUNT(*) FROM samples").fetchone()[0], 132)
        self.assertEqual(other.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertIn(f"focus-{first}.db.zip", self.backups())

    def test_no_vacuum_other_days(self):
        day = dt.date(self.today.year, self.today.month, 15)
        with mock.patch.object(housekeeping, "dt", fake_dt(day)):
            r = housekeeping.run(self.cfg)
        self.assertNotIn("vacuum", r)

    def test_vacuum_mid_month_when_many_free_pages(self):
        day = dt.date(self.today.year, self.today.month, 15)
        insert_run(self.db, self.today - dt.timedelta(days=200), "08:00", 600)  # mẫu rất cũ, sẽ bị xoá
        with mock.patch.object(housekeeping, "dt", fake_dt(day)):
            r = housekeeping.run(self.cfg)
        self.assertEqual(r["vacuum"], "ok")  # xoá xong trang trống > 25% -> VACUUM ngay
        self.assertLess(housekeeping._free_ratio(self.db), 0.25)

    def test_wal_checkpoint_truncates(self):
        insert_run(self.db, self.today, "09:00", 120)
        wal = db_path(self.cfg) + "-wal"
        self.assertGreater(os.path.getsize(wal), 0)
        out = housekeeping.checkpoint_wal(self.db)
        self.assertEqual(os.path.getsize(wal), 0)
        self.assertTrue(out.endswith("-> 0 B"), out)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM samples").fetchone()[0], 1440)

    def write_log(self, name, data, age_days=0):
        folder = os.path.join(self.cfg["data_dir"], "logs")
        os.makedirs(folder, exist_ok=True)
        p = os.path.join(folder, name)
        with open(p, "wb") as f:
            f.write(data)
        t = time.time() - age_days * 86400
        os.utime(p, (t, t))
        return p

    def test_trim_utf16_launcher_log_keeps_encoding(self):
        lines = "".join(f"14/10/2026 08:{i % 60:02d}  Khong tim thay Python ({i})\r\n" for i in range(30000))
        p = self.write_log("launcher-error.txt", b"\xff\xfe" + lines.encode("utf-16-le"))
        r = housekeeping.trim_text_logs(self.cfg)
        self.assertEqual(r["trimmed"], ["launcher-error.txt"])
        raw = read_bytes(p)
        self.assertTrue(raw.startswith(b"\xff\xfe"))
        self.assertLessEqual(len(raw), 200 * 1024 + 2)
        self.assertGreater(len(raw), 150 * 1024)
        text = raw[2:].decode("utf-16-le")  # giải mã sạch: không vỡ ký tự
        self.assertTrue(text.startswith("14/10/2026"))  # bắt đầu từ đầu dòng
        self.assertTrue(text.endswith("(29999)\r\n"))  # giữ phần mới nhất
        # VBScript ghi tiếp (append UTF-16 không BOM) vẫn đọc được
        with open(p, "ab") as f:
            f.write("dòng mới\r\n".encode("utf-16-le"))
        self.assertTrue(read_bytes(p)[2:].decode("utf-16-le").endswith("dòng mới\r\n"))

    def test_trim_utf8_log_in_place_and_open_append_writer_continues(self):
        body = "".join(f"lỗi số {i} ở đây\n" for i in range(100000)).encode("utf-8")
        p = self.write_log("launchd.err.log", body)
        writer = open(p, "ab")  # launchd giữ file mở kiểu append suốt lúc chạy
        self.addCleanup(writer.close)
        r = housekeeping.trim_text_logs(self.cfg)
        self.assertEqual(r["trimmed"], ["launchd.err.log"])
        writer.write("sau khi cắt\n".encode("utf-8"))
        writer.flush()
        text = read_bytes(p).decode("utf-8")  # không vỡ ký tự nhiều byte
        self.assertTrue(text.startswith("lỗi số "))
        self.assertTrue(text.endswith("lỗi số 99999 ở đây\nsau khi cắt\n"))
        self.assertLess(len(text.encode()), 210 * 1024)

    def test_text_logs_delete_old_and_keep_focus_log(self):
        big = b"x" * (2 * 1024 * 1024)
        self.write_log("focus.log", big, age_days=90)  # focus.log do log_setup tự xoay: không đụng
        self.write_log("focus.log.2026-01-01", b"cu", age_days=90)
        self.write_log("config-error.txt", b"loi cu", age_days=31)
        self.write_log("launchd.out.log", b"", age_days=61)
        self.write_log("launcher-error.txt", b"\xff\xfe", age_days=59)
        self.write_log("anh.png", b"x", age_days=100)  # không phải .txt/.log: không xoá
        r = housekeeping.trim_text_logs(self.cfg)
        self.assertEqual(sorted(r["deleted"]), ["config-error.txt", "launchd.out.log"])
        self.assertEqual(r["trimmed"], [])
        left = sorted(os.listdir(os.path.join(self.cfg["data_dir"], "logs")))
        self.assertEqual(left, ["anh.png", "focus.log", "focus.log.2026-01-01", "launcher-error.txt"])
        self.assertEqual(os.path.getsize(os.path.join(self.cfg["data_dir"], "logs", "focus.log")), len(big))
        self.write_log("config-error.txt", b"moi", age_days=5)
        self.assertEqual(housekeeping.trim_text_logs(self.cfg)["deleted"], [])

    def test_prune_bytecode_only_orphans_inside_app(self):
        root = os.path.join(self.tmp, "app")
        tag = sys.implementation.cache_tag
        for pkg in ("focus", "tests", "khac"):
            os.makedirs(os.path.join(root, pkg, "__pycache__"))
            for mod in ("__init__", "tracker", "dialogs"):
                if mod != "dialogs":
                    open(os.path.join(root, pkg, mod + ".py"), "w").close()
                open(os.path.join(root, pkg, "__pycache__", f"{mod}.{tag}.pyc"), "w").close()
        old = time.time() - 40 * 86400
        for name, age in (("tracker.cpython-30.pyc", old), ("__init__.cpython-31.pyc", time.time())):
            p = os.path.join(root, "focus", "__pycache__", name)
            open(p, "w").close()
            os.utime(p, (age, age))
        removed = housekeeping.prune_bytecode(root)
        self.assertEqual(sorted(removed), [f"focus/dialogs.{tag}.pyc", "focus/tracker.cpython-30.pyc",
                                           f"tests/dialogs.{tag}.pyc"])
        self.assertTrue(os.path.exists(os.path.join(root, "khac", "__pycache__", f"dialogs.{tag}.pyc")))
        self.assertTrue(os.path.exists(os.path.join(root, "focus", "__pycache__", "__init__.cpython-31.pyc")))
        self.assertTrue(os.path.exists(os.path.join(root, "focus", "__pycache__", f"tracker.{tag}.pyc")))
        self.assertEqual(housekeeping.prune_bytecode(os.path.join(self.tmp, "khong-co")), [])
        self.assertEqual(housekeeping.APP_ROOT, os.path.dirname(os.path.dirname(housekeeping.__file__)))

    def test_prune_tmp_in_backup_logs_and_reports(self):
        old = time.time() - 2 * 86400
        data, rep = self.cfg["data_dir"], self.cfg["report_dir"]
        paths = {
            os.path.join(data, "backup", "focus-2026-01-01.db.zip.tmp"): True,
            os.path.join(data, "logs", "x.tmp"): True,
            os.path.join(rep, "focus-2026-01-01.html.tmp"): True,
            os.path.join(rep, "cua-nguoi-khac.tmp"): False,  # report_dir có thể là thư mục chung
            os.path.join(data, "khac", "y.tmp"): False,
        }
        for p in paths:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").close()
            os.utime(p, (old, old))
        fresh = os.path.join(data, "backup", "dang-ghi.tmp")
        open(fresh, "w").close()
        self.assertEqual(housekeeping.prune_tmp(self.cfg), 3)
        for p, gone in paths.items():
            self.assertEqual(os.path.exists(p), not gone, p)
        self.assertTrue(os.path.exists(fresh))

    def test_reports_only_own_html(self):
        cfg = make_cfg(self.tmp, keep_reports_days=5)
        old = time.time() - 10 * 86400
        for name in ("focus-2026-01-01.html", "trang-cua-toi.html"):
            p = os.path.join(cfg["report_dir"], name)
            open(p, "w").close()
            os.utime(p, (old, old))
        r = housekeeping.run(cfg)
        self.assertEqual(r["reports"], 1)
        self.assertEqual(os.listdir(cfg["report_dir"]), ["trang-cua-toi.html"])

    def test_data_usage_and_freed_bytes(self):
        data = self.cfg["data_dir"]
        insert_run(self.db, self.today, "09:00", 10)
        os.makedirs(os.path.join(data, "backup"))
        with open(os.path.join(data, "backup", "focus-2020-01-01.db"), "wb") as f:
            f.write(b"b" * 5000)
        with open(os.path.join(self.cfg["report_dir"], "focus-2020-01-01.html"), "wb") as f:
            f.write(b"r" * 3000)
        with open(os.path.join(data, "ai_model.json"), "wb") as f:
            f.write(b"o" * 700)
        u = housekeeping.data_usage(self.cfg)
        self.assertEqual(set(u), {"total_bytes", "db_bytes", "backups_bytes", "reports_bytes", "logs_bytes",
                                  "other_bytes"})
        self.assertEqual(u["backups_bytes"], 5000)
        self.assertEqual(u["reports_bytes"], 3000)
        self.assertGreater(u["db_bytes"], 0)
        self.assertGreaterEqual(u["other_bytes"], 700)
        self.assertEqual(u["total_bytes"], u["db_bytes"] + u["backups_bytes"] + u["reports_bytes"] + u["logs_bytes"]
                         + u["other_bytes"])
        # log to quá: dọn xong freed_bytes > 0
        self.write_log("launcher-error.txt", b"\xff\xfe" + ("a\r\n" * 400000).encode("utf-16-le"))
        r = housekeeping.run(self.cfg)
        self.assertGreater(r["freed_bytes"], 1024 * 1024)
        self.assertIn("usage_after", r)

    def test_fmt_size(self):
        self.assertEqual(housekeeping.fmt_size(0), "0 B")
        self.assertEqual(housekeeping.fmt_size(999), "999 B")
        self.assertEqual(housekeeping.fmt_size(1536), "1.5 KB")
        self.assertEqual(housekeeping.fmt_size(12.3 * 1024 * 1024), "12.3 MB")
        self.assertEqual(housekeeping.fmt_size(3 * 1024 ** 3), "3.0 GB")
        self.assertEqual(housekeeping.fmt_size(-2048), "-2.0 KB")
        self.assertEqual(housekeeping.fmt_size(None), "0 B")

    def test_each_new_step_isolated(self):
        for fn in ("trim_text_logs", "prune_bytecode", "prune_tmp", "checkpoint_wal", "data_usage"):
            with mock.patch.object(housekeeping, fn, side_effect=RuntimeError("hỏng")):
                r = housekeeping.run(self.cfg, force=True)
            self.assertIn("giữ", r["db_backup"], fn)
            self.assertIn("seconds", r)
