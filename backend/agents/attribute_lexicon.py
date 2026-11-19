"""General vocabulary used by the deterministic requirement extractor.

IMPORTANT: nothing in this module decides *which* entities, modules or pages an application has.
Those come only from the user's prompt (see ``spec_extraction``). This lexicon is general English /
business vocabulary used to:

* suggest typical attributes for an entity the prompt asked for but did not describe
  (e.g. a "vehicle" usually has a plate number), and typical relations between two entities that
  the prompt *both* requested;
* map a department/activity noun the user wrote to the record it manages
  (e.g. "billing" -> invoices, "pharmacy" -> medicines);
* recognise attribute words (dates, amounts, quantities, statuses) and generic app features
  (search, dashboard, reports) so they are not mistaken for data entities.

Unknown nouns are fully supported: they become entities with attributes inferred from their
grammar (event-like nouns get dates/statuses, other nouns get a name) and from the prompt itself.
"""

from typing import Dict, List, Tuple

# ----------------------------------------------------------------------------------------------
# Typical attributes: noun (singular, snake) -> list of "name:type[:flags]"
# type: string|text|integer|float|decimal|boolean|date|datetime|time|email|enum(a|b)
# flags: req, uniq, search, min=N, max=N
# ----------------------------------------------------------------------------------------------
TYPICAL_ATTRIBUTES: Dict[str, List[str]] = {
    # people
    "patient": ["name:string:req,search", "date_of_birth:date", "gender:enum(male|female|other)", "phone:string", "address:text"],
    "doctor": ["name:string:req,search", "specialization:string:search", "phone:string", "email:email", "is_available:boolean"],
    "nurse": ["name:string:req,search", "phone:string", "shift:enum(morning|evening|night)"],
    "driver": ["name:string:req,search", "license_number:string:uniq,search", "phone:string", "license_expiry:date", "status:enum(available|on_trip|off_duty)"],
    "student": ["name:string:req,search", "email:email:search", "enrollment_number:string:uniq", "date_of_birth:date"],
    "teacher": ["name:string:req,search", "email:email:search", "subject:string:search", "phone:string"],
    "instructor": ["name:string:req,search", "email:email:search", "expertise:string"],
    "customer": ["name:string:req,search", "email:email:search", "phone:string", "address:text"],
    "employee": ["name:string:req,search", "email:email:search", "designation:string:search", "phone:string", "hire_date:date"],
    "staff": ["name:string:req,search", "designation:string:search", "phone:string", "email:email"],
    "member": ["name:string:req,search", "email:email:search", "phone:string", "joined_on:date"],
    "supplier": ["name:string:req,search", "email:email", "phone:string", "address:text"],
    "contact": ["name:string:req,search", "email:email:search", "phone:string", "company:string"],
    "team": ["name:string:req,uniq,search", "description:text"],
    "author": ["name:string:req,search", "biography:text"],
    "tenant": ["name:string:req,search", "email:email", "phone:string"],
    "owner": ["name:string:req,search", "email:email", "phone:string"],
    "beekeeper": ["name:string:req,search", "phone:string", "email:email"],
    # assets / catalogue things
    "vehicle": ["plate_number:string:req,uniq,search", "make:string:search", "model:string:search", "year:integer:min=1900", "status:enum(available|in_use|maintenance)"],
    "bed": ["bed_number:string:req,search", "ward:string:search", "status:enum(available|occupied|reserved|maintenance)"],
    "room": ["room_number:string:req,uniq,search", "room_type:string", "capacity:integer:min=1", "status:enum(available|occupied|maintenance)"],
    "product": ["name:string:req,search", "description:text:search", "price:decimal:req,min=0", "stock:integer:min=0", "image_url:string"],
    "medicine": ["name:string:req,search", "category:string:search", "quantity:integer:min=0", "price:decimal:min=0", "expiry_date:date"],
    "book": ["title:string:req,search", "isbn:string:uniq", "published_year:integer:min=0", "copies_available:integer:min=0"],
    "course": ["title:string:req,search", "code:string:uniq,search", "description:text", "credits:integer:min=0"],
    "lesson": ["title:string:req,search", "content:text", "lesson_date:date", "position:integer:min=0"],
    "project": ["name:string:req,search", "description:text", "start_date:date", "end_date:date", "status:enum(planned|active|on_hold|completed)"],
    "category": ["name:string:req,uniq,search", "description:text"],
    "department": ["name:string:req,uniq,search", "description:text", "location:string"],
    "hive": ["name:string:req,uniq,search", "location:string:search", "installed_on:date", "status:enum(active|weak|dead)"],
    "queen": ["name:string:search", "marking_color:string", "introduced_on:date", "status:enum(active|replaced|missing)"],
    "equipment": ["name:string:req,search", "serial_number:string:uniq", "status:enum(available|in_use|maintenance)"],
    "property": ["title:string:req,search", "address:string:search", "price:decimal:min=0", "status:enum(available|let|sold)"],
    "menu_item": ["name:string:req,search", "description:text", "price:decimal:req,min=0", "is_available:boolean"],
    "warehouse": ["name:string:req,search", "location:string"],
    "account": ["name:string:req,search", "balance:decimal"],
    "inventory_item": ["name:string:req,search", "sku:string:uniq", "quantity:integer:min=0", "unit_price:decimal:min=0"],
    "milestone": ["title:string:req,search", "due_date:date", "status:enum(open|reached|missed)"],
    "task": ["title:string:req,search", "description:text", "due_date:date", "status:enum(todo|in_progress|done)", "priority:enum(low|medium|high)"],
    "ticket": ["subject:string:req,search", "description:text:search", "priority:enum(low|medium|high|urgent)", "status:enum(open|in_progress|resolved|closed)"],
    # events / records
    "appointment": ["appointment_date:date:req", "appointment_time:time", "reason:text", "status:enum(scheduled|completed|cancelled)"],
    "admission": ["admitted_on:date:req", "discharged_on:date", "reason:text", "status:enum(admitted|discharged)"],
    "prescription": ["prescribed_on:date", "medication:string:req,search", "dosage:string", "instructions:text"],
    "lab_test": ["test_name:string:req,search", "requested_on:date", "result:text", "status:enum(requested|in_progress|completed)"],
    "medical_record": ["record_date:date", "diagnosis:text:search", "treatment:text", "notes:text"],
    "invoice": ["invoice_number:string:uniq,search", "issued_on:date", "total_amount:decimal:min=0", "paid_amount:decimal:min=0", "status:enum(unpaid|partially_paid|paid)"],
    "payment": ["amount:decimal:req,min=0", "paid_on:date", "method:enum(cash|card|bank_transfer)", "status:enum(pending|completed|failed)"],
    "trip": ["origin:string:req,search", "destination:string:req,search", "start_time:datetime", "end_time:datetime", "distance_km:float:min=0", "status:enum(planned|in_progress|completed|cancelled)"],
    "maintenance": ["service_date:date:req", "description:text:search", "cost:decimal:min=0", "status:enum(scheduled|in_progress|completed)"],
    "fuel_record": ["fill_date:date:req", "liters:float:req,min=0", "cost:decimal:min=0", "odometer_km:integer:min=0"],
    "assignment": ["title:string:req,search", "description:text", "due_date:date", "max_score:integer:min=0"],
    "vehicle_assignment": ["start_date:date:req", "end_date:date", "status:enum(active|ended)"],
    "attendance": ["attendance_date:date:req", "status:enum(present|absent|late|excused)"],
    "examination": ["title:string:req,search", "exam_date:date:req", "max_marks:integer:min=0"],
    "exam_result": ["marks:integer:min=0", "grade:string"],
    "enrollment": ["enrolled_on:date", "status:enum(active|completed|dropped)"],
    "order": ["order_number:string:uniq,search", "order_date:date", "total_amount:decimal:min=0", "shipping_address:text", "status:enum(pending|paid|shipped|delivered|cancelled)"],
    "order_item": ["quantity:integer:req,min=1", "unit_price:decimal:min=0"],
    "cart_item": ["quantity:integer:req,min=1"],
    "delivery": ["tracking_number:string:uniq,search", "carrier:string", "shipped_on:date", "delivered_on:date", "status:enum(pending|in_transit|delivered|returned)"],
    "review": ["rating:integer:req,min=1,max=5", "comment:text:search"],
    "comment": ["content:text:req,search"],
    "booking": ["booking_date:date:req", "status:enum(pending|confirmed|cancelled)", "notes:text"],
    "reservation": ["reserved_on:date:req", "status:enum(pending|confirmed|cancelled)"],
    "inspection": ["inspection_date:date:req", "findings:text:search", "condition:enum(good|fair|poor)"],
    "honey_harvest": ["harvest_date:date:req", "quantity_kg:float:req,min=0", "notes:text"],
    "harvest": ["harvest_date:date:req", "quantity:float:min=0", "notes:text"],
    "swarm_report": ["reported_on:date:req", "location:string:search", "description:text", "status:enum(reported|captured|lost)"],
    "expense": ["title:string:req,search", "amount:decimal:req,min=0", "expense_date:date:req"],
    "sale": ["sale_date:date:req", "quantity:integer:min=1", "total_amount:decimal:min=0"],
    "loan": ["borrowed_on:date:req", "due_on:date:req", "returned_on:date", "status:enum(borrowed|returned|overdue)"],
    "leave_request": ["start_date:date:req", "end_date:date:req", "reason:text", "status:enum(pending|approved|rejected)"],
    "shift": ["shift_date:date:req", "start_time:time", "end_time:time"],
    "schedule": ["day:enum(monday|tuesday|wednesday|thursday|friday|saturday|sunday)", "start_time:time", "end_time:time"],
    "note": ["title:string:req,search", "content:text:search"],
    "post": ["title:string:req,search", "content:text:req,search", "status:enum(draft|published|archived)"],
    "event": ["title:string:req,search", "starts_at:datetime:req", "location:string:search", "capacity:integer:min=0"],
    "report": ["title:string:req,search", "report_date:date", "summary:text"],
}

# A department / activity noun the user wrote -> the record(s) it manages.
MODULE_RECORDS: Dict[str, List[str]] = {
    "billing": ["invoice"],
    "invoicing": ["invoice"],
    "pharmacy": ["medicine"],
    "laboratory": ["lab_test"],
    "lab": ["lab_test"],
    "inventory": ["inventory_item"],
    "stock": ["inventory_item"],
    "shopping_cart": ["cart_item"],
    "cart": ["cart_item"],
    "checkout": ["order"],
    "shipping": ["delivery"],
    "delivery_tracking": ["delivery"],
    "attendance": ["attendance"],
    "payroll": ["payslip"],
    "fuel": ["fuel_record"],
    "maintenance": ["maintenance"],
    "scheduling": ["schedule"],
    "booking": ["booking"],
    "admissions": ["admission"],
    "examinations": ["examination"],
    "exams": ["examination"],
    "exam": ["examination"],
    "grading": ["exam_result"],
    "staff": ["staff"],
    "medical_records": ["medical_record"],
    "lab_tests": ["lab_test"],
}

# Typical relations: child -> parents (applied ONLY when the prompt requested both entities).
TYPICAL_RELATIONS: Dict[str, List[str]] = {
    "appointment": ["patient", "doctor", "department"],
    "admission": ["patient", "bed", "room", "doctor"],
    "bed": ["room"],
    "room": ["department"],
    "prescription": ["patient", "doctor", "medicine"],
    "lab_test": ["patient", "doctor"],
    "medical_record": ["patient", "doctor"],
    "invoice": ["patient", "customer", "order", "student", "member"],
    "payment": ["invoice", "order", "customer"],
    "doctor": ["department"],
    "staff": ["department"],
    "employee": ["department"],
    "nurse": ["department"],
    "trip": ["vehicle", "driver"],
    "maintenance": ["vehicle", "equipment"],
    "fuel_record": ["vehicle", "driver"],
    "vehicle_assignment": ["vehicle", "driver"],
    "lesson": ["course"],
    "course": ["teacher", "instructor"],
    "assignment": ["course", "lesson"],
    "attendance": ["student", "lesson", "course"],
    "examination": ["course"],
    "exam_result": ["examination", "student"],
    "enrollment": ["student", "course"],
    "product": ["category", "supplier"],
    "inventory_item": ["product", "warehouse"],
    "cart_item": ["product"],
    "order": ["customer"],
    "order_item": ["order", "product"],
    "delivery": ["order"],
    "review": ["product", "course", "book"],
    "task": ["project", "milestone", "team"],
    "milestone": ["project"],
    "project": ["team"],
    "comment": ["task", "post", "ticket"],
    "queen": ["hive"],
    "inspection": ["hive"],
    "honey_harvest": ["hive"],
    "harvest": ["hive"],
    "swarm_report": ["hive"],
    "hive": ["apiary"],
    "loan": ["book", "member"],
    "sale": ["medicine", "product"],
    "medicine_sale": ["medicine"],
    "leave_request": ["employee", "staff"],
    "booking": ["room", "event", "customer"],
    "expense": ["category"],
}

# Lexical flags used for access-policy defaults (never to add entities).
PERSONAL_RECORDS = {"cart_item", "wishlist", "order", "review", "note", "habit", "goal", "workout", "journal_entry"}
CATALOGUE_RECORDS = {"product", "category", "menu_item", "course"}

# Words that describe app features, pages or plumbing rather than stored data.
FEATURE_WORDS = {
    "search", "searching", "sort", "sorting", "filter", "filters", "filtering", "pagination", "login", "logins", "logout",
    "registration", "signup", "sign up", "sign in", "authentication", "authorization", "auth", "dashboard", "dashboards",
    "analytics", "chart", "charts", "statistics", "stats", "graph", "graphs", "settings", "history", "homepage",
    "home page", "storefront", "landing page", "banner", "hero banner", "navigation", "sidebar", "navbar", "theme",
    "layout", "design", "export", "import", "print", "printing", "upload", "uploads", "download", "api", "apis", "crud",
    "database", "backend", "frontend", "ui", "ux", "admin panel", "role", "roles", "permission", "permissions",
    "access control", "user", "users", "account", "accounts", "profile", "profiles", "notification", "notifications",
    "email notifications", "management", "module", "modules", "system", "app", "application", "platform", "website",
    "site", "portal", "page", "pages", "form", "forms", "table", "tables", "button", "buttons", "workflow", "workflows",
    "feature", "features", "functionality", "operation", "operations", "data", "information", "info", "details",
    "record", "records", "item", "items", "list", "lists", "view", "views", "screen", "screens", "process", "processes",
    "requirement", "requirements", "integration", "integrations", "test", "tests", "testing", "deployment",
    "reports", "report", "reporting", "overview", "summary", "status", "statuses", "tracking", "progress", "deadline",
    "deadlines", "priority", "priorities", "availability", "schedule management", "photography", "images", "image",
    "photos", "ratings", "prices", "descriptions", "typography", "spacing", "colors", "colour", "color", "icons",
    "loading states", "error handling", "validation", "validation messages", "empty states", "sample data",
}

# Attribute words: if a phrase's head noun is one of these it describes a field, not an entity.
ATTRIBUTE_HEADS = {
    "name", "title", "date", "time", "status", "amount", "price", "cost", "fee", "number", "no", "id", "email", "phone",
    "address", "age", "gender", "description", "notes", "note", "history", "quantity", "qty", "stock", "level", "type",
    "category", "code", "rating", "score", "marks", "grade", "balance", "total", "count", "capacity", "duration",
    "location", "deadline", "progress", "priority", "availability", "specialization", "designation", "salary", "url",
    "photo", "image", "picture", "details", "information", "info", "contact", "group", "remarks", "comments", "result",
    "results", "year", "dosage", "unit", "units", "rate", "value", "size", "weight", "height", "distance", "mileage",
    "odometer", "liters", "litres", "selection", "slot", "expiry", "expiration", "reason", "diagnosis", "label",
}

# Words naming people; used to recognise roles/target users ("for beekeepers", "Doctor: ...").
PERSON_SUFFIXES = ("er", "or", "ist", "ian", "ant", "ent", "eer", "ee")
NOT_PEOPLE = {"order", "number", "folder", "header", "footer", "filter", "register", "letter", "chapter", "center",
              "user", "layer", "container", "computer", "paper", "water", "monitor", "sensor", "server", "error",
              "factor", "sector", "vendor_list", "content", "student_list", "component", "department", "payment",
              "equipment", "document", "assignment", "appointment", "management", "requirement", "treatment",
              "enrollment", "statement", "agreement", "movement", "shipment", "investment", "settlement", "event",
              "percent", "parent_list", "tenant_list", "client_list", "point", "segment", "moment", "element"}

# Common value sets for well-known attribute names.
KNOWN_VALUE_SETS: Dict[str, List[str]] = {
    "gender": ["male", "female", "other"],
    "blood_group": ["a_pos", "a_neg", "b_pos", "b_neg", "ab_pos", "ab_neg", "o_pos", "o_neg"],
    "blood_type": ["a_pos", "a_neg", "b_pos", "b_neg", "ab_pos", "ab_neg", "o_pos", "o_neg"],
    "priority": ["low", "medium", "high"],
    "payment_method": ["cash", "card", "bank_transfer"],
    "method": ["cash", "card", "bank_transfer"],
    "day": ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
    "marital_status": ["single", "married", "divorced", "widowed"],
    "shift": ["morning", "evening", "night"],
}

# Verb -> resulting state, used to build workflows from verbs the prompt uses ("admit", "discharge").
VERB_STATES: Dict[str, str] = {
    "admit": "admitted", "discharge": "discharged", "approve": "approved", "reject": "rejected", "submit": "submitted",
    "assign": "assigned", "complete": "completed", "cancel": "cancelled", "close": "closed", "open": "open",
    "resolve": "resolved", "ship": "shipped", "deliver": "delivered", "dispatch": "dispatched", "pay": "paid",
    "refund": "refunded", "return": "returned", "borrow": "borrowed", "check_in": "checked_in", "check_out": "checked_out",
    "confirm": "confirmed", "publish": "published", "archive": "archived", "start": "in_progress", "finish": "completed",
    "schedule": "scheduled", "book": "booked", "enroll": "enrolled", "graduate": "graduated", "suspend": "suspended",
    "activate": "active", "deactivate": "inactive", "dispense": "dispensed", "capture": "captured",
}

TERMINAL_STATES = {"completed", "done", "closed", "cancelled", "canceled", "rejected", "discharged", "delivered",
                   "returned", "resolved", "paid", "archived", "ended", "lost", "dead", "failed", "dropped", "refunded",
                   "captured", "dispensed", "checked_out", "graduated", "reached", "missed", "sold"}
CANCEL_STATES = {"cancelled", "canceled", "rejected", "void", "voided", "failed", "lost"}
AVAILABLE_STATES = {"available", "free", "vacant", "open", "idle", "in_stock"}
OCCUPIED_STATES = {"occupied", "in_use", "assigned", "booked", "reserved", "rented", "borrowed", "on_trip", "busy", "let"}

# Generic colour words for theme requests ("blue-and-white theme", "teal accent").
COLOR_WORDS: Dict[str, str] = {
    "blue": "#2563eb", "navy": "#1e3a8a", "teal": "#0d9488", "green": "#16a34a", "emerald": "#059669",
    "purple": "#7c3aed", "violet": "#7c3aed", "indigo": "#4f46e5", "red": "#dc2626", "orange": "#ea580c",
    "amber": "#d97706", "yellow": "#ca8a04", "pink": "#db2777", "rose": "#e11d48", "cyan": "#0891b2",
    "gray": "#4b5563", "grey": "#4b5563", "black": "#111827", "brown": "#92400e", "gold": "#b45309",
}


def parse_attribute(spec: str) -> Tuple[str, str, List[str], List[str]]:
    """Parse 'name:type[:flags]' into (name, type, enum_values, flags)."""
    parts = spec.split(":")
    name, ftype = parts[0], parts[1]
    flags = parts[2].split(",") if len(parts) > 2 and parts[2] else []
    values: List[str] = []
    if ftype.startswith("enum(") and ftype.endswith(")"):
        values = ftype[5:-1].split("|")
        ftype = "enum"
    return name, ftype, values, flags
