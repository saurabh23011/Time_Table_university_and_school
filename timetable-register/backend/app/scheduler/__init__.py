from .conflicts import (  # noqa: F401
    AssignmentReq,
    Conflict,
    EntryView,
    ValidationContext,
    detect_conflicts,
    has_major,
    suggest_slots,
    summarize,
)
from .engine import SolveResult, Solver, generate  # noqa: F401
from .model import (  # noqa: F401
    ClassInfo,
    ExternalBusy,
    Placement,
    Problem,
    RoomInfo,
    SessionReq,
    SoftWeights,
    TeacherInfo,
    Window,
)
from .timegrid import DEFAULT_SCHEDULE, ScheduleConfigError, build_grid, grid_to_dict  # noqa: F401
