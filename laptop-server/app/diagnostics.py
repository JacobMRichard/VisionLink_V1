from dataclasses import dataclass

from app.util.session import Session
from app.util.event_log import EventLog
from app.util.recent_store import RecentStore, ExceptionsLog
from app.util.exporter import Exporter


@dataclass
class DiagnosticsBundle:
    session: Session
    events: EventLog
    timings: RecentStore
    metadata: RecentStore
    exceptions: ExceptionsLog
    exporter: Exporter


def make_diagnostics() -> DiagnosticsBundle:
    session = Session()
    events = EventLog(session.events_path, session.session_id)
    timings = RecentStore(session.recent_timings_path, "timings", window=50)
    metadata = RecentStore(session.recent_metadata_path, "metadata", window=20)
    exceptions = ExceptionsLog(session.exceptions_path)
    exporter = Exporter(session.folder)
    return DiagnosticsBundle(
        session=session,
        events=events,
        timings=timings,
        metadata=metadata,
        exceptions=exceptions,
        exporter=exporter,
    )
