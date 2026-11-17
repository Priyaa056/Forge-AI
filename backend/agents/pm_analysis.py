"""Requirement analysis for the PM Agent.

Two responsibilities:

* :func:`analyze_prompt` – deterministic, prompt-driven requirement extraction used when no LLM is
  configured. Every output is derived from the user's prompt (detected domain, entities, fields,
  relations, roles and features); nothing is a canned response.
* :func:`normalize_requirements` – enforces the naming and structural conventions every downstream
  agent relies on (applied to LLM output as well), so that a creative LLM answer can never break
  code generation silently.
"""

import re
from typing import Dict, List, Optional, Tuple

from backend.codegen.naming import (
    fk_field_name,
    humanize,
    pluralize,
    safe_identifier,
    singularize,
    to_pascal,
    to_snake,
)
from backend.schemas.pm_schema import (
    DatabaseEntity,
    DevelopmentTask,
    EntityField,
    PMOutput,
    Requirement,
    TechStack,
    UserRole,
)


class PromptValidationError(ValueError):
    """Raised when a prompt is empty, too vague or does not describe an application."""


# ---------------------------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------------------------
# Field DSL: "name:type[:flags]" where type is a semantic type, enum(a|b|c) or ref(Entity);
# flags: req (required), uniq (unique), search (free-text searchable), min=N, max=N.

ENTITY_KB: Dict[str, Dict] = {
    "task": {"name": "Task", "kw": [r"\btasks?\b", r"\bto-?dos?\b"], "access": "owner", "display": "title",
             "fields": ["title:string:req,search", "description:text:search", "status:enum(todo|in_progress|done)",
                        "priority:enum(low|medium|high)", "due_date:date"]},
    "project": {"name": "Project", "kw": [r"\bprojects?\b"], "access": "shared", "display": "name",
                "fields": ["name:string:req,search", "description:text", "status:enum(planning|active|completed|on_hold)",
                           "start_date:date", "end_date:date"]},
    "category": {"name": "Category", "kw": [r"\bcategor(?:y|ies)\b"], "access": "admin_managed", "display": "name",
                 "fields": ["name:string:req,uniq,search", "description:text"]},
    "tag": {"name": "Tag", "kw": [r"\btags?\b"], "access": "shared", "display": "name",
            "fields": ["name:string:req,uniq,search", "color:string"]},
    "product": {"name": "Product", "kw": [r"\bproducts?\b", r"\bcatalog(?:ue)?\b", r"\bitems? for sale\b"], "access": "admin_managed",
                "display": "name",
                "fields": ["name:string:req,search", "description:text:search", "price:decimal:req,min=0",
                           "stock:integer:min=0", "sku:string:uniq", "image_url:string", "is_active:boolean"]},
    "cart_item": {"name": "CartItem", "kw": [r"\b(?:shopping )?carts?\b", r"\bbaskets?\b"], "access": "owner", "display": "id",
                  "fields": ["quantity:integer:req,min=1"]},
    "order": {"name": "Order", "kw": [r"\borders\b", r"\border (?:management|history|tracking|status|processing|placement)\b", r"\bplace (?:an )?orders?\b", r"\bcheckout\b", r"\bpurchases\b"], "access": "owner", "display": "order_number",
              "fields": ["order_number:string:uniq,search", "status:enum(pending|paid|shipped|delivered|cancelled)",
                         "total_amount:decimal:min=0", "shipping_address:text", "notes:text"]},
    "order_item": {"name": "OrderItem", "kw": [r"\border items?\b", r"\bline items?\b"], "access": "owner", "display": "id",
                   "fields": ["quantity:integer:req,min=1", "unit_price:decimal:min=0"]},
    "review": {"name": "Review", "kw": [r"\breviews?\b", r"\bratings?\b"], "access": "owner", "display": "title",
               "fields": ["title:string:search", "rating:integer:req,min=1,max=5", "comment:text:search"]},
    "customer": {"name": "Customer", "kw": [r"\bcustomers?\b", r"\bclients?\b"], "access": "shared", "display": "name",
                 "fields": ["name:string:req,search", "email:email:search", "phone:string", "company:string:search", "address:text"]},
    "supplier": {"name": "Supplier", "kw": [r"\bsuppliers?\b", r"\bvendors?\b"], "access": "admin_managed", "display": "name",
                 "fields": ["name:string:req,search", "email:email", "phone:string", "address:text"]},
    "warehouse": {"name": "Warehouse", "kw": [r"\bwarehouses?\b"], "access": "admin_managed", "display": "name",
                  "fields": ["name:string:req,search", "location:string"]},
    "stock_movement": {"name": "StockMovement", "kw": [r"\bstock movements?\b", r"\binventory (?:transactions|movements)\b"],
                       "access": "shared", "display": "id",
                       "fields": ["movement_type:enum(in|out|adjustment):req", "quantity:integer:req", "reason:text"]},
    "post": {"name": "Post", "kw": [r"\bposts?\b", r"\barticles?\b", r"\bblog\b"], "access": "owner", "display": "title",
             "fields": ["title:string:req,search", "content:text:req,search", "status:enum(draft|published|archived)",
                        "published_at:datetime"]},
    "comment": {"name": "Comment", "kw": [r"\bcomments?\b"], "access": "owner", "display": "id",
                "fields": ["content:text:req,search"]},
    "event": {"name": "Event", "kw": [r"\bevents?\b"], "access": "admin_managed", "display": "title",
              "fields": ["title:string:req,search", "description:text:search", "location:string:search",
                         "starts_at:datetime:req", "ends_at:datetime", "capacity:integer:min=0"]},
    "booking": {"name": "Booking", "kw": [r"\bbookings?\b", r"\breservations?\b"], "access": "owner", "display": "id",
                "fields": ["booking_date:date:req", "guests:integer:min=1", "status:enum(pending|confirmed|cancelled)", "notes:text"]},
    "room": {"name": "Room", "kw": [r"\brooms?\b"], "access": "admin_managed", "display": "name",
             "fields": ["name:string:req,search", "room_type:enum(single|double|suite)", "price_per_night:decimal:min=0",
                        "capacity:integer:min=1", "is_available:boolean"]},
    "appointment": {"name": "Appointment", "kw": [r"\bappointments?\b"], "access": "owner", "display": "id",
                    "fields": ["scheduled_at:datetime:req", "reason:text:search", "status:enum(scheduled|completed|cancelled)"]},
    "doctor": {"name": "Doctor", "kw": [r"\bdoctors?\b", r"\bphysicians?\b"], "access": "admin_managed", "display": "name",
               "fields": ["name:string:req,search", "specialization:string:search", "email:email", "phone:string"]},
    "patient": {"name": "Patient", "kw": [r"\bpatients?\b"], "access": "shared", "display": "name",
                "fields": ["name:string:req,search", "date_of_birth:date", "phone:string", "medical_notes:text"]},
    "course": {"name": "Course", "kw": [r"\bcourses?\b"], "access": "admin_managed", "display": "title",
               "fields": ["title:string:req,search", "description:text:search", "level:enum(beginner|intermediate|advanced)",
                          "duration_hours:integer:min=0", "is_published:boolean"]},
    "lesson": {"name": "Lesson", "kw": [r"\blessons?\b", r"\bmodules? of (?:a|the) course\b"], "access": "admin_managed", "display": "title",
               "fields": ["title:string:req,search", "content:text", "position:integer:min=0"]},
    "enrollment": {"name": "Enrollment", "kw": [r"\benrol?lments?\b", r"\benrol?l\b"], "access": "owner", "display": "id",
                   "fields": ["status:enum(active|completed|dropped)", "progress:integer:min=0,max=100"]},
    "student": {"name": "Student", "kw": [r"\bstudents?\b"], "access": "shared", "display": "name",
                "fields": ["name:string:req,search", "email:email:search", "grade:string"]},
    "employee": {"name": "Employee", "kw": [r"\bemployees?\b", r"\bstaff\b"], "access": "admin_managed", "display": "name",
                 "fields": ["name:string:req,search", "email:email:search", "job_title:string:search", "hire_date:date",
                            "salary:decimal:min=0"]},
    "department": {"name": "Department", "kw": [r"\bdepartments?\b"], "access": "admin_managed", "display": "name",
                   "fields": ["name:string:req,uniq,search", "description:text"]},
    "leave_request": {"name": "LeaveRequest", "kw": [r"\bleave(?: requests?)?\b", r"\btime off\b"], "access": "owner", "display": "id",
                      "fields": ["start_date:date:req", "end_date:date:req", "reason:text",
                                 "status:enum(pending|approved|rejected)"]},
    "invoice": {"name": "Invoice", "kw": [r"\binvoices?\b", r"\bbilling\b"], "access": "owner", "display": "invoice_number",
                "fields": ["invoice_number:string:req,uniq,search", "amount:decimal:req,min=0", "due_date:date",
                           "status:enum(draft|sent|paid|overdue)"]},
    "payment": {"name": "Payment", "kw": [r"\bpayments?\b"], "access": "owner", "display": "id",
                "fields": ["amount:decimal:req,min=0", "method:enum(card|cash|bank_transfer)", "paid_at:datetime",
                           "status:enum(pending|completed|failed)"]},
    "expense": {"name": "Expense", "kw": [r"\bexpenses?\b", r"\bspending\b"], "access": "owner", "display": "title",
                "fields": ["title:string:req,search", "amount:decimal:req,min=0", "expense_date:date:req", "notes:text"]},
    "budget": {"name": "Budget", "kw": [r"\bbudgets?\b"], "access": "owner", "display": "name",
               "fields": ["name:string:req,search", "limit_amount:decimal:req,min=0", "period:enum(weekly|monthly|yearly)"]},
    "account": {"name": "Account", "kw": [r"\bbank accounts?\b", r"\bwallets?\b"], "access": "owner", "display": "name",
                "fields": ["name:string:req,search", "balance:decimal", "account_type:enum(checking|savings|credit|cash)"]},
    "transaction": {"name": "Transaction", "kw": [r"\btransactions?\b"], "access": "owner", "display": "description",
                    "fields": ["description:string:req,search", "amount:decimal:req", "transaction_type:enum(income|expense)",
                               "transaction_date:date:req"]},
    "note": {"name": "Note", "kw": [r"\bnotes?\b(?! app)", r"\bnote[- ]taking\b"], "access": "owner", "display": "title",
             "fields": ["title:string:req,search", "content:text:search", "is_pinned:boolean"]},
    "contact": {"name": "Contact", "kw": [r"\bcontacts?\b", r"\baddress book\b"], "access": "owner", "display": "name",
                "fields": ["name:string:req,search", "email:email:search", "phone:string", "company:string:search", "notes:text"]},
    "lead": {"name": "Lead", "kw": [r"\bleads?\b"], "access": "shared", "display": "name",
             "fields": ["name:string:req,search", "email:email:search", "source:string",
                        "status:enum(new|contacted|qualified|lost)"]},
    "deal": {"name": "Deal", "kw": [r"\bsales deals?\b", r"\bdeals? pipeline\b", r"\bopportunit(?:y|ies)\b"], "access": "shared", "display": "title",
             "fields": ["title:string:req,search", "value:decimal:min=0", "stage:enum(prospect|negotiation|won|lost)",
                        "expected_close_date:date"]},
    "ticket": {"name": "Ticket", "kw": [r"\btickets?\b", r"\bsupport requests?\b", r"\bhelp ?desk\b"], "access": "owner", "display": "subject",
               "fields": ["subject:string:req,search", "description:text:req,search", "priority:enum(low|medium|high|urgent)",
                          "status:enum(open|in_progress|resolved|closed)"]},
    "issue": {"name": "Issue", "kw": [r"\bissues?\b", r"\bbugs?\b"], "access": "shared", "display": "title",
              "fields": ["title:string:req,search", "description:text:search", "severity:enum(low|medium|high|critical)",
                         "status:enum(open|in_progress|resolved|closed)"]},
    "recipe": {"name": "Recipe", "kw": [r"\brecipes?\b"], "access": "owner", "display": "title",
               "fields": ["title:string:req,search", "ingredients:text:req,search", "instructions:text:req",
                          "prep_minutes:integer:min=0", "servings:integer:min=1",
                          "difficulty:enum(easy|medium|hard)"]},
    "book": {"name": "Book", "kw": [r"\bbooks\b", r"\bbook (?:catalog|titles?|inventory|collection|records?)\b"], "access": "admin_managed", "display": "title",
             "fields": ["title:string:req,search", "isbn:string:uniq", "published_year:integer:min=0",
                        "copies_available:integer:min=0"]},
    "author": {"name": "Author", "kw": [r"\bauthors?\b"], "access": "admin_managed", "display": "name",
               "fields": ["name:string:req,search", "biography:text"]},
    "loan": {"name": "Loan", "kw": [r"\bloans?\b", r"\bborrow(?:ing|ed)?\b"], "access": "owner", "display": "id",
             "fields": ["borrowed_on:date:req", "due_on:date:req", "returned_on:date", "status:enum(borrowed|returned|overdue)"]},
    "job": {"name": "Job", "kw": [r"\bjobs?\b", r"\bjob postings?\b", r"\bvacanc(?:y|ies)\b"], "access": "admin_managed", "display": "title",
            "fields": ["title:string:req,search", "description:text:search", "location:string:search",
                       "employment_type:enum(full_time|part_time|contract|internship)", "salary:decimal:min=0", "is_open:boolean"]},
    "application": {"name": "Application", "kw": [r"\bjob applications?\b", r"\bapply\b"], "access": "owner", "display": "id",
                    "fields": ["cover_letter:text", "resume_url:string", "status:enum(submitted|reviewing|interview|rejected|hired)"]},
    "workout": {"name": "Workout", "kw": [r"\bworkouts?\b", r"\bexercises?\b", r"\bfitness\b"], "access": "owner", "display": "name",
                "fields": ["name:string:req,search", "workout_date:date:req", "duration_minutes:integer:min=0",
                           "calories_burned:integer:min=0", "notes:text"]},
    "habit": {"name": "Habit", "kw": [r"\bhabits?\b"], "access": "owner", "display": "name",
              "fields": ["name:string:req,search", "frequency:enum(daily|weekly|monthly)", "streak:integer:min=0", "is_active:boolean"]},
    "goal": {"name": "Goal", "kw": [r"\bgoals?\b"], "access": "owner", "display": "title",
             "fields": ["title:string:req,search", "description:text", "target_date:date", "status:enum(not_started|in_progress|achieved)"]},
    "property": {"name": "Property", "kw": [r"\bpropert(?:y|ies)\b", r"\breal estate\b", r"\bproperty listings?\b"], "access": "admin_managed",
                 "display": "title",
                 "fields": ["title:string:req,search", "address:string:search", "price:decimal:min=0", "bedrooms:integer:min=0",
                            "property_type:enum(apartment|house|land|commercial)", "is_available:boolean"]},
    "vehicle": {"name": "Vehicle", "kw": [r"\bvehicles?\b", r"\bcars?\b", r"\bfleet\b"], "access": "admin_managed", "display": "name",
                "fields": ["name:string:req,search", "plate_number:string:uniq,search", "model_year:integer:min=1900",
                           "status:enum(available|in_use|maintenance)"]},
    "menu_item": {"name": "MenuItem", "kw": [r"\bmenu(?: items?)?\b", r"\bdish(?:es)?\b"], "access": "admin_managed", "display": "name",
                  "fields": ["name:string:req,search", "description:text", "price:decimal:req,min=0", "is_available:boolean"]},
    "message": {"name": "Message", "kw": [r"\bmessages?\b", r"\bchat\b"], "access": "owner", "display": "subject",
                "fields": ["subject:string:search", "body:text:req,search", "is_read:boolean"]},
}

# child entity key -> parent entity keys it references when both are present
RELATIONS_KB: Dict[str, List[str]] = {
    "task": ["category", "project"],
    "issue": ["project"],
    "product": ["category", "supplier"],
    "cart_item": ["product"],
    "order_item": ["order", "product"],
    "review": ["product", "course", "book", "recipe"],
    "post": ["category"],
    "comment": ["post", "task", "ticket", "issue"],
    "booking": ["room", "event"],
    "appointment": ["doctor", "patient"],
    "lesson": ["course"],
    "enrollment": ["course"],
    "employee": ["department"],
    "leave_request": ["employee"],
    "invoice": ["customer"],
    "payment": ["invoice", "order"],
    "expense": ["category", "budget"],
    "transaction": ["account", "category"],
    "book": ["author", "category"],
    "loan": ["book"],
    "application": ["job"],
    "recipe": ["category"],
    "deal": ["lead", "customer"],
    "event": ["category"],
    "stock_movement": ["product", "warehouse"],
    "ticket": ["category"],
}

DOMAINS: List[Tuple[str, str, str, List[str]]] = [
    # (key, regex, project name, default entities)
    ("ecommerce", r"e-?commerce|online (?:store|shop)|web ?shop|shopping|marketplace", "E-Commerce Store",
     ["product", "category", "cart_item", "order", "order_item"]),
    ("task_management", r"\btasks?\b|to-?do|kanban|task manag", "Task Manager", ["task", "category"]),
    ("project_management", r"project manag", "Project Tracker", ["project", "task"]),
    ("blog", r"\bblog|cms\b|content management", "Blog Platform", ["post", "category", "comment"]),
    ("hotel_booking", r"hotel|room booking|reservation", "Booking System", ["room", "booking"]),
    ("events", r"\bevent", "Event Manager", ["event", "booking"]),
    ("healthcare", r"hospital|clinic|patient|doctor|medical", "Clinic Manager", ["doctor", "patient", "appointment"]),
    ("education", r"\blms\b|learning|school|course|e-?learning|student", "Learning Platform", ["course", "lesson", "enrollment"]),
    ("hr", r"\bhr\b|human resource|employee|payroll|leave", "HR Portal", ["employee", "department", "leave_request"]),
    ("inventory", r"inventory|warehouse|stock", "Inventory Manager", ["product", "supplier", "stock_movement"]),
    ("finance", r"expense|budget|finance|money|spending", "Expense Tracker", ["expense", "category", "budget"]),
    ("crm", r"\bcrm\b|customer relationship|sales pipeline|leads?\b", "CRM", ["customer", "lead", "deal"]),
    ("library", r"library|\bbooks?\b", "Library Manager", ["book", "author", "loan"]),
    ("recipes", r"recipe|cooking|meal", "Recipe Book", ["recipe", "category"]),
    ("helpdesk", r"help ?desk|support ticket|ticketing|customer support", "Help Desk", ["ticket", "category", "comment"]),
    ("recruitment", r"recruit|job board|hiring|candidate|job portal", "Job Board", ["job", "application"]),
    ("fitness", r"fitness|workout|gym|exercise", "Fitness Tracker", ["workout", "goal"]),
    ("notes", r"note[- ]?taking|\bnotes app|notebook", "Notes", ["note", "tag"]),
    ("real_estate", r"real estate|propert(?:y|ies)|rental", "Property Listings", ["property"]),
    ("restaurant", r"restaurant|food order|cafe|menu", "Restaurant Orders", ["menu_item", "order"]),
    ("habits", r"habit", "Habit Tracker", ["habit", "goal"]),
]

# Categories are personal in these domains; elsewhere they are a catalogue managed by admins.
OWNER_CATEGORY_DOMAINS = {"task_management", "finance", "notes", "recipes"}

GENERIC_STOPWORDS = {
    "app", "apps", "application", "applications", "system", "website", "site", "platform", "portal", "user", "users",
    "data", "thing", "things", "stuff", "information", "info", "everything", "it", "them", "account", "accounts",
    "login", "logins", "registration", "admin", "dashboard", "page", "pages", "web", "mobile", "the", "a", "an",
    "their", "my", "our", "your", "all", "and", "or", "with", "for", "simple", "basic", "full", "complete", "modern",
    "role", "roles", "profile", "profiles", "password", "passwords", "authentication", "auth", "status", "search",
}

ROLE_KEYWORDS = {
    "manager": "Manages records within the organisation",
    "seller": "Lists and manages products",
    "vendor": "Lists and manages products",
    "customer": "Browses and purchases",
    "teacher": "Creates and manages course content",
    "instructor": "Creates and manages course content",
    "student": "Consumes course content",
    "doctor": "Manages appointments",
    "editor": "Edits and publishes content",
    "agent": "Handles support requests",
}


def _parse_field(spec: str) -> EntityField:
    parts = spec.split(":")
    name, ftype = parts[0], parts[1]
    flags = parts[2].split(",") if len(parts) > 2 and parts[2] else []
    enum_values: List[str] = []
    references = None
    m = re.match(r"enum\((.*)\)", ftype)
    if m:
        enum_values = m.group(1).split("|")
        ftype = "enum"
    m = re.match(r"ref\((.*)\)", ftype)
    if m:
        references = m.group(1)
        ftype = "reference"
    field = EntityField(
        name=name,
        type=ftype,
        nullable="req" not in flags,
        unique="uniq" in flags,
        searchable="search" in flags,
        enum_values=enum_values,
        references=references,
        label=humanize(name),
    )
    for flag in flags:
        if flag.startswith("min="):
            field.min_value = float(flag[4:])
        elif flag.startswith("max="):
            field.max_value = float(flag[4:])
    if enum_values:
        field.default = enum_values[0]
        field.nullable = False
    if ftype == "boolean":
        field.default = "true" if name.startswith("is_") and name in {"is_active", "is_available", "is_open"} else "false"
        field.nullable = False
    return field


def _kb_entity(key: str, domain: Optional[str]) -> DatabaseEntity:
    kb = ENTITY_KB[key]
    access = kb["access"]
    if key == "category" and domain in OWNER_CATEGORY_DOMAINS:
        access = "owner"
    return DatabaseEntity(
        name=kb["name"],
        description=f"{humanize(kb['name'])} records",
        fields=[_parse_field(f) for f in kb["fields"]],
        access=access,
        display_field=kb["display"],
    )


def _detect_domain(text: str) -> Optional[Tuple[str, str, List[str]]]:
    for key, pattern, name, defaults in DOMAINS:
        if re.search(pattern, text):
            return key, name, defaults
    return None


def _extract_generic_nouns(text: str) -> List[str]:
    candidates: List[str] = []
    patterns = [
        r"\b(?:manage|managing|track|tracking|record|recording|organi[sz]e|organi[sz]ing|catalog(?:ue)?|log|logging|schedule|scheduling|store|storing)\s+(?:their |my |our |the |all |your |of )?([a-z]+(?: [a-z]+)?)",
        r"\b([a-z]+)\s+(?:management|tracker|tracking|catalog(?:ue)?|directory|log|registry|inventory)\b",
        r"\blist of ([a-z]+)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            phrase = match.group(1).strip()
            tokens = [t for t in phrase.split() if t not in GENERIC_STOPWORDS]
            if not tokens:
                continue
            noun = singularize(tokens[-1])
            if len(noun) < 3 or noun in GENERIC_STOPWORDS:
                continue
            if noun not in candidates:
                candidates.append(noun)
    return candidates


def _generic_entity(noun: str) -> DatabaseEntity:
    return DatabaseEntity(
        name=to_pascal(noun),
        description=f"{humanize(noun)} records",
        fields=[
            _parse_field("name:string:req,search"),
            _parse_field("description:text:search"),
            _parse_field("status:enum(active|inactive)"),
        ],
        access="owner",
        display_field="name",
    )


def validate_prompt(prompt: Optional[str]) -> str:
    text = (prompt or "").strip()
    if not text:
        raise PromptValidationError("The prompt is empty. Describe the application you want FORGE AI to build.")
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    if len(text) < 15 or len(words) < 4:
        raise PromptValidationError(
            "The prompt is too short to derive requirements. Describe the application, who uses it and its main "
            "features, e.g. 'Build a task manager with login, task categories and an admin dashboard'."
        )
    if len(text) > 4000:
        raise PromptValidationError("The prompt is longer than 4000 characters; summarise the main requirements.")
    vowelless = [w for w in words if len(w) > 3 and not re.search(r"[aeiouyAEIOUY]", w)]
    if len(vowelless) > len(words) / 2:
        raise PromptValidationError("The prompt does not look like a natural-language description of an application.")
    return text


def analyze_prompt(prompt: str) -> PMOutput:
    """Derive structured requirements from a natural-language prompt without an LLM."""
    text = validate_prompt(prompt)
    lower = text.lower()
    assumptions: List[str] = []

    domain = _detect_domain(lower)
    domain_key = domain[0] if domain else None

    detected: List[str] = []
    for key, kb in ENTITY_KB.items():
        if any(re.search(p, lower) for p in kb["kw"]):
            detected.append(key)

    # Disambiguation: an e-commerce "order management" mention implies order items as well.
    if "order" in detected and ("product" in detected or domain_key == "ecommerce") and "order_item" not in detected:
        detected.append("order_item")
        assumptions.append("Orders contain order items that reference products.")
    if "cart_item" in detected and "product" not in detected:
        detected.append("product")
    if "post" in detected and domain_key not in ("blog", None) and not re.search(r"\b(?:blog|posts?|articles?)\b", lower):
        detected.remove("post")
    # "booking" style words inside other domains: keep only if explicitly mentioned.
    if domain_key == "education" and "student" in detected and "enrollment" not in detected:
        detected.append("enrollment")

    if domain_key in ("ecommerce", "restaurant") and "customer" in detected:
        detected.remove("customer")
        assumptions.append("Customers are represented by registered user accounts.")
    if not detected and domain:
        detected = list(domain[2])
        assumptions.append(f"No explicit entities named; using the typical {domain[1]} data model.")

    entities: List[DatabaseEntity] = [_kb_entity(key, domain_key) for key in detected]

    if not entities:
        for noun in _extract_generic_nouns(lower):
            if noun in ENTITY_KB:
                entities.append(_kb_entity(noun, domain_key))
            else:
                entities.append(_generic_entity(noun))
        if entities:
            assumptions.append("Entities were inferred from the nouns the prompt asks to manage/track.")

    if not entities:
        raise PromptValidationError(
            "Could not identify what data the application should manage. Mention the main things users work with, "
            "e.g. 'tasks', 'products and orders', 'patients and appointments'."
        )

    by_key = {e.name: e for e in entities}

    # Feature-driven field augmentation on the primary entity.
    primary = entities[0]
    names = {f.name for f in primary.fields}
    if re.search(r"\bpriorit", lower) and "priority" not in names:
        primary.fields.append(_parse_field("priority:enum(low|medium|high)"))
    if re.search(r"\bdue dates?\b|\bdeadlines?\b", lower) and not any("due" in n for n in names):
        primary.fields.append(_parse_field("due_date:date"))
    if re.search(r"\bstatus(?:es)?\b", lower) and "status" not in names:
        primary.fields.append(_parse_field("status:enum(open|in_progress|completed)"))

    # Relations between detected entities.
    for key in detected:
        child = ENTITY_KB[key]["name"]
        for parent_key in RELATIONS_KB.get(key, []):
            parent = ENTITY_KB[parent_key]["name"]
            if parent in by_key and child in by_key:
                fk = fk_field_name(parent)
                if fk not in {f.name for f in by_key[child].fields}:
                    required = (key, parent_key) in {("cart_item", "product"), ("order_item", "order"),
                                                     ("order_item", "product"), ("lesson", "course"),
                                                     ("enrollment", "course"), ("loan", "book")}
                    by_key[child].fields.append(EntityField(
                        name=fk, type="reference", references=parent, nullable=not required,
                        label=humanize(parent), description=f"{humanize(child)} belongs to a {humanize(parent).lower()}",
                    ))

    roles = [UserRole(name="admin", description="Full access to all records, users and the admin dashboard", is_admin=True),
             UserRole(name="user", description="Registered user who manages their own records")]
    for kw, desc in ROLE_KEYWORDS.items():
        role_pattern = (rf"\b{kw}s? (?:can|should|may|will|role)\b|\b(?:as an?|for|by) {kw}s?\b|"
                        rf"\b{kw}s? (?:and|or) admins?\b|\badmins?(?:,| and| or) {kw}s?\b")
        if re.search(role_pattern, lower) and kw not in {r.name for r in roles}:
            if to_pascal(kw) in by_key:  # it is a data entity, not a role
                continue
            roles.append(UserRole(name=kw, description=desc))

    has_admin = True
    if not re.search(r"\badmin", lower):
        assumptions.append("An admin role and dashboard are included to manage users and data.")

    project_name = _project_name(text, domain, entities)
    pm = PMOutput(
        project_name=project_name,
        description=text,
        tech_stack=TechStack(),
        database_entities=entities,
        app_type=domain_key or "custom",
        user_roles=roles,
        requires_auth=True,
        has_admin_dashboard=has_admin,
        source_prompt=text,
        generation_mode="deterministic",
        assumptions=assumptions,
    )
    if re.search(r"\bsearch", lower):
        for entity in pm.database_entities:
            if not any(f.searchable for f in entity.fields):
                for f in entity.fields:
                    if f.type in ("string", "text"):
                        f.searchable = True
    return normalize_requirements(pm)


def _project_name(text: str, domain, entities: List[DatabaseEntity]) -> str:
    m = re.search(r"\b(?:called|named|titled)\s+[\"']?([A-Za-z0-9][\w\- ]{1,40}?)[\"']?(?:[,.;]|\s+(?:with|that|for|which)\b|$)", text)
    if m:
        return m.group(1).strip()
    if domain:
        return domain[1]
    return f"{humanize(entities[0].name)} Manager"


# ---------------------------------------------------------------------------------------------
# Normalization (applies to both LLM and deterministic output)
# ---------------------------------------------------------------------------------------------

_TYPE_ALIASES = {
    "str": "string", "string": "string", "varchar": "string", "char": "string", "url": "string", "phone": "string",
    "text": "text", "longtext": "text", "markdown": "text",
    "int": "integer", "integer": "integer", "bigint": "integer", "smallint": "integer", "number": "integer",
    "float": "float", "double": "float", "real": "float",
    "decimal": "decimal", "numeric": "decimal", "money": "decimal", "currency": "decimal", "price": "decimal",
    "bool": "boolean", "boolean": "boolean",
    "date": "date",
    "datetime": "datetime", "timestamp": "datetime", "timestamptz": "datetime", "time": "datetime",
    "email": "email",
    "enum": "enum", "choice": "enum", "select": "enum",
    "reference": "reference", "foreign_key": "reference", "fk": "reference", "relation": "reference",
}


def _normalize_type(raw: str) -> str:
    t = (raw or "string").strip().lower()
    t = re.sub(r"\(.*\)", "", t).strip()
    t = t.replace("timestamp with time zone", "datetime")
    if t in _TYPE_ALIASES:
        return _TYPE_ALIASES[t]
    for key, value in _TYPE_ALIASES.items():
        if key in t:
            return value
    return "string"


def _user_entity(roles: List[UserRole]) -> DatabaseEntity:
    role_names = [r.name for r in roles] or ["admin", "user"]
    non_admin = [r for r in role_names if r != "admin"] or ["user"]
    return DatabaseEntity(
        name="User",
        description="Application user account (managed by the Authentication agent)",
        is_system=True,
        access="admin_managed",
        display_field="full_name",
        fields=[
            EntityField(name="id", type="integer", primary_key=True, nullable=False, read_only=True, label="ID"),
            EntityField(name="email", type="email", unique=True, nullable=False, searchable=True, label="Email"),
            EntityField(name="full_name", type="string", nullable=False, searchable=True, label="Full name"),
            EntityField(name="role", type="enum", enum_values=role_names, default=non_admin[0], nullable=False, label="Role"),
            EntityField(name="is_active", type="boolean", default="true", nullable=False, label="Active"),
            EntityField(name="hashed_password", type="string", nullable=False, hidden=True, read_only=True, label="Password hash"),
            EntityField(name="created_at", type="datetime", read_only=True, label="Created at"),
        ],
    )


def normalize_requirements(pm: PMOutput) -> PMOutput:
    """Enforce conventions every downstream agent depends on. Raises PromptValidationError if unusable."""
    data = pm.model_copy(deep=True)

    # Roles
    roles: List[UserRole] = []
    seen_roles = set()
    for role in data.user_roles or []:
        name = to_snake(role.name)
        if not name or name in seen_roles:
            continue
        seen_roles.add(name)
        roles.append(UserRole(name=name, description=role.description, is_admin=role.is_admin or name == "admin"))
    if "admin" not in seen_roles:
        roles.insert(0, UserRole(name="admin", description="Full administrative access", is_admin=True))
    if not any(not r.is_admin for r in roles):
        roles.append(UserRole(name="user", description="Registered user"))
    data.user_roles = roles

    # Entities
    entities: List[DatabaseEntity] = []
    seen_entities = set()
    for entity in data.database_entities:
        name = to_pascal(singularize(entity.name)) if entity.name else ""
        if not name or name.lower() in seen_entities or name == "User":
            continue
        seen_entities.add(name.lower())
        entity.name = name
        entity.is_system = False
        if entity.access not in ("owner", "admin_managed", "shared"):
            entity.access = "owner"
        entities.append(entity)
    if not entities:
        raise PromptValidationError("Requirement analysis produced no application entities.")
    if len(entities) > 12:
        entities = entities[:12]
        data.assumptions.append("Only the first 12 entities are generated.")

    entity_names = {e.name for e in entities} | {"User"}

    for entity in entities:
        fields: List[EntityField] = []
        seen = set()
        for f in entity.fields:
            fname = safe_identifier(f.name)
            if fname in seen or fname in {"id", "created_at", "updated_at", "owner_id", "user_id"}:
                continue
            ftype = _normalize_type(f.type)
            if f.references:
                ref = to_pascal(singularize(f.references))
                if ref not in entity_names or ref == entity.name:
                    continue
                f.references = ref
                ftype = "reference"
                fname = fk_field_name(ref)
                if fname in seen:
                    continue
            elif ftype == "reference":
                guess = to_pascal(fname[:-3]) if fname.endswith("_id") else to_pascal(fname)
                if guess in entity_names and guess != entity.name:
                    f.references = guess
                    fname = fk_field_name(guess)
                else:
                    ftype = "integer"
            elif fname.endswith("_id") and to_pascal(fname[:-3]) in entity_names and to_pascal(fname[:-3]) != entity.name:
                ftype = "reference"
                f.references = to_pascal(fname[:-3])
            if ftype == "enum":
                values = [to_snake(v) for v in f.enum_values if str(v).strip()]
                values = list(dict.fromkeys(values))
                if not values:
                    ftype = "string"
                f.enum_values = values
                if values and (f.default is None or to_snake(f.default) not in values):
                    f.default = values[0]
                elif values:
                    f.default = to_snake(f.default)
            else:
                f.enum_values = []
            if ftype == "boolean" and f.default not in ("true", "false"):
                f.default = "false"
            if ftype in ("integer", "float", "decimal"):
                if f.default is not None:
                    try:
                        float(f.default)
                    except (TypeError, ValueError):
                        f.default = None
            elif ftype not in ("enum", "boolean"):
                f.default = None
            f.name = fname
            f.type = ftype
            f.primary_key = False
            f.read_only = False
            f.hidden = False
            f.label = f.label or humanize(fname)
            if ftype in ("text",):
                f.unique = False
            seen.add(fname)
            fields.append(f)
        if not fields:
            fields.append(EntityField(name="name", type="string", nullable=False, searchable=True, label="Name"))
        if not any(f.searchable for f in fields):
            for f in fields:
                if f.type in ("string", "text", "email"):
                    f.searchable = True
                    break

        system_fields = [EntityField(name="id", type="integer", primary_key=True, nullable=False, read_only=True, label="ID")]
        tail = [EntityField(name="created_at", type="datetime", read_only=True, label="Created at")]
        if entity.access == "owner":
            tail.insert(0, EntityField(name="owner_id", type="reference", references="User", read_only=True,
                                       nullable=True, label="Owner"))
        entity.fields = system_fields + fields + tail
        valid_display = {f.name for f in entity.fields if f.type in ("string", "email", "enum", "integer", "text")}
        if entity.display_field not in valid_display:
            entity.display_field = next((f.name for f in fields if f.type in ("string", "email")), "id")

    # Order entities so referenced entities come first (needed by migrations and forms).
    ordered: List[DatabaseEntity] = []
    remaining = list(entities)
    for _ in range(len(entities) + 1):
        for entity in list(remaining):
            deps = {f.references for f in entity.fields if f.references and f.references not in ("User", entity.name)}
            if deps <= {e.name for e in ordered}:
                ordered.append(entity)
                remaining.remove(entity)
    ordered.extend(remaining)  # cycles (rare): keep order; DB agent uses deferred FK creation
    data.database_entities = [_user_entity(data.user_roles)] + ordered

    data.tech_stack = data.tech_stack or TechStack()
    data.requires_auth = True
    _derive_documentation(data)
    return data


def _derive_documentation(data: PMOutput) -> None:
    """Fill features, modules, requirements, dependencies and plan when missing."""
    app_entities = [e for e in data.database_entities if not e.is_system]
    role_names = ", ".join(r.name for r in data.user_roles)

    features: List[str] = list(dict.fromkeys(f for f in (data.features or []) if f))
    generated = ["User registration and login (JWT authentication)", f"Role-based access control ({role_names})"]
    for e in app_entities:
        plural = humanize(pluralize(to_snake(e.name))).lower()
        generated.append(f"{humanize(e.name)} management: create, view, edit and delete {plural}")
        if any(f.searchable for f in e.fields):
            generated.append(f"Search {plural}")
        for f in e.fields:
            if f.type == "enum":
                generated.append(f"Filter {plural} by {f.label.lower()}")
            if f.type == "reference" and f.references != "User":
                generated.append(f"Assign {plural} to a {humanize(f.references).lower()}")
    if data.has_admin_dashboard:
        generated.append("Admin dashboard with statistics and user management")
    for g in generated:
        if g not in features:
            features.append(g)
    data.features = features

    if not data.modules:
        data.modules = ["Authentication & Users"] + [f"{humanize(e.name)} Management" for e in app_entities]
        if data.has_admin_dashboard:
            data.modules.append("Admin Dashboard")

    if not data.functional_requirements:
        reqs = []
        for i, feat in enumerate(features, start=1):
            module = "Authentication & Users" if ("login" in feat.lower() or "role" in feat.lower()) else (
                "Admin Dashboard" if "admin" in feat.lower() else next(
                    (f"{humanize(e.name)} Management" for e in app_entities
                     if humanize(pluralize(to_snake(e.name))).lower() in feat.lower() or humanize(e.name) in feat), None))
            reqs.append(Requirement(id=f"FR-{i:03d}", title=feat, description=feat, priority="must", module=module))
        data.functional_requirements = reqs

    if not data.non_functional_requirements:
        data.non_functional_requirements = [
            Requirement(id="NFR-001", title="Security", description="Passwords hashed with PBKDF2-SHA256; stateless JWT (HS256) sessions; role checks on every protected endpoint."),
            Requirement(id="NFR-002", title="Data integrity", description="Server-side validation of all inputs, foreign key constraints and per-user data isolation."),
            Requirement(id="NFR-003", title="Performance", description="Paginated list endpoints and indexed foreign keys."),
            Requirement(id="NFR-004", title="Usability", description="Responsive React interface with search, filters and form validation feedback."),
            Requirement(id="NFR-005", title="Portability", description="PostgreSQL in Docker Compose for deployment; SQLite fallback for local preview."),
            Requirement(id="NFR-006", title="Testability", description="Automated API tests generated and executed for every entity and the auth flow."),
        ]

    if not data.dependencies:
        deps = []
        for e in app_entities:
            for f in e.fields:
                if f.type == "reference" and f.references and f.references != "User":
                    deps.append(f"{e.name} depends on {f.references} ({f.name})")
            if e.access == "owner":
                deps.append(f"{e.name} records are owned by a User")
        deps.append("All protected modules depend on Authentication")
        data.dependencies = deps

    if not data.development_plan:
        data.development_plan = [
            DevelopmentTask(step=1, agent="pm", description="Analyse the prompt and produce structured requirements"),
            DevelopmentTask(step=2, agent="ui", description="Design pages and navigation; generate the React frontend", depends_on=["pm"]),
            DevelopmentTask(step=3, agent="backend", description="Design REST API contracts; generate FastAPI routers and schemas", depends_on=["pm", "ui"]),
            DevelopmentTask(step=4, agent="db", description="Design the relational schema; generate SQLAlchemy models and PostgreSQL migration", depends_on=["pm", "backend"]),
            DevelopmentTask(step=5, agent="auth", description="Implement registration, login, JWT and RBAC", depends_on=["pm", "backend", "db"]),
            DevelopmentTask(step=6, agent="qa", description="Generate and execute tests; build the frontend; report", depends_on=["ui", "backend", "db", "auth"]),
            DevelopmentTask(step=7, agent="deploy", description="Generate Docker/Compose config, validate env and run a health check", depends_on=["qa"]),
        ]
