"""Supervised automatic market refresh, analysis, streaming, and alert checks."""
import asyncio
import threading
from datetime import datetime, timezone

from config import (
    AUTO_ALERT_CHECK_SECONDS, AUTO_DATA_REFRESH_SECONDS, AUTO_DAILY_REFRESH_DAYS,
    AUTO_MINUTE_REFRESH_DAYS, AUTO_MONITORING_ENABLED, SYMBOLS,
)
from database.connection import get_connection

ADVISORY_LOCK_ID = 735190241
OWNER_RETRY_SECONDS = 30
STREAM_RETRY_MIN_SECONDS = 2
STREAM_RETRY_MAX_SECONDS = 60
REFRESH_RETRY_MIN_SECONDS = 30
REFRESH_RETRY_MAX_SECONDS = 300


class MarketAutomation:
    """Keep one API worker responsible for automatic market monitoring.

    Ownership acquisition, historical ingestion, the Alpaca WebSocket, and
    alert checks all recover from transient failures without an API restart.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._state = {
            "enabled": AUTO_MONITORING_ENABLED, "owner": False,
            "stream": "starting", "last_alert_check": None,
            "last_data_refresh": None, "last_analysis": None,
            "analysis_unchanged": False, "last_error": None,
        }
        self._tasks = []
        self._owner_task = None
        self._processor = None
        self._stream_thread = None
        self._lock_connection = None
        self._daily_snapshot = None
        self._stopping = threading.Event()

    def status(self):
        with self._lock:
            return dict(self._state)

    def _set(self, **values):
        with self._lock:
            self._state.update(values)

    async def start(self):
        self._stopping.clear()
        if not AUTO_MONITORING_ENABLED:
            self._set(stream="disabled")
            return
        # The API should remain available while Postgres starts or recovers.
        self._owner_task = asyncio.create_task(self._ownership_loop(), name="automation-owner")

    def _try_acquire_owner(self):
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s)", (ADVISORY_LOCK_ID,))
                owns_lock = bool(cursor.fetchone()[0])
            if owns_lock:
                return connection
        except Exception:
            connection.close()
            raise
        connection.close()
        return None

    @staticmethod
    def _release_owner(connection):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (ADVISORY_LOCK_ID,))
        except Exception:
            pass
        connection.close()

    async def _ownership_loop(self):
        while not self._stopping.is_set():
            try:
                acquisition = asyncio.create_task(asyncio.to_thread(self._try_acquire_owner))
                try:
                    connection = await asyncio.shield(acquisition)
                except asyncio.CancelledError:
                    # The worker thread cannot be cancelled; collect its result
                    # so a lock acquired during shutdown is not orphaned.
                    connection = await acquisition
                    if connection is not None:
                        await asyncio.to_thread(self._release_owner, connection)
                    raise
                if connection is not None:
                    self._lock_connection = connection
                    self._set(owner=True, stream="connecting", last_error=None)
                    # Load shared Alpaca/pipeline modules before worker threads
                    # start. Concurrent first imports from the refresh and
                    # stream threads can deadlock Python's import lock.
                    from alpaca.data.timeframe import TimeFrame  # noqa: F401
                    from alerts.alert_checker import check_all_active_alerts  # noqa: F401
                    from analysis.pipeline import run_historical_analysis  # noqa: F401
                    from ingestion.price_ingestion import insert_price_data  # noqa: F401
                    from realtime.stream_processor import RealtimeProcessor  # noqa: F401
                    self._tasks = [
                        asyncio.create_task(self._refresh_loop(), name="market-data-refresh"),
                        asyncio.create_task(self._alert_loop(), name="price-alert-checks"),
                    ]
                    self._start_stream()
                    return
                self._set(owner=False, stream="managed_by_another_api_worker")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._lock_connection is not None:
                    await asyncio.to_thread(self._release_owner, self._lock_connection)
                    self._lock_connection = None
                self._set(owner=False, stream="database_unavailable", last_error=f"Automation startup: {str(exc)[:250]}")
            await asyncio.sleep(OWNER_RETRY_SECONDS)

    def _start_stream(self):
        self._stream_thread = threading.Thread(
            target=self._stream_supervisor, name="alpaca-market-stream", daemon=True
        )
        self._stream_thread.start()

    def _stream_supervisor(self):
        delay = STREAM_RETRY_MIN_SECONDS
        while not self._stopping.is_set():
            processor = None
            monitor_stop = None
            monitor = None
            try:
                from realtime.stream_processor import RealtimeProcessor
                processor = RealtimeProcessor()
                self._processor = processor
                self._set(stream="connecting")
                monitor_stop = threading.Event()
                monitor = threading.Thread(
                    target=self._watch_stream_state,
                    args=(processor, monitor_stop),
                    name="alpaca-stream-status",
                    daemon=True,
                )
                monitor.start()
                processor.run()
                if self._stopping.is_set():
                    break
                self._set(stream="disconnected", last_error="Market-data stream ended; reconnecting automatically.")
            except Exception as exc:
                if not self._stopping.is_set():
                    self._set(stream="retrying", last_error=f"Market-data stream: {str(exc)[:220]}")
            finally:
                if monitor_stop is not None:
                    monitor_stop.set()
                if monitor is not None:
                    if monitor.is_alive():
                        monitor.join(1)
                if processor is not None:
                    try:
                        processor.stream.stop()
                    except Exception:
                        pass
                if self._processor is processor:
                    self._processor = None
            if self._stopping.wait(delay):
                break
            delay = min(delay * 2, STREAM_RETRY_MAX_SECONDS)
        self._set(stream="stopped")

    def _watch_stream_state(self, processor, stop_event):
        """Reflect Alpaca's authenticated/running state while its run call blocks."""
        was_running = False
        while not stop_event.wait(0.5) and not self._stopping.is_set():
            is_running = bool(getattr(processor.stream, "_running", False))
            if is_running and not was_running:
                self._set(stream="running", last_error=None)
            elif was_running and not is_running:
                self._set(stream="reconnecting")
            was_running = is_running

    async def _refresh_loop(self):
        retry_delay = REFRESH_RETRY_MIN_SECONDS
        while not self._stopping.is_set():
            try:
                analyzed = await asyncio.to_thread(self._refresh_and_analyze)
                self._set(last_data_refresh=datetime.now(timezone.utc).isoformat(), last_error=None)
                if analyzed:
                    self._set(last_analysis=datetime.now(timezone.utc).isoformat(), analysis_unchanged=False)
                else:
                    self._set(analysis_unchanged=True)
                retry_delay = REFRESH_RETRY_MIN_SECONDS
                delay = AUTO_DATA_REFRESH_SECONDS
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._set(last_error=f"Automatic refresh: {str(exc)[:250]}")
                delay = retry_delay
                retry_delay = min(retry_delay * 2, REFRESH_RETRY_MAX_SECONDS)
            await asyncio.sleep(delay)

    def _refresh_and_analyze(self):
        from alpaca.data.timeframe import TimeFrame
        from analysis.pipeline import run_historical_analysis
        from ingestion.price_ingestion import insert_price_data

        insert_price_data(TimeFrame.Day, AUTO_DAILY_REFRESH_DAYS)
        insert_price_data(TimeFrame.Minute, AUTO_MINUTE_REFRESH_DAYS)
        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT s.symbol, MAX(pb.timestamp)
                       FROM security s LEFT JOIN price_bar pb
                         ON pb.security_id = s.security_id AND pb.timeframe = 'day'
                       WHERE s.symbol = ANY(%s) GROUP BY s.symbol ORDER BY s.symbol""",
                    (SYMBOLS,),
                )
                snapshot = tuple(cursor.fetchall())
        if snapshot != self._daily_snapshot:
            run_historical_analysis(SYMBOLS)
            self._daily_snapshot = snapshot
            return True
        return False

    async def _alert_loop(self):
        while not self._stopping.is_set():
            try:
                from alerts.alert_checker import check_all_active_alerts
                await asyncio.to_thread(check_all_active_alerts)
                self._set(last_alert_check=datetime.now(timezone.utc).isoformat())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._set(last_error=f"Automatic alert check: {str(exc)[:250]}")
            await asyncio.sleep(AUTO_ALERT_CHECK_SECONDS)

    async def stop(self):
        self._stopping.set()
        if self._owner_task:
            self._owner_task.cancel()
            await asyncio.gather(self._owner_task, return_exceptions=True)
            self._owner_task = None
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        processor = self._processor
        if processor is not None:
            try:
                processor.stream.stop()
            except Exception:
                pass
        if self._stream_thread and self._stream_thread.is_alive():
            await asyncio.to_thread(self._stream_thread.join, 5)
        self._stream_thread = None
        if self._lock_connection is not None:
            await asyncio.to_thread(self._release_owner, self._lock_connection)
            self._lock_connection = None
        self._set(owner=False, stream="stopped")
