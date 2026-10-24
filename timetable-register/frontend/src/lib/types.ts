export type Role = "super_admin" | "institution_admin" | "department_admin" | "teacher" | "student";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  institution_id: number | null;
  department_id: number | null;
  teacher_id: number | null;
  class_id: number | null;
  is_active: boolean;
}

export interface Institution {
  id: number;
  name: string;
  code: string;
  kind: "university" | "college" | "school";
  address: string | null;
  default_schedule_id: number | null;
  soft_weights: Record<string, number>;
}

export interface Window {
  day: number;
  start: string;
  end: string;
}

export interface Slot {
  key: string;
  kind: "period" | "break" | "lunch";
  start: number;
  end: number;
  time: string;
  label: string;
}

export interface Entry {
  id: number;
  assignment_id: number | null;
  day: number;
  day_name: string;
  start: number;
  end: number;
  time: string;
  period_index: number;
  length: number;
  locked: boolean;
  class_id: number;
  class_name: string;
  department_id: number | null;
  subject_id: number;
  subject_name: string;
  subject_code: string;
  subject_kind: string;
  color: string;
  teacher_id: number;
  teacher_name: string;
  room_id: number;
  room_name: string;
  room_type: string;
  conflicts: string[];
}

export interface View {
  kind: "grid" | "master";
  view: string;
  ref_id: number | null;
  title: string;
  subtitle: string;
  days: { day: number; name: string; short: string }[];
  slots: Slot[];
  day_slots: Record<string, string[]>;
  rows?: {
    id: number;
    name: string;
    department: string;
    periods: Record<string, [number, number][]>;
    breaks: Record<string, [number, number, string][]>;
  }[];
  entries: Entry[];
}

export interface Suggestion {
  day: number;
  period_index: number;
  start: number;
  end: number;
  room_id: number;
  room_name: string;
  label: string;
}

export interface Conflict {
  type: string;
  severity: "major" | "minor";
  message: string;
  entry_ids: number[];
  day: number | null;
  day_name: string | null;
  time: string | null;
  suggestions: Suggestion[];
}

export interface Timetable {
  id: number;
  institution_id: number;
  department_id: number | null;
  name: string;
  term: string | null;
  status: "draft" | "published" | "archived";
  share_token: string | null;
  share_url?: string;
  generation: any;
  conflict_summary: { total?: number; major?: number; minor?: number; by_type?: Record<string, number> };
  created_at: string;
  updated_at: string;
  published_at: string | null;
  entry_count?: number | null;
}

export interface Option {
  id: number;
  name: string;
  room_type?: string;
  kind?: string;
}

export interface TimetableDetail extends Timetable {
  options: {
    classes: Option[];
    teachers: Option[];
    rooms: Option[];
    labs: Option[];
    departments: Option[];
    schools: Option[];
  };
  can_edit: boolean;
  scope: string;
}

export const DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
export const DAY_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export const ROLE_LABEL: Record<Role, string> = {
  super_admin: "Super admin",
  institution_admin: "Institution admin",
  department_admin: "Department admin",
  teacher: "Teacher",
  student: "Student",
};

export const CONFLICT_LABEL: Record<string, string> = {
  teacher_conflict: "Teacher double-booked",
  class_conflict: "Class has two subjects",
  room_conflict: "Room double-booked",
  teacher_availability: "Teacher unavailable",
  class_availability: "Class unavailable",
  room_availability: "Room unavailable",
  room_type_mismatch: "Wrong room type",
  room_capacity: "Room too small",
  invalid_slot: "Off the period grid",
  lecture_count: "Weekly lectures don't match",
  teacher_daily_limit: "Teacher over daily limit",
  teacher_weekly_limit: "Teacher over weekly limit",
};
