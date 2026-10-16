"""Hàng đợi chạy nền cho mọi việc cần mạng (gửi Telegram, gọi AI).

Vòng lấy mẫu chỉ bỏ việc vào hàng đợi rồi đi tiếp, nên mạng chậm, AI nghẽn hay Telegram bị chặn
cũng không làm trễ hay mất mẫu nào.
"""
import queue
import threading

from .logs import get_logger

log = get_logger()


class Notifier:
    def __init__(self, maxsize=100, on_error=None):
        self.on_error = on_error  # on_error(label, exc): báo người dùng câu dễ hiểu (bot.notify_job_error)
        self.q = queue.Queue(maxsize=maxsize)
        self.thread = threading.Thread(target=self._run, daemon=True, name="notifier")
        self.thread.start()

    def submit(self, label, fn, *args):
        try:
            self.q.put_nowait((label, fn, args))
        except queue.Full:  # mạng chết lâu: bỏ tin cũ hơn là ăn RAM
            log.warning("Hàng đợi gửi đầy, bỏ: %s", label)

    def _run(self):
        while True:
            label, fn, args = self.q.get()
            try:
                fn(*args)
            except Exception as e:
                log.error("Việc nền '%s' lỗi: %s", label, e, exc_info=True)
                if self.on_error:
                    try:
                        self.on_error(label, e)
                    except Exception:
                        log.warning("Không báo được lỗi việc nền '%s'", label, exc_info=True)
            finally:
                self.q.task_done()

    def drain(self, timeout=30):
        """Đợi các việc đang chờ chạy xong (dùng khi tắt tracker)."""
        done = threading.Event()
        threading.Thread(target=lambda: (self.q.join(), done.set()), daemon=True).start()
        return done.wait(timeout)
