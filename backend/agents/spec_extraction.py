"""Prompt-driven application specification extraction (the PM agent's deterministic mode).

Every module, entity, field, status, role, rule and dashboard metric in the specification is
derived from the user's prompt:

* structure: markdown headings, numbered/bulleted module lists and their sub-bullets, sentences;
* modules:   "<X> Management" titles, list items, "with A, B and C" enumerations;
* entities:  module nouns, enumerations, objects of record-keeping verbs ("register patients"),
             explicit model lists ("create patient, doctor ... models"), compounds ("fuel records");
* fields:    "<entity> with name, age, ..." / "by selecting a patient, doctor, date and time";
* statuses:  "track available, occupied and maintenance beds", "... with X, Y and Z statuses";
* roles:     role sections ("Doctor: access to patients ..."), "for <people>", "<people> can ...";
* rules:     "prevent duplicate bookings for the same doctor and time slot", low stock, expiry, ...;
* metrics:   dashboard asks ("today's appointments", "available beds", "monthly revenue");
* negation:  "replace Products with ...", "do not show X", descriptions of the current state.

No entity or module is ever added unless the prompt asks for it. ``attribute_lexicon`` only
enriches requested entities (typical attributes/relations); unknown domains are handled generically.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from backend.agents import attribute_lexicon as lex
from backend.codegen.naming import humanize, pluralize, safe_identifier, singularize, to_pascal, to_snake
from backend.schemas.pm_schema import (
    BusinessRule,
    DashboardMetric,
    DatabaseEntity,
    EntityField,
    ModuleSpec,
    PMOutput,
    RolePermission,
    TraceItem,
    UserRole,
)

DETERMINERS = {"a", "an", "the", "their", "its", "his", "her", "our", "your", "my", "all", "any", "each", "every",
               "new", "existing", "proper", "complete", "full", "basic", "simple", "various", "different", "multiple",
               "relevant", "appropriate", "related", "specific", "own", "separate", "individual", "same", "other",
               "functional", "detailed", "custom", "dedicated", "this", "that", "these", "those", "some", "both"}
CONNECTORS = {"and", "or", "&", "plus", "as well as"}
PREPOSITIONS = {"for", "of", "in", "on", "at", "by", "to", "from", "with", "within", "under", "per", "about",
                "between", "into", "across", "via", "after", "before", "during", "without", "through", "like",
                "than", "including", "such", "as", "using", "where", "when", "which", "that", "who", "so", "if"}
CREATE_VERBS = {"register", "add", "create", "record", "log", "book", "schedule", "manage", "maintain", "store",
                "generate", "issue", "admit", "enroll", "enrol", "submit", "upload", "publish", "post", "place",
                "request", "plan", "organize", "organise", "keep", "capture", "file", "raise", "hire", "onboard",
                "enter", "define", "document", "assign", "list", "catalog", "catalogue", "sell", "rent", "lend",
                "borrow", "dispatch", "process", "handle", "track", "save"}
WEAK_VERBS = {"track", "handle", "process", "list"}  # objects only promoted when no module entity exists
# Clauses inside enumerations ("recruiters post job openings, candidates apply, and interviews are scheduled"):
# verbs that can follow a plural subject, the record an intransitive verb implies, and plurals that are not subjects.
CLAUSE_VERBS = CREATE_VERBS | {"use", "apply", "approve", "reject", "review", "rate", "pay", "order", "return",
                               "attend", "treat", "prescribe", "teach", "visit", "join", "receive", "send", "write",
                               "make", "buy", "deliver", "ship", "inspect", "repair", "sign", "update", "view",
                               "browse", "check", "complete", "own", "run", "host", "comment", "vote", "bid",
                               "donate", "subscribe", "collect", "complain", "need", "have", "belong", "contain",
                               "grade", "mark", "assess", "evaluate", "supervise", "learn", "study", "choose",
                               "select", "earn", "redeem", "lease", "train", "lead", "share", "follow", "invite",
                               "accept", "decline", "cancel", "confirm", "reserve", "purchase", "transfer", "withdraw",
                               "deposit", "claim", "verify", "monitor", "measure", "diagnose", "dispense", "administer",
                               "vaccinate", "groom", "drive", "ride", "load", "pack", "scan", "audit", "allocate",
                               "rank", "nominate", "elect", "read", "watch", "take", "give", "find", "search"}
EVENT_OF_VERB = {"apply": "application", "enroll": "enrollment", "enrol": "enrolment", "subscribe": "subscription",
                 "donate": "donation", "book": "booking", "order": "order", "pay": "payment", "rent": "rental",
                 "review": "review", "rate": "rating", "vote": "vote", "bid": "bid", "complain": "complaint",
                 "borrow": "loan"}
FIELD_ONLY_HEADS = {"name", "title", "date", "time", "status", "amount", "price", "cost", "fee", "number", "id", "email",
                    "phone", "address", "age", "gender", "description", "note", "quantity", "qty", "level", "type",
                    "size", "area", "detail", "photo", "image", "total", "balance", "score", "rating"}
NOT_CLAUSE_SUBJECTS = {"sales", "goods", "news", "series", "species", "analytics", "logistics", "statistics", "status",
                       "details", "settings", "records", "logs", "reports", "users"}
PASSIVE_CLAUSE = re.compile(
    r"^(?:the\s+)?([a-z][a-z -]*?)\s+(?:is|are|was|were|gets?|can be|will be|should be|must be|has been|have been)\s+"
    r"(?:also\s+|then\s+|automatically\s+)?([a-z]+ed|made|paid|sent|kept|held|sold|built|shown|done|given|taken|"
    r"written|set)\b(.*)$")
COLLECTION_HEADS = {"inventory", "list", "catalog", "catalogue", "details", "detail", "information", "info", "data",
                    "profile", "profiles", "database", "directory", "register", "stock", "listing", "listings", "collection"}
FEATURE_HEADS = {"search", "searching", "sorting", "filtering", "registration", "login", "logins", "authentication",
                 "authorization", "pagination", "validation", "navigation", "notification", "notifications",
                 "integration", "integrations", "export", "import", "upload", "uploads", "download", "printing",
                 "permissions", "settings", "functionality", "features", "feature", "support", "access", "control",
                 "controls", "page", "pages", "screen", "screens", "dashboard", "dashboards", "analytics"}
NOMINALIZATION_THINGS = {"location", "station", "position", "question", "collection", "medication", "institution",
                         "organization", "organisation", "nation", "section", "mission", "option", "edition", "version",
                         "solution", "publication", "profession", "division", "portion", "ration", "lotion", "potion",
                         "television", "vision", "commission", "condition", "description", "specification", "notification",
                         "equation", "foundation", "union", "region", "religion", "session", "pension", "mansion"}
LEADIN_VERBS = {"display", "show", "include", "manage", "track", "allow", "create", "list", "view", "enter", "record",
                "provide", "support", "generate", "implement", "use", "monitor", "maintain"}
CRUD_NOUNS = {"creation", "editing", "deletion", "removal", "viewing", "creating", "deleting", "browsing"}
ACTION_NOUNS = CRUD_NOUNS | {"listing", "management", "tracking", "scheduling", "categorization"}
PLURAL_CLASSIFIERS = {"category", "tag", "group", "brand", "genre", "label", "collection"}
HISTORY_HEADS = {"history", "histories"}
RECORD_ALIASES = {"activity", "activities", "record", "records", "log", "logs", "event", "events", "session", "sessions",
                  "entry", "entries"}  # "irrigation activities" are the irrigation records themselves
MONEY_HEADS = {"expense", "cost", "wage", "fee", "charge", "spending", "salary", "bill", "payment"}
ACTIVE_WORDS = {"active", "current", "currently", "employed", "working", "ongoing", "operational", "running"}  # "order history" -> order (only when that entity exists)
CLASSIFIER_HEADS = {"category", "type", "tag", "group", "kind", "brand", "genre"}  # "product categories" -> category
# presentation vocabulary: never data entities ("sidebar navigation", "statistics cards", "clean blue theme")
UI_HEADS = {"theme", "themes", "layout", "layouts", "navigation", "sidebar", "navbar", "bar", "card", "cards", "chart",
            "charts", "table", "tables", "form", "forms", "button", "buttons", "filter", "filters", "modal", "modals",
            "header", "footer", "design", "style", "styles", "color", "colors", "colour", "colours", "font", "fonts",
            "typography", "icon", "icons", "animation", "animations", "mockup", "component", "components", "mode",
            "ui", "ux", "toast", "toasts", "banner", "hero", "spacing", "background", "homepage", "storefront",
            "photography", "screen", "screens", "view", "views", "menu", "menus", "widget", "widgets", "grid",
            "control", "controls", "graph", "graphs", "states", "messages", "look", "feel", "palette", "accent"}
DESIGN_ONLY = {"loading", "success", "error", "errors", "state", "states", "empty", "warning", "warnings",
               "requirement", "requirements", "theme", "themes", "layout", "layouts", "navigation", "sidebar", "navbar", "button", "buttons", "modal",
               "modals", "header", "footer", "typography", "font", "fonts", "icon", "icons", "animation", "animations",
               "mockup", "component", "components", "toast", "toasts", "banner", "hero", "spacing", "background",
               "homepage", "storefront", "photography", "widget", "widgets", "palette", "accent", "ui", "ux", "chart",
               "charts", "graph", "graphs", "filter", "filters", "look", "feel"}
UI_ADJECTIVES = {"interactive", "responsive", "modern", "professional", "clean", "elegant", "premium", "polished",
                 "attractive", "beautiful", "minimal", "minimalist", "light", "dark", "top", "side", "main", "reusable",
                 "promotional", "statistics", "summary", "empty", "loading", "searchable", "filterable", "sortable",
                 "mobile", "desktop", "intuitive", "sleek", "consistent", "accessible", "friendly", "healthcare"}
# leading state/participle adjectives: "assigned doctors", "available beds", "featured products" -> the noun
STATE_ADJECTIVES = {"upcoming", "available", "pending", "active", "current", "recent", "todays", "today's", "total",
                    "admitted", "assigned", "occupied", "overdue", "expired", "completed", "cancelled", "canceled",
                    "open", "closed", "inactive", "featured", "popular", "latest", "selected", "registered",
                    "scheduled", "unpaid", "paid", "outstanding", "archived", "approved", "rejected"}
EVENT_HEADS = {"activity", "usage", "consumption", "application", "fine", "penalty", "donation", "expense", "claim", "refund", "visit", "reading", "check", "checkup", "inspection", "report", "log", "record", "request", "entry",
               "harvest", "sale", "payment", "assessment", "evaluation", "observation", "measurement", "treatment",
               "session", "transaction", "incident", "admission", "booking", "reservation", "delivery", "trip",
               "submission", "attendance", "appointment", "order", "loan", "rental", "shipment", "survey", "audit"}
IMPERATIVE_START = re.compile(r"^(?:implement|build|create|add|provide|include|support|develop|enable|design|set up|"
                              r"introduce|offer)\b", re.I)
VERB_START = {"divide", "split", "monitor", "select", "choose", "pick", "calculate", "compute", "verify", "start",
              "allow", "use", "ensure", "display", "show", "make", "support", "provide", "keep", "do", "don't", "generate",
              "connect", "redesign", "remove", "replace", "inspect", "review", "run", "start", "verify", "analyze",
              "analyse", "let", "enable", "give", "send", "store", "track", "record", "register", "manage", "book",
              "add", "create", "maintain", "update", "edit", "delete", "view", "search", "filter", "sort", "list", "log",
              "assign", "admit", "issue", "schedule", "calculate", "compute", "prevent", "avoid", "never", "always",
              "each", "every", "users", "user", "admins", "admin", "it", "this", "the", "all", "there", "we", "i"}
STATE_SYNONYMS = {"upcoming": "scheduled", "canceled": "cancelled", "in_process": "in_progress", "finished": "completed"}
IMPERATIVE_WORDS = {"implement", "build", "create", "add", "provide", "include", "support", "develop", "enable", "design",
                    "introduce", "offer", "functional", "proper"}
CONTROL_VERBS = {"add", "remove", "edit", "delete", "update", "view", "create", "save", "cancel", "search", "sort",
                 "filter", "filtering", "sorting", "searching", "select", "selection"}
RECORD_HEADS = {"record", "log", "report", "request", "entry", "note", "update", "result", "sale", "order", "item",
                "assignment", "harvest", "inspection", "reading", "visit", "booking", "reservation", "payment"}
GENERIC_NOISE_HEADS = {"update", "updates", "change", "changes", "operation", "operations", "activity", "activities",
                       "statistic", "statistics", "trend", "trends", "chart", "charts", "summary", "overview"}
MODULE_SUFFIXES = {"management", "module", "modules", "system", "section", "handling", "administration", "admin",
                   "tracking", "tracker", "operations", "center", "centre", "portal", "workflow", "workflows",
                   "page", "pages", "screen", "area", "panel", "feature", "features"}
APP_NOUNS = r"(?:management system|management app|management application|management platform|management software|management tool|system|app|application|platform|website|web app|site|portal|tool|software|tracker|solution|marketplace|store|shop|dashboard|manager)"
META_HEADING = re.compile(r"\b(technical|technolog\w*|tech stack|stack|design\w*|ui|ux|styl\w*|theme\w*|instructions?|"
                          r"notes?|deliverables?|constraints?|deployment|testing|important|generation|layout|"
                          r"look and feel|branding|non-functional|nonfunctional|guidelines|general|architecture|final)\b", re.I)
TECH_WORDS = {"api", "apis", "rest", "restful", "database", "databases", "db", "crud", "endpoint", "endpoints",
              "frontend", "backend", "server", "jwt", "sql", "postgresql", "postgres", "react", "fastapi", "schema",
              "schemas", "typescript", "tailwind", "css", "html", "javascript", "python", "docker", "orm", "json",
              "http", "url", "repository", "repo", "codebase", "folder", "deployment", "infrastructure"}
ROLE_HEADING = re.compile(r"\b(roles?|user types?|actors?|permissions?|access control|access levels?|users? and)\b", re.I)
DASHBOARD_HEADING = re.compile(r"\bdashboard\b", re.I)
REPORT_HEADING = re.compile(r"\breports?\b|\breporting\b|\banalytics\b", re.I)
SKIP_SENTENCE = re.compile(r"\b(looks like|currently|the current application|current app|is not the|was not|"
                           r"are not the|existing (?:frontend|backend|project|code|application|app|infrastructure))\b", re.I)
NEGATIVE_CUE = re.compile(r"\b(do not|don't|never|avoid|remove|unrelated|irrelevant|instead of|rather than|without)\b", re.I)
UNSUPPORTED = [
    (r"\bprint(?:able|ing)?\b", "Printable documents (e.g. printable invoices)"),
    (r"\b(?:file|image|photo|document)s?\s+upload|\bupload(?:s|ing)?\b|\battachments?\b", "File/image uploads"),
    (r"\b(?:stripe|paypal|payment gateway|online payments?|card processing)\b", "Online payment processing"),
    (r"\b(?:email|e-mail|sms|push)\s+(?:notifications?|alerts?|reminders?)\b|\bnotifications?\b", "Email/SMS/push notifications"),
    (r"\b(?:real[- ]time chat|chat|messaging)\b", "Real-time chat/messaging"),
    (r"\b(?:gps|live map|maps?\b|geolocation|real[- ]time tracking)\b", "Maps/GPS tracking"),
    (r"\b(?:video|streaming)\b", "Video/streaming"),
    (r"\b(?:recommendations?|machine learning|ai[- ]powered|predict(?:ion|ive))\b", "AI recommendations/predictions"),
    (r"\b(?:pdf|excel)\b", "PDF/Excel export"),
    (r"\b(?:multi[- ]?language|i18n|translation|localization)\b", "Multi-language support"),
    (r"\bpassword (?:reset|recovery)\b|\bforgot password\b|\bemail verification\b", "Password recovery / email verification"),
    (r"\b(?:storefront|landing page|hero banner|marketing (?:site|page))\b", "Public storefront / marketing landing page design"),
    (r"\bcheckout\b", "Checkout flow that converts cart contents into order lines"),
]
ATTRIBUTE_ENUMERATIONS = {"deadline", "progress", "progress tracking", "priority", "status", "due date"}
DEMO_DATA = re.compile(r"\b(sample|demo|seed|synthetic|dummy|mock|example|realistic|test)\s+(data|records|entries)\b", re.I)

ROLE_ACTION_WORDS = [
    (re.compile(r"\bfull (?:system )?access\b|\ball (?:modules|features|access)\b|\beverything\b|\bsuper\s?user\b", re.I), {"read", "create", "update", "delete"}),
    (re.compile(r"\b(update|edit|modify|change|correct)\b(?!.*\b(?:manage|create|add|register|record)\b)", re.I), {"read", "update"}),
    (re.compile(r"\b(manage|management|register|registration|create|add|book|booking|record|recording|maintain|issue|schedule|admit|admission|process|handle|submit|request|raise|report|place|apply|enrol|enroll|log|order)\b", re.I), {"read", "create", "update"}),
    (re.compile(r"\b(access|view|see|read|browse|monitor|check)\b", re.I), {"read"}),
]


class PromptValidationError(ValueError):
    """Raised when a prompt is empty, too vague or does not describe an application."""


# ----------------------------------------------------------------------------------------------
# text utilities
# ----------------------------------------------------------------------------------------------

def _strip_markup(text: str) -> str:
    text = re.sub(r"(?m)^(\s*)[*+]\s+", r"\1- ", text)  # "* item" bullets survive the emphasis removal below
    text = re.sub(r"[*_`]{1,3}", "", text)
    text = text.replace("—", " - ").replace("–", " - ").replace("’", "'").replace("“", '"').replace("”", '"')
    return text


def _words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z0-9'+-]*", text)


def _singular_phrase(words: List[str]) -> str:
    if not words:
        return ""
    return " ".join(words[:-1] + [singularize(words[-1])])


def _key(phrase: str) -> str:
    return to_snake(_singular_phrase(phrase.lower().split()))


def _split_list(text: str) -> List[str]:
    """Split an enumeration 'a, b, and c' / 'a; b; c' / 'a or b' into items."""
    text = re.sub(r"\(.*?\)", " ", text)
    parts = re.split(r"\s*(?:,|;|/|\band/or\b|\band\b|\bor\b|&|\bas well as\b|\bplus\b)\s*", text)
    return [p.strip(" .:-") for p in parts if p and p.strip(" .:-")]


def _clean_phrase(phrase: str) -> List[str]:
    """Lower-case content words of a noun phrase (drops determiners, possessives, numbers)."""
    words = [w.lower().strip("'") for w in _words(phrase)]
    words = [re.sub(r"'s$", "", w) for w in words]
    while words and (words[0] in DETERMINERS or words[0] in CONNECTORS or words[0] in PREPOSITIONS):
        words = words[1:]
    return [w for w in words if w and w not in DETERMINERS]


def _cut_at_preposition(words: List[str]) -> List[str]:
    for i, w in enumerate(words):
        if w in PREPOSITIONS and i > 0:
            return words[:i]
    return words


def _sentences(text: str) -> List[str]:
    text = re.sub(r"\b(e\.g|i\.e|etc|vs)\.", lambda m: m.group(1), text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])|\n+", text)
    return [p.strip() for p in parts if p and p.strip()]


def _ui_word(word: str) -> bool:
    return word in UI_HEADS or word in UI_ADJECTIVES or word in lex.COLOR_WORDS or word in GENERIC_NOISE_HEADS


def is_design_sentence(sentence: str) -> bool:
    """Sentences about look and feel ("clean blue-and-white theme, sidebar navigation, statistics cards")."""
    words = [w.lower() for w in _words(sentence)]
    if re.search(r"\b(theme|typography|look and feel|colou?r scheme|palette|font|spacing)\b", sentence, re.I):
        return True
    return sum(1 for w in words if w in UI_HEADS or w in lex.COLOR_WORDS) >= 3


def _is_person_noun(word: str) -> bool:
    w = singularize(word.lower())
    if w.endswith(("ment", "ent_list")) or w in {"comment", "content", "event", "intent", "parent_company"}:
        return False
    return (len(w) > 3 and w.endswith(lex.PERSON_SUFFIXES) and w not in lex.NOT_PEOPLE) or w in {
        "staff", "admin", "administrator", "nurse", "clerk", "chef", "guest", "patient", "student", "client",
        "customer", "member", "parent", "tenant", "resident", "coach", "athlete", "volunteer", "agent", "vet",
        "candidate", "applicant", "pupil", "pilot"}


def _clause(item: str) -> Optional[Tuple[List[str], str, str, bool]]:
    """Read an enumeration item that is a clause, not a noun phrase.

    'candidates apply' -> (['candidates'], 'apply', '', False); 'experiments use samples' -> (..., 'samples', False);
    'results are recorded' -> (['results'], 'recorded', '', True). Noun phrases ('purchase orders', 'sales report')
    return None: the subject must be a plural noun and, unless it names people, the verb needs an object.
    """
    low = re.sub(r"\s+", " ", item.strip().lower()).strip(" .!?")
    pm = PASSIVE_CLAUSE.match(low)
    if pm:
        subject = _cut_at_preposition(_clean_phrase(pm.group(1)))
        return (subject, pm.group(2), pm.group(3).strip(), True) if subject else None
    words = low.split()
    for i in range(1, min(len(words), 4)):
        verb, last = words[i], words[i - 1]
        if verb not in CLAUSE_VERBS or last in NOT_CLAUSE_SUBJECTS:
            continue
        plural = (last.endswith("s") and not last.endswith("ss") and singularize(last) != last) or last in {
            "staff", "people", "personnel"}
        subject = _clean_phrase(" ".join(words[:i]))
        if not plural or not subject or any(w in PREPOSITIONS or w in CLAUSE_VERBS for w in subject):
            continue
        rest = " ".join(words[i + 1:])
        if rest.split()[:1] in (["off"], ["up"], ["out"]) or (
                rest.split()[:1] == ["in"] and verb in {"check", "log", "sign", "hand", "fill", "drop"}):
            rest = " ".join(rest.split()[1:])  # "technicians sign off tasks", "staff check guests in"
        if not rest and not _is_person_noun(subject[-1]):
            continue  # "sales order", "assets register": a noun phrase after all
        return subject, verb, rest, False
    return None


# ----------------------------------------------------------------------------------------------
# document structure
# ----------------------------------------------------------------------------------------------

@dataclass
class Block:
    title: str                  # module/item title (may be empty for plain sentences)
    body: List[str]             # sentences belonging to this block (title remainder + sub-bullets)
    section: str                # nearest heading text
    kind: str                   # module | role | meta | dashboard | reports | text
    is_section: bool = False    # a numbered section title ("3. Farm Management") owning the bullets below it
    noun_items: List[Tuple[str, str]] = field(default_factory=list)  # (lead-in, noun-phrase bullet): field lists
    raw_items: List[str] = field(default_factory=list)               # bullets as written (role lines)


def _parse_blocks(text: str) -> List[Block]:
    lines = text.splitlines()
    blocks: List[Block] = []
    section = ""
    current: Optional[Block] = None
    current_indent = -1

    def section_kind(heading: str) -> str:
        if ROLE_HEADING.search(heading):
            return "role"
        if META_HEADING.search(heading):
            return "meta"
        return "module"

    numbered: Optional[Block] = None   # the numbered section currently collecting bullets
    leadin = ""
    blank_before = True
    for raw in lines:
        if not raw.strip():
            blank_before = True
            continue
        indent = len(raw) - len(raw.lstrip(" \t"))
        line = raw.strip()
        was_blank, blank_before = blank_before, False
        heading = re.match(r"^#{1,6}\s*(.+)$", line)
        is_marker = re.match(r"^([-*•+]|\d+[.)])\s", line)
        lead_word = (_words(line) or [""])[0].lower()
        known_heading = lead_word not in CREATE_VERBS | IMPERATIVE_WORDS | LEADIN_VERBS and bool(
            ROLE_HEADING.search(line) or META_HEADING.search(line) or DASHBOARD_HEADING.search(line)
            or (REPORT_HEADING.search(line) and len(_words(line)) <= 3))
        if not heading and numbered is not None and len(line) < 60 and line.endswith(":") and not is_marker                 and not known_heading:
            leadin = line[:-1].strip()  # "Display:", "Allow users to:", "Manage:" inside a numbered section
            continue
        title_line = (was_blank and not is_marker and len(line) < 50 and not re.search(r"[.!?:;,]$", line)
                      and len(_words(line)) <= 6 and line[:1].isupper() and not re.search(r"[.!?]\s", line))
        if heading or title_line or (len(line) < 60 and line.endswith(":") and not is_marker):
            section = (heading.group(1) if heading else line.rstrip(":")).strip()
            current, numbered, leadin = None, None, ""
            current_indent = -1
            continue
        item = re.match(r"^(?:[-*•+]|\d+[.)]|[a-z][.)])\s+(.*)$", line)
        content = item.group(1).strip() if item else line
        kind = section_kind(section) if section else "module"
        bullet = bool(item) and bool(re.match(r"^[-*•+]\s", line))
        number_title = (bool(item) and not bullet and len(content) < 60 and ":" not in content
                        and not re.search(r"[.!?]$", content))
        if number_title:
            current = Block(title=content, body=[], section=section, kind=kind, is_section=True)
            numbered, leadin, current_indent = current, "", indent
            blocks.append(current)
            continue
        if numbered is not None and (bullet or (not item and not was_blank)):
            numbered.raw_items.append(content)
            first_word = (_words(content) or [""])[0].lower()
            starts_with_verb = first_word in VERB_START or first_word in CREATE_VERBS or first_word in IMPERATIVE_WORDS
            if bullet and not starts_with_verb and len(_words(content)) <= 6 and not re.search(r"[:;]", content):
                numbered.noun_items.append((leadin, content.rstrip(".!")))
            else:
                numbered.body.extend(_sentences(content))
            continue
        if numbered is not None and not item:
            numbered, leadin = None, ""  # a paragraph after a blank line ends the numbered section
        if item and not bullet:
            numbered, leadin = None, ""
        if item and (current is None or indent <= current_indent):
            title, _, rest = content.partition(":")
            if not rest and " - " in content and len(content.split(" - ")[0]) < 50:
                title, _, rest = content.partition(" - ")
            single = len(_sentences(content)) == 1
            first = (_words(content) or [""])[0].lower()
            if rest and len(title) < 60:
                current = Block(title=title.strip(), body=_sentences(rest), section=section, kind=kind)
            elif len(content) < 60 and not re.search(r"[.!?]$", content):
                current = Block(title=content, body=[], section=section, kind=kind)
            elif single and IMPERATIVE_START.match(content) and len(content) < 200 and not re.search(
                    r"\b(?:so that|which|that|when|where|if)\b", content, re.I):
                # "Implement Room and Bed Management with available, occupied ... statuses."
                current = Block(title=content.rstrip(".!"), body=[], section=section, kind=kind)
            elif single and len(content) < 90 and first not in VERB_START and not re.search(
                    r"\b(?:should|must|can|will|is|are|be)\b", content, re.I):
                # noun-phrase items: "Product categories and featured products."
                current = Block(title=content.rstrip(".!"), body=[], section=section, kind=kind)
            else:
                current = Block(title="", body=_sentences(content), section=section, kind=kind)
            current_indent = indent
            blocks.append(current)
        elif item and current is not None:
            current.body.extend(_sentences(content))
        else:
            for sentence in _sentences(content):
                blocks.append(Block(title="", body=[sentence], section=section, kind=kind))
            current = None
            current_indent = -1
    for b in blocks:
        title_l = b.title.lower()
        if b.is_section and b.kind == "module":
            if ROLE_HEADING.search(title_l):
                b.kind = "role"
            elif META_HEADING.search(title_l) and not DASHBOARD_HEADING.search(title_l):
                b.kind = "meta"
        if b.is_section and b.kind == "dashboard" or (b.is_section and DASHBOARD_HEADING.search(title_l)):
            b.kind = "dashboard"
            b.body = b.body + [f"{lead} {noun[:1].lower() + noun[1:]}".strip() for lead, noun in b.noun_items]
            b.noun_items = []
            continue
        if b.kind == "module" and b.title:
            if DASHBOARD_HEADING.search(title_l):
                b.kind = "dashboard"
            elif REPORT_HEADING.search(title_l) and len(_clean_phrase(title_l)) <= 3:
                b.kind = "reports"
        if b.kind in ("role", "module") and not b.title and b.body:
            # "Dashboard: display total books, ..." written as a plain line under any heading
            head, _, rest = b.body[0].partition(":")
            if rest and len(head) < 30 and DASHBOARD_HEADING.search(head) and len(_clean_phrase(head)) <= 2:
                b.title, b.body, b.kind = head.strip(), _sentences(rest) + b.body[1:], "dashboard"
                continue
        if b.kind == "role" and not b.title and b.body:
            title, _, rest = b.body[0].partition(":")
            if rest and len(title) < 40:
                b.title, b.body = title.strip(), _sentences(rest) + b.body[1:]
        if b.kind == "role" and b.title and (DASHBOARD_HEADING.search(b.title) or REPORT_HEADING.search(b.title)):
            b.kind = "dashboard" if DASHBOARD_HEADING.search(b.title) else "reports"
    return blocks


# ----------------------------------------------------------------------------------------------
# extraction state
# ----------------------------------------------------------------------------------------------

@dataclass
class FieldDraft:
    name: str
    type: str
    values: List[str] = field(default_factory=list)
    required: bool = False
    unique: bool = False
    searchable: bool = False
    references: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    label: Optional[str] = None
    explicit: bool = True


@dataclass
class EntityDraft:
    key: str
    sources: List[str] = field(default_factory=list)
    fields: Dict[str, FieldDraft] = field(default_factory=dict)
    statuses: List[str] = field(default_factory=list)
    subtypes: List[str] = field(default_factory=list)
    refs: Set[str] = field(default_factory=set)
    modules: List[str] = field(default_factory=list)
    order: int = 0
    explicit_status: bool = False

    @property
    def name(self) -> str:
        return to_pascal(self.key)


class Extraction:
    def __init__(self, text: str):
        self.text = text
        self.lower = text.lower()
        self.entities: Dict[str, EntityDraft] = {}
        self.negative: Set[str] = set()
        self.modules: List[ModuleSpec] = []
        self.roles: Dict[str, Dict] = {}
        self.target_users: List[str] = []
        self.rules: List[BusinessRule] = []
        self.metric_phrases: List[str] = []
        self.attribute_asks: List[str] = []
        self.pending_attributes: List[str] = []
        self.consumed: Set[str] = set()  # sentences whose lists were used as statuses/fields
        self.clause_roles: Dict[str, Dict] = {}  # people acting in sentences; used when no roles are declared
        self.seed: Dict[str, List[str]] = {}
        self.ambiguities: List[str] = []
        self.trace: List[TraceItem] = []
        self.counter = 0
        self.domain_words: List[str] = []
        self.wants_reports = False
        self.wants_dashboard = False

    # ------------------------------------------------------------------ entities
    def resolve(self, phrase_words: List[str], allow_new: bool = True, source: str = "") -> Optional[str]:
        """Map a noun phrase to an entity key (existing or new). Returns None for non-entities."""
        phrase_words = list(phrase_words)
        while len(phrase_words) > 1 and phrase_words[-1] in ACTION_NOUNS:
            phrase_words = phrase_words[:-1]  # "task creation", "task editing" -> task
        if len(phrase_words) == 1 and phrase_words[0] in ACTION_NOUNS:
            return None
        if len(phrase_words) == 1 and phrase_words[0].endswith("s") and singularize(phrase_words[0]) in PLURAL_CLASSIFIERS:
            head = singularize(phrase_words[0])  # a listed "categories"/"tags" module is a record of its own
            if head in self.entities:
                return head
            if allow_new and head not in self.negative:
                self.entities[head] = EntityDraft(key=head, order=len(self.entities), sources=[source] if source else [])
                return head
            return None
        words = [w for w in phrase_words if w not in MODULE_SUFFIXES or len(phrase_words) == 1]
        stripped = [w for w in words if w not in self.domain_words] or words
        if stripped != words:  # "hospital departments" -> department, but "reef sites" stays a reef site
            base = to_snake(_singular_phrase(stripped))
            known = base in self.entities or base in lex.TYPICAL_ATTRIBUTES or base in lex.MODULE_RECORDS
            words = stripped if known else words
        while len(words) > 1 and (words[0] in STATE_ADJECTIVES or words[0] in UI_ADJECTIVES or (
                words[0].endswith("ed") and to_snake(_singular_phrase(words[1:])) in self.entities)):
            words = words[1:]
        if not words or any(w in TECH_WORDS for w in words):
            return None
        phrase = " ".join(words)
        if phrase in lex.FEATURE_WORDS or singularize(phrase) in lex.FEATURE_WORDS:
            return None
        if words[-1] in lex.COLOR_WORDS or (len(words) == 1 and words[0] in DESIGN_ONLY) or (
                len(words) > 1 and words[-1] in UI_HEADS and all(_ui_word(w) for w in words[:-1])):
            return None
        if len(words) > 1 and words[-1] in FEATURE_HEADS:
            return None  # "product search", "user registration"
        head = singularize(words[-1])
        if len(words) > 1 and words[-1] in HISTORY_HEADS:
            base = to_snake(_singular_phrase(words[:-1]))
            base = lex.MODULE_RECORDS.get(base, [base])[0]
            return base if base in self.entities else None
        if len(words) == 2 and head in CLASSIFIER_HEADS:  # "product categories" -> category (relation added by caller)
            if head in self.entities:
                return head
            if not allow_new or head in self.negative:
                return None
            self.entities[head] = EntityDraft(key=head, order=len(self.entities), sources=[source] if source else [])
            return head
        key = to_snake(_singular_phrase(words))
        # module/activity nouns -> the record they manage ("billing" -> invoice)
        for candidate in (key, to_snake(phrase), head):
            if candidate in lex.MODULE_RECORDS and (len(words) == 1 or candidate == key):
                key = lex.MODULE_RECORDS[candidate][0]
                head = key.split("_")[-1]
                words = key.split("_")
                break
        if key in self.entities:
            return key
        if head in self.entities and len(words) > 1 and words[0] in self.entities:
            return head  # "patient invoices" -> invoice (relation added by caller)
        if len(words) > 1 and words[-1] in COLLECTION_HEADS | {"records"} and to_snake(_singular_phrase(words[:-1])) in self.entities:
            return to_snake(_singular_phrase(words[:-1]))  # "patient records" -> patient
        if len(words) > 1 and head in COLLECTION_HEADS:
            words = words[:-1]
            key = to_snake(_singular_phrase(words))
            head = singularize(words[-1])
            if key in self.entities:
                return key
        if len(words) > 1 and words[-1] in RECORD_ALIASES:
            base = to_snake(_singular_phrase(words[:-1]))
            if base in self.entities and _event_like(base):
                return base  # "irrigation activities/history/records" -> the irrigation records
            twin = next((k for k in self.entities if k.endswith("_" + head) and k != key
                         and k.split("_")[0] in set(self.entities) | set(self.domain_words) | {words[0]}), None)
            if twin and (words[0] in self.entities or singularize(words[0]) in self.entities):
                return twin  # "farm activities" when "field activities" already exist
        noise = head in GENERIC_NOISE_HEADS and not (len(words) > 1 and head in ("activity",) and words[0] not in {
            "recent", "latest", "user", "system", "all", "daily", "my"})
        if head in lex.ATTRIBUTE_HEADS or noise or phrase in lex.FEATURE_WORDS:
            return None
        if len(words) > 3:
            words = words[-2:]
            key = to_snake(_singular_phrase(words))
        if key in self.negative or head in self.negative:
            return None
        if allow_new and len(words) == 1:
            twins = [k for k in self.entities if k.endswith("_" + key)]
            if len(twins) == 1:
                return twins[0]  # "receptionists book appointments" after "vet appointments": the same records
        if not allow_new or len(key) < 3:
            return None
        self.entities[key] = EntityDraft(key=key, order=len(self.entities), sources=[source] if source else [])
        return key

    def add_entity(self, phrase: str, source: str, allow_new: bool = True, module: Optional[str] = None) -> Optional[str]:
        words = _cut_at_preposition(_clean_phrase(phrase))
        if not words:
            return None
        key = self.resolve(words, allow_new=allow_new, source=source)
        if key:
            ent = self.entities[key]
            if source and source not in ent.sources:
                ent.sources.append(source)
            if module and module not in ent.modules:
                ent.modules.append(module)
            # compound modifier that is another entity -> relation ("patient invoices")
            if len(words) > 1:
                modifier = to_snake(singularize(words[0]))
                if modifier in self.entities and modifier != key:
                    if key in CLASSIFIER_HEADS or (_event_like(modifier) and not _event_like(key)):
                        self.entities[modifier].refs.add(key)  # products belong to a category; irrigation uses a system
                    else:
                        ent.refs.add(modifier)
        return key

    # ------------------------------------------------------------------ fields
    def add_field(self, entity: str, phrase: str) -> None:
        ent = self.entities.get(entity)
        if ent is None:
            return
        count = re.match(r"^\s*(?:the\s+|total\s+)?number\s+of\s+([a-z][a-z ]*)$", phrase.strip().lower())
        if count:  # "number of copies" -> copies (integer)
            name = safe_identifier("_".join(_cut_at_preposition(_clean_phrase(count.group(1)))))
            if name:
                ent.fields.setdefault(name, FieldDraft(name, "integer", min_value=0, label=humanize(name).capitalize()))
                return
        words = _cut_at_preposition(_clean_phrase(phrase))
        if not words:
            return
        text = " ".join(words)
        if text in {"contact details", "contact information", "contact info", "contact"}:
            for f in (FieldDraft("phone", "string", label="Phone"), FieldDraft("email", "email", label="Email")):
                ent.fields.setdefault(f.name, f)
            return
        if text in {"date and time", "date time"}:
            self.add_field(entity, "date")
            self.add_field(entity, "time")
            return
        # references: "patient", "selecting a doctor", "assigned doctor", "doctor name"
        ref_words = [w for w in words if w not in {"selection", "name", "id", "details", "assigned", "selected", "responsible",
                                                   "assignment", "allocation", "reference", "link"}]
        if ref_words:
            ref_key = to_snake(_singular_phrase(ref_words))
            if ref_key in self.entities and ref_key != entity:
                ent.refs.add(ref_key)
                return
            if len(ref_words) == 1 and singularize(ref_words[0]) in self.entities and singularize(ref_words[0]) != entity:
                ent.refs.add(singularize(ref_words[0]))
                return
        fd = infer_field(words, ent.key)
        if fd is None:
            return
        if fd.name == "status":
            ent.explicit_status = ent.explicit_status or bool(fd.values)
            if fd.values:
                ent.statuses = fd.values
            elif not ent.statuses:
                ent.statuses = []
            ent.fields.setdefault("status", fd)
            return
        ent.fields.setdefault(fd.name, fd)

    def set_statuses(self, entity: str, values: List[str], source: str) -> None:
        ent = self.entities.get(entity)
        if not ent:
            return
        cleaned = [STATE_SYNONYMS.get(to_snake(v), to_snake(v)) for v in values if v and len(v) < 30]
        cleaned = [v for v in dict.fromkeys(cleaned) if v]
        if len(cleaned) >= 2 and self.plausible_states(values):
            ent.statuses = cleaned
            ent.explicit_status = True
            ent.fields["status"] = FieldDraft("status", "enum", values=cleaned, required=True, label="Status")
            self.trace_item("rule", f"{humanize(entity)} statuses: {', '.join(cleaned)}", [f"{to_pascal(entity)}.status"], source)

    def plausible_states(self, values: List[str]) -> bool:
        """'available, occupied, reserved' are states; 'patient selection, date, time' are fields."""
        for v in values:
            words = [w for w in v.lower().split() if w not in ("and", "or")]
            if not words or len(words) > 2:
                return False
            if words[0] in PREPOSITIONS and len(words) == 2:
                continue  # "in progress", "on hold", "in use"
            if _is_person_noun(words[-1]):
                return False  # "nurses, receptionists and administrative staff" are kinds of people
            if any(w in lex.ATTRIBUTE_HEADS or w in UI_HEADS for w in words):
                return False
        return len(values) >= 2

    def trace_item(self, kind: str, text: str, targets: List[str], source: str = "", status: str = "mapped") -> None:
        self.counter += 1
        self.trace.append(TraceItem(id=f"REQ-{self.counter:03d}", text=(source or text)[:300], kind=kind, targets=targets,
                                    status=status))


# ----------------------------------------------------------------------------------------------
# field inference (generic lexical rules)
# ----------------------------------------------------------------------------------------------

def infer_field(words: List[str], entity_key: str) -> Optional[FieldDraft]:
    words = [w for w in words if w not in UI_HEADS or w in {"time", "type"}] or words
    text = " ".join(words)
    if not words or text in {"details", "information", "info", "data", "record", "records", "profile", "profiles"}:
        return None
    if words[-1] in {"details", "information", "info"} and len(words) > 1 and not set(words[:-1]) & set(entity_key.split("_")) \
            and not _is_person_noun(words[-2]):
        name = safe_identifier("_".join(words[:-1]))  # "ownership details" -> ownership
        return FieldDraft(name, "text", searchable=True, label=humanize(name).capitalize())
    if words[-1] in {"details", "information", "info", "data", "profile", "profiles"} or text in CONTROL_VERBS:
        return None  # "employee details" (the record itself), "add"/"remove" controls
    if words[-1] in {"dashboard", "admin", "panel", "login", "registration", "authentication", "page", "pages"} or \
            any(w in {"dashboard", "panel", "login", "authentication"} for w in words):
        return None
    entity_words = entity_key.split("_")
    trimmed = [w for w in words if w not in entity_words] or words
    plural_name = safe_identifier("_".join(trimmed))
    name = safe_identifier("_".join(trimmed[:-1] + [singularize(trimmed[-1])]))  # "prices" -> price
    label = humanize(name)
    singular_words = [singularize(w) for w in words]
    has = lambda *opts: any(o in words or o in singular_words for o in opts) or any(text.endswith(o) for o in opts)  # noqa: E731

    if has("status", "state", "stage"):
        qualifiers = [w for w in trimmed if w not in ("status", "state", "stage", "statuses", "current", "overall",
                                                      "operating", "operational", "record", "workflow")]
        if qualifiers and trimmed[-1] in ("status", "stage", "state"):  # "growth stage", "health status"
            known = lex.KNOWN_VALUE_SETS.get(plural_name)
            if known:
                return FieldDraft(plural_name, "enum", values=list(known), label=humanize(plural_name).capitalize())
            return FieldDraft(plural_name, "string", searchable=True, label=humanize(plural_name).capitalize())
        return FieldDraft("status", "enum", label="Status")
    for known, values in lex.KNOWN_VALUE_SETS.items():
        if name == known or text.replace(" ", "_") == known:
            return FieldDraft(known, "enum", values=list(values), label=humanize(known))
    if has("email", "e-mail"):
        return FieldDraft("email", "email", label="Email")
    if has("phone", "mobile", "telephone") or text in {"contact number", "phone number"}:
        return FieldDraft("phone", "string", label="Phone")
    if has("balance", "outstanding", "due amount") or text in {"pending balance", "pending amount"}:
        return FieldDraft("balance", "decimal", label="Balance")
    if has("price", "cost", "amount", "fee", "fees", "salary", "revenue", "budget", "charge", "charges", "fare", "wage",
           "total", "paid", "tax", "discount", "value", "expense", "expenses", "spending") and not has("number", "count", "date"):
        return FieldDraft(name if name not in {"total", "paid", "value"} else f"{name}_amount", "decimal", min_value=0, label=label)
    if has("age"):
        return FieldDraft("age", "integer", min_value=0, max_value=150, label="Age")
    if has("quantity", "qty", "stock", "count", "capacity", "seats", "units", "copies") or text.startswith("number of"):
        return FieldDraft(name, "integer", min_value=0, label=label)
    if has("progress", "percentage", "percent"):
        return FieldDraft("progress", "integer", min_value=0, max_value=100, label="Progress (%)")
    if has("score", "marks", "points", "rating"):
        return FieldDraft(name, "integer", min_value=0, label=label)
    if has("year"):
        return FieldDraft(name, "integer", min_value=1900, label=label)
    if has("weight", "height", "distance", "km", "kilometers", "miles", "liters", "litres", "mileage", "kg", "temperature",
           "area", "acreage", "acres", "hectares", "size", "production", "yield", "output", "volume", "usage", "consumption") \
            and not has("history", "notes", "description", "details", "remarks"):
        return FieldDraft(name, "float", min_value=0, label=label)
    if has("deadline", "due") and not has("amount"):
        return FieldDraft("due_date", "date", label="Due date")
    if has("expiry", "expiration"):
        return FieldDraft("expiry_date", "date", label="Expiry date")
    if has("datetime", "timestamp") or (has("time") and has("date")):
        return FieldDraft(name, "datetime", label=label)
    if has("date", "dob", "birthday", "day") or text in {"birth date", "date of birth"}:
        fname = name if name != "date" else f"{entity_key}_date"
        fname = "date_of_birth" if "birth" in text or "dob" in text else fname
        return FieldDraft(fname, "date", label=humanize(fname).capitalize())
    if has("time", "slot"):
        fname = name if name not in {"time", "time_slot", "slot"} else f"{entity_key}_time"
        return FieldDraft(fname, "time", label=label if name not in {"time", "time_slot", "slot"} else "Time")
    if has("availability") and len(trimmed) > 1 and not _is_person_noun(trimmed[0]):
        return FieldDraft(name, "float", min_value=0, label=label)
    if has("availability", "available", "active", "enabled", "published") or words[0] in {"is", "has"}:
        base = "available" if has("availability", "available") else trimmed[-1]
        return FieldDraft(f"is_{base}", "boolean", label=humanize(base).capitalize())
    if has("history", "notes", "note", "description", "remarks", "comments", "address", "instructions", "summary",
           "boundary", "boundaries",
           "diagnosis", "findings", "result", "results", "bio", "biography", "content", "body", "symptoms", "treatment"):
        tname = plural_name if trimmed[-1] in {"notes", "findings", "symptoms", "instructions", "remarks", "results",
                                                "comments"} else name
        return FieldDraft(tname, "text", searchable=True, label=humanize(tname))
    if has("image", "photo", "picture", "url", "link", "website", "logo"):
        return FieldDraft(name if name.endswith("url") else f"{name}_url", "string", label=label)
    searchable = has("name", "title", "number", "code", "specialization", "designation", "category", "type", "location")
    return FieldDraft(name, "string", searchable=searchable, unique=has("code", "sku", "isbn", "serial", "registration"),
                      label=label)


# ----------------------------------------------------------------------------------------------
# main extraction
# ----------------------------------------------------------------------------------------------

def validate_prompt(prompt: Optional[str]) -> str:
    text = (prompt or "").strip()
    if not text:
        raise PromptValidationError("The prompt is empty. Describe the application you want FORGE AI to build.")
    words = re.findall(r"[A-Za-z][A-Za-z'-]*", text)
    if len(text) < 15 or len(words) < 4:
        raise PromptValidationError(
            "The prompt is too short to derive requirements. Describe the application, who uses it and its main "
            "features, e.g. 'Build a task manager with login, task categories and an admin dashboard'.")
    if len(text) > 20000:
        raise PromptValidationError("The prompt is longer than 20,000 characters; summarise the main requirements.")
    vowelless = [w for w in words if len(w) > 3 and not re.search(r"[aeiouyAEIOUY]", w)]
    if len(vowelless) > len(words) / 2:
        raise PromptValidationError("The prompt does not look like a natural-language description of an application.")
    return text


def _domain(ex: Extraction, text: str) -> Tuple[str, str]:
    """Return (project name, app type) derived from the prompt itself."""
    name = None
    m = re.search(r"\b(?:named|called|titled|name it|brand(?:ed)? as)\s+[\"']?([A-Z0-9][\w&' -]{1,70}?)[\"']?(?=[,.;:!\n]|\s+(?:with|that|for|which|and|to)\b|$)", text)
    subtitle = ""
    if m:
        name = re.sub(r"\s+", " ", m.group(1).strip(" '\""))
        if " - " in name:  # "AgriTrack - Smart Farm Management System": brand + description
            name, subtitle = (part.strip() for part in name.split(" - ", 1))
    if not name:  # "Analyze the existing MediCare Hospital project and correct it"
        m = re.search(r"\b(?:existing|current|the|our|my)\s+([A-Z][\w&'-]*(?:\s+[A-Z][\w&'-]*){0,4})\s+"
                      r"(?:project|application|app|website|platform|site)\b", text)
        if m and m.group(1).lower() not in {"the", "this"}:
            name = m.group(1).strip()
    m = re.search(r"\b(?:build|create|make|develop|design|generate|implement)\s+(?:me\s+)?(?:(?:a|an|the)\s+)?((?:[\w-]+\s+){0,5}?)" + APP_NOUNS + r"\b",
                  text, re.I)
    domain_phrase = ""
    app_noun = ""
    sm = re.search(r"((?:[\w-]+\s+){1,4}?)" + APP_NOUNS + r"\b", subtitle, re.I) if subtitle else None
    if sm:  # the brand's description names the domain ("Smart Farm Management System")
        domain_phrase, app_noun = sm.group(1).strip(), subtitle[sm.end(1):sm.end()].strip()
    elif m:
        domain_phrase = m.group(1).strip()
        app_noun = text[m.end(1):m.end()].strip()
    else:  # "This is not the requested Hospital Management System" (skip descriptions of the current state)
        for sentence in _sentences(text):
            if re.search(r"\b(looks like|currently|current (?:application|app|project)|generic|instead of|rather than)\b",
                         sentence, re.I):
                continue
            fm = re.search(r"((?:[A-Za-z-]+\s+){1,3}?)(management system|management app|management application|"
                           r"management platform|booking system|tracking system|tracker|marketplace)\b", sentence, re.I)
            if fm:
                words = [w for w in _words(fm.group(1)) if w.lower() not in DETERMINERS | {
                    "requested", "actual", "real", "is", "not", "this", "a", "an", "the"}]
                domain_phrase = " ".join(words[-2:])
                app_noun = fm.group(2)
                break
    domain_words = [w.lower() for w in _words(domain_phrase)
                    if w.lower() not in DETERMINERS | {"modern", "responsive", "full-stack", "fullstack", "web", "mobile", "smart",
                                                        "online", "complete", "multi-specialty", "professional", "small",
                                                        "simple", "basic", "secure", "beautiful", "premium", "smart"}]
    ex.domain_words = [singularize(w) for w in domain_words if w not in {"management"}]
    app_type = to_snake(" ".join(domain_words) or "custom") or "custom"
    if not name and not domain_words and app_noun and domain_phrase:  # "an online store" -> Online Store
        name = " ".join(w.capitalize() for w in _words(domain_phrase)) + " " + " ".join(w.capitalize() for w in app_noun.split())
    if not name:
        if domain_words:
            name = " ".join("-".join(p.capitalize() for p in w.split("-")) for w in domain_words)
            noun = " ".join(w.capitalize() for w in app_noun.split()) if app_noun else ""
            if noun and noun.lower() not in name.lower():
                name = f"{name} {noun}"
        else:
            name = ""
    return name.strip(), app_type


def _negative_mentions(ex: Extraction, sentence: str) -> None:
    low = sentence.lower()
    for m in re.finditer(r"\breplace\s+(.+?)\s+with\b", low):
        for item in _split_list(m.group(1)):
            words = _clean_phrase(item)
            if words:
                ex.negative.add(to_snake(_singular_phrase(words)))
    for m in re.finditer(r"\b(?:remove|instead of|rather than|unrelated|irrelevant|not show|not display|not include|avoid)\s+(.+?)(?:[.;]|$)", low):
        for item in _split_list(m.group(1)):
            words = _cut_at_preposition(_clean_phrase(item))
            if words and len(words) <= 3:
                ex.negative.add(to_snake(_singular_phrase(words)))


def _module_title_entities(ex: Extraction, title: str, source: str) -> Tuple[str, List[str], Optional[str]]:
    """'Admission and Bed Management' -> ('admission_and_bed', [admission, bed], statuses-hint)."""
    clean = re.sub(r"\(.*?\)", "", title)
    clean = re.sub(r"^(?:implement|build|create|add|provide|include|support|develop|enable|design|set up|introduce|offer)"
                   r"\s+(?:a\s+|an\s+|the\s+)?(?:(?:functional|proper|complete|full|basic|simple|dedicated|separate)\s+)*",
                   "", clean, flags=re.I)
    status_hint = None
    m = re.search(r"\bwith\s+(.+?)\s+status(?:es)?\b", clean, re.I)
    if m and ex.plausible_states(_split_list(m.group(1))):
        status_hint = m.group(1)
    before_with = re.split(r"\b(?:with|for|to|that|including|so)\b", clean, maxsplit=1, flags=re.I)[0]
    with_part = ""
    wm = re.search(r"\b(?:with|including|covering)\s+(.+)$", clean, re.I)
    if wm and not status_hint:
        with_part = wm.group(1)
    words = _clean_phrase(before_with)
    words = [w for w in words if w not in MODULE_SUFFIXES]
    if not words:
        return "", [], status_hint
    entities = []
    workflow = bool(re.search(r"\bworkflows?\b", clean, re.I))
    for part in re.split(r"\s+(?:and|&)\s+|,\s*", " ".join(words)):
        part_words = [w for w in part.split() if w]
        if not part_words:
            continue
        if workflow and len(entities) >= 1:
            continue  # "Admission and Discharge workflows": discharge is a state of the admission
        rest = [w for w in part_words if w not in ex.domain_words] or part_words
        if rest[-1] in {"report", "reports", "reporting", "analytics"}:
            ex.wants_reports = True  # "Hospital Reports" -> the reports page
            continue
        key = ex.add_entity(" ".join(part_words), source)
        if key and key not in entities:
            entities.append(key)
    # "Doctor Management with doctor profiles, specializations, departments, and availability"
    if with_part and entities:
        own_words = {w for k in entities for w in k.split("_")}
        for item in _split_list(with_part):
            iw = [w for w in _clean_phrase(item) if w not in UI_HEADS or w in {"time", "type"}]
            if iw and iw[-1] in {"tracking", "management"} and len(iw) > 1:
                iw = iw[:-1]
            if not iw or " ".join(iw) in CONTROL_VERBS:
                continue
            if ex.resolve(list(iw), allow_new=False) in entities:
                continue  # the module's own records ("invoices" in Billing, "doctor profiles")
            if iw[-1] in RECORD_HEADS | COLLECTION_HEADS | {"requests", "records"} and any(
                    singularize(w) in own_words for w in iw[:-1]):
                continue  # "test requests" in Laboratory
            ex.add_field(entities[0], " ".join(iw))
    return "_".join(words), entities, status_hint


def _module_label(ex: Extraction, title_words: List[str], module_entities: List[str]) -> str:
    """Navigation label in the user's terminology: 'Pharmacy', 'Billing & Payments', 'Admissions & Beds'."""
    if not title_words or len(title_words) > 6:
        return " & ".join(humanize(pluralize(k)).capitalize() for k in module_entities[:3])
    labels = []
    for part in re.split(r"\s+(?:and|&)\s+", " ".join(title_words)):
        words = [w for w in part.split() if w not in ex.domain_words] or part.split()
        if words[-1] in {"report", "reports", "reporting", "analytics"}:
            continue  # the reports page is its own module
        key = to_snake(_singular_phrase(words))
        if key in ex.entities:
            labels.append(humanize(pluralize(key)))  # the entity itself -> plural ("Patients")
        else:
            labels.append(" ".join(words))           # the user's own word ("Pharmacy", "Billing")
    labels = [l for l in dict.fromkeys(labels) if l]
    return " & ".join(l[:1].upper() + l[1:] for l in labels)[:40]


def _note_role(ex: Extraction, word: str, mention: str) -> None:
    """People who act in a sentence ('receptionists book appointments') are user roles of the app."""
    word = re.sub(r"[^a-z]", "", word.lower())
    noun = to_snake(singularize(word))
    if not word or not _is_person_noun(word) or noun in {"user", "person", "people", "customer_user"}:
        return
    noun = "admin" if noun == "administrator" else noun
    role = ex.clause_roles.setdefault(noun, {"description": "", "is_admin": noun.startswith("admin"), "mentions": ""})
    role["mentions"] = (role["mentions"] + " " + mention).strip()


def _clause_entities(ex: Extraction, item: str, source: str, allow_new: bool,
                     previous: Optional[str] = None) -> Optional[List[str]]:
    """Records (and roles) named by a clause in an enumeration; None when the item is a plain noun phrase.

    'candidates apply' -> candidate + application (and a candidate role); 'experiments use samples' -> experiment
    (referencing sample); 'results are recorded' -> result; 'vets record vaccinations' -> vet role + vaccination.
    `previous` is the record listed just before ("post job openings, candidates apply": applications are for them).
    """
    parsed = _clause(item)
    if parsed is None:
        return None
    subject, verb, rest, passive = parsed
    with_part = re.search(r"\bwith\s+(.+)$", rest)
    obj_text = re.split(r"\b(?:for|from|to|of|in|on|into|across|per|between|with|by|at|when|where|after|before)\b",
                        rest)[0].strip() if rest else ""
    objects = [o for o in _split_list(obj_text) if _clean_phrase(o)] if obj_text and not passive else []
    # "students enroll in courses", "candidates apply for jobs": the thing after the preposition is a record too
    pobj = re.match(r"^(?:in|for|to|on|at|into)\s+(.+)$", rest) if not passive and not objects else None
    pobj_text = re.split(r"\b(?:for|from|to|of|in|on|into|with|by|at|when|where)\b", pobj.group(1))[0].strip() \
        if pobj else ""
    keys: List[str] = []

    def add(phrase: str, recorded: bool = False) -> Optional[str]:
        key = ex.add_entity(phrase, source, allow_new=allow_new)
        if key is None and recorded and allow_new:
            # "results are recorded", "candidates apply" (-> applications): the clause itself says these are records,
            # even though 'result', 'location' or 'application' usually name a field or the app
            words = _cut_at_preposition(_clean_phrase(phrase))
            words = words[-3:]
            if words and not any(w in TECH_WORDS or _ui_word(w) for w in words) and \
                    singularize(words[-1]) not in FIELD_ONLY_HEADS:
                key = to_snake(_singular_phrase(words))
                if key in ex.negative or len(key) < 3:
                    key = None
                elif key not in ex.entities:
                    ex.entities[key] = EntityDraft(key=key, order=len(ex.entities), sources=[source] if source else [])
        if key and key not in keys:
            keys.append(key)
        return key

    if passive:
        subject_key = add(" ".join(subject), recorded=subject[-1] not in {"user", "users"})
        by = re.search(r"\bby\s+([a-z ]+)$", rest)
        if by and _clean_phrase(by.group(1)):
            _note_role(ex, _clean_phrase(by.group(1))[-1], f"{verb} {' '.join(subject)}")
    elif _is_person_noun(subject[-1]):
        _note_role(ex, subject[-1], f"{verb} {obj_text}".strip())
        subject_key = None
        if not objects:  # "candidates apply": the people are records too, and so is what the verb creates
            subject_key = add(" ".join(subject))
            target_key = add(pobj_text) if pobj_text and _clean_phrase(pobj_text) else None
            event = EVENT_OF_VERB.get(verb)
            event_key = add(event, recorded=True) if event else None
            for parent in (subject_key, target_key or previous):
                if event_key and parent and parent in ex.entities and parent != event_key:
                    ex.entities[event_key].refs.add(parent)
        for o in objects:
            add(o)
    else:
        subject_key = add(" ".join(subject))
        for o in objects:
            key = add(o)
            if key and subject_key and key != subject_key:
                ex.entities[subject_key].refs.add(key)  # "experiments use samples"
    if with_part and subject_key:
        for f in _split_list(with_part.group(1)):
            ex.add_field(subject_key, f)  # "interviews are scheduled with feedback"
    return keys


def _field_lists(ex: Extraction, sentence: str, context: List[str], source: str, strong: bool) -> List[str]:
    """Handle '<verb> <object> with/by selecting/including <fields>' and status lists. Returns entities touched."""
    low = sentence.lower().strip()
    touched: List[str] = []

    # "(track|display|show) available, occupied, and maintenance beds"
    m = re.search(r"\b(?:track|display|show|list|view|manage|support|filter by|with)\s+((?:[a-z-]+(?: [a-z-]+)?,\s*)+(?:and|or)\s+[a-z-]+)\s+([a-z ]+?)(?:[.;,]|$)", low)
    status_list = False
    if m:
        target = _cut_at_preposition(_clean_phrase(m.group(2)))
        values = _split_list(m.group(1))
        if target and target[-1].startswith("status"):
            tkey = context[0] if context else None
        else:
            tkey = ex.add_entity(" ".join(target), source, allow_new=False) if target else None
        if tkey and all(len(v.split()) <= 2 for v in values) and ex.plausible_states(values):
            ex.set_statuses(tkey, values, source)
            touched.append(tkey)
            status_list = True
            ex.consumed.add(sentence)  # K. a status list is not a list of modules

    # "... with available, occupied, reserved, and maintenance statuses"
    m = re.search(r"\b(?:with|has|have|having|statuses?|states?)\s*:?\s*((?:[a-z-]+(?: [a-z-]+)?,\s*)+(?:and|or)?\s*[a-z-]+(?: [a-z-]+)?)\s+(?:status(?:es)?|states?)\b", low)
    if m and context:
        ex.set_statuses(context[0], _split_list(m.group(1)), source)

    special = _special_sentence(ex, low, context, source)
    if special is not None:
        return touched + special

    # verb object + field list
    verb_pat = r"\b(" + "|".join(sorted(CREATE_VERBS | {"display", "show", "store"}, key=len, reverse=True)) + r")\s+(.+?)(?:\s+(?:with|by selecting|by choosing|including|containing|specifying|showing|having|such as)\s+(.+?))?(?:\.|;|$)"
    verb_re = re.compile(verb_pat)
    verb_matches = [verb_re.match(low, vm.start()) for vm in re.finditer(
        r"\b(?:" + "|".join(sorted(CREATE_VERBS | {"display", "show", "store"}, key=len, reverse=True)) + r")\b", low)]
    for m in verb_matches:  # every verb is considered ("create an app to track my houseplants")
        if m is None:
            continue
        verb, obj, fields = m.group(1), m.group(2), m.group(3)
        if verb == "assign" and context:
            continue  # "assign rooms and beds" references existing records (handled below)
        if re.match(r"^(?:a|an|the|my|our)?\s*(?:[\w-]+\s+){0,5}?" + APP_NOUNS + r"(?:\s*$|\s+(?:to|for|that|which|where|with)\b)", obj):
            continue  # the object is the application itself
        before = low[:m.start()].split()[-1:]
        if before and (before[0] in DETERMINERS or before[0] in {"online", "web", "e-commerce", "ecommerce", "retail",
                                                                  "grocery", "app", "data", "audit", "activity"}):
            continue  # "an online store with ...": a noun, not a verb
        if before and before[0].isalpha() and before[0].endswith("s"):
            _note_role(ex, before[0], f"{verb} {obj}")  # "receptionists book appointments"
        if verb in {"display", "show"} and not fields:
            # "display total amount, paid amount, and pending balance" -> fields of context entity
            if context and not status_list and "," in obj and not re.search(r"\b(chart|trend|statistic|report|table)", obj):
                for item in _split_list(obj):
                    ex.add_field(context[0], item)
            continue
        # objects: "patients and assign rooms and beds" -> split on 'and <verb>'
        obj = re.split(r"\s+and\s+(?=" + "|".join(CREATE_VERBS) + r")\b", obj)[0]
        obj_items = _split_list(re.split(r"\b(?:for|from|to|of|in|on|into|across|per|between)\b", obj)[0])
        if status_list:
            break  # "track available, occupied and reserved tables": states, not records
        allow_new = strong and verb not in {"display", "show"} and (verb not in WEAK_VERBS or not context)
        keys: List[str] = []
        existing_before = set(ex.entities)
        # "tractors, harvesters, pumps, and other agricultural equipment" -> equipment with a category
        if len(obj_items) >= 3 and re.match(r"^(?:other|similar)\s+", obj_items[-1]):
            rest = re.sub(r"^(?:other|similar)\s+", "", obj_items[-1])
            head_words = _clean_phrase(rest)[-1:]
            parent = (ex.add_entity(" ".join(head_words), source, allow_new=False) if head_words else None) or \
                ex.add_entity(rest, source, allow_new=allow_new)  # "other agricultural equipment" -> equipment
            if parent:
                ex.entities[parent].subtypes = [to_snake(singularize(_clean_phrase(i)[-1])) for i in obj_items[:-1]
                                                if _clean_phrase(i)] + ["other"]
                touched.append(parent)
                continue
        people = [i for i in obj_items if _clean_phrase(i) and _is_person_noun(_clean_phrase(i)[-1])]
        if context and len(obj_items) >= 3 and len(people) == len(obj_items):
            last = _clean_phrase(obj_items[-1])
            ctx_ent = ex.entities.get(context[0])
            if ctx_ent and last and (singularize(last[-1]) == context[0] or last[-1] in {"staff", "personnel", "team"}):
                ctx_ent.subtypes = [to_snake(_singular_phrase(_clean_phrase(i))) for i in obj_items[:-1]] + [
                    to_snake(" ".join(last[:-1]) or "other")]
                touched.append(context[0])
                continue
        clause_target: Optional[str] = None
        for item in obj_items:
            clause_keys = _clause_entities(ex, item, source, allow_new=allow_new,
                                           previous=keys[-1] if keys else None)
            if clause_keys is not None:  # "candidates apply", "results are recorded": not record names
                keys.extend(k for k in clause_keys if k not in keys)
                clause_target = clause_keys[0] if clause_keys else clause_target
                ex.consumed.add(sentence)
                continue
            if re.match(r"^\s*(?:their|its|his|her)\b", item) and (keys or context):
                ex.add_field((keys or context)[0], item)  # "houseplants and their watering schedule"
                continue
            words = _clean_phrase(item)
            if not words:
                continue
            if words[-1] in COLLECTION_HEADS | {"details", "information"} and context and verb in {"store", "maintain", "keep", "manage"}:
                cand = to_snake(_singular_phrase(words[:-1])) if len(words) > 1 else ""
                if cand and cand not in ex.entities and _is_person_noun(cand.split("_")[-1]):
                    keys.append(context[0])
                    continue
            if words[-1] in HISTORY_HEADS and len(words) > 1 and ex.resolve(list(words), allow_new=False):
                key = ex.resolve(list(words), allow_new=False)
                if key and key not in keys:
                    keys.append(key)
                continue
            if (words[-1] in lex.ATTRIBUTE_HEADS or singularize(words[-1]) in lex.ATTRIBUTE_HEADS) and context:
                ex.add_field(context[0], item)
                continue
            if not allow_new and context and verb in WEAK_VERBS:
                head = to_snake(_singular_phrase(words))
                if _event_like(head) and ex.resolve(list(words), allow_new=False) is None:
                    allow_new = True  # "track attendance", "track water usage": records of their own
            key = ex.add_entity(item, source, allow_new=allow_new)
            if key:
                keys.append(key)
        for key in keys:
            if key not in touched:
                touched.append(key)
        if fields and keys:
            ex.consumed.add(sentence)
            target = clause_target or keys[0]  # "... and interviews are scheduled with feedback" -> interview
            for item in _split_list(fields):
                ex.add_field(target, item)
        # recording an existing record inside an event module links them ("record harvested crops" in Harvests)
        if context and _event_like(context[0]):
            for key in list(keys):
                if key != context[0] and key in ex.entities and key in existing_before:
                    ex.entities[context[0]].refs.add(key)
                    if key in touched:
                        touched.remove(key)
        # "assign rooms and beds" after "admit patients" -> context entity references them
        for am in re.finditer(r"\bassign(?:ed|s|ing)?\s+(?!.*\bto\b)(.+?)(?:\.|;|$)", low):
            for item in _split_list(am.group(1)):
                rk = ex.add_entity(item, source, allow_new=False)
                if rk and context and rk != context[0]:
                    ex.entities[context[0]].refs.add(rk)
    # bare field lists: "Record admission date, assigned doctor, and discharge date."
    m = re.match(r"^(?:record|capture|store|include|log|enter)\s+(.+)$", low)
    if m and context and "," in m.group(1) and not re.search(r"\b(?:with|by selecting|including)\b", m.group(1)):
        items = _split_list(m.group(1))
        if all(_clean_phrase(i) and (_clean_phrase(i)[-1] in lex.ATTRIBUTE_HEADS or to_snake(_singular_phrase(_clean_phrase(i)[-1:])) in ex.entities or "assigned" in i) for i in items):
            for item in items:
                ex.add_field(context[0], item)
    return touched


def _noun_items(ex: Extraction, b: Block, module_entities: List[str], module: Optional[ModuleSpec]) -> None:
    """Noun-phrase bullets of a numbered section: a field list, or categories of a money record."""
    items = [(lead, noun) for lead, noun in b.noun_items if usable_noun(noun)]
    if not items:
        return
    if any(re.search(r"\breports?\b", lead, re.I) for lead, _ in items):
        ex.wants_reports = True  # "Create reports for: crop production, ..."
        return
    heads = [singularize(_clean_phrase(n)[-1]) for _, n in items if _clean_phrase(n)]
    money = [h for h in heads if h in MONEY_HEADS]
    if len(money) >= 3 and len(money) >= len(heads) / 2:
        # "Seed expenses, Fertilizer expenses, Worker wages, ..." -> one money record with a category
        main = max(set(money), key=money.count)
        target = next((k for k in module_entities if k.split("_")[-1] == main), None) or (
            module_entities[0] if module_entities else ex.add_entity(main, b.title))
        if not target:
            return
        categories = []
        for _, noun in items:
            words = _clean_phrase(noun)
            head = singularize(words[-1]) if words else ""
            if head not in MONEY_HEADS:
                ex.metric_phrases.append(noun)  # "Crop sales revenue", "Profit and loss" are figures, not categories
                continue
            words = words[:-1] if head in ("expense", "cost", "charge", "fee", "spending") and len(words) > 1 else words
            categories.append(to_snake(" ".join(words)))
        ent = ex.entities[target]
        ent.subtypes = list(dict.fromkeys(categories))
        for name, kind in (("amount", "decimal"), (f"{target.split('_')[-1]}_date", "date"), ("description", "text")):
            ent.fields.setdefault(name, FieldDraft(name, kind, required=name == "amount", min_value=0 if kind == "decimal" else None,
                                                   label=humanize(name).capitalize()))
        if module is not None and target not in module.entities:
            module.entities.insert(0, target)
        ex.trace_item("field", f"{humanize(target)} categories", [f"{to_pascal(target)}.category"], b.title)
        return
    if not module_entities:
        return
    for _, noun in items:  # "Crop name", "Planting date", "Field assignment", "Growth stage" ...
        ex.add_field(module_entities[0], noun)


def usable_noun(noun: str) -> bool:
    return not re.search(r"\b(?:must|should|will|can|is|are|be)\b", noun, re.I) and len(_words(noun)) <= 6


def _special_sentence(ex: Extraction, low: str, context: List[str], source: str) -> Optional[List[str]]:
    """Sentence shapes with a fixed meaning. Returns the touched records, or None when not one of them."""
    # "generate water consumption reports" -> the reports page, not a record
    if re.match(r"^\s*(?:generate|create|produce|export|view|provide)\b.*\breports?\b", low):
        ex.wants_reports = True
        return []
    # "divide farms into individual fields" -> a field belongs to a farm
    m = re.search(r"\b(?:divide|split|break|organi[sz]e|group)\s+(.+?)\s+into\s+(?:individual\s+|separate\s+|multiple\s+|smaller\s+)?(.+?)(?:[.;,]|$)", low)
    if m:
        parent = ex.add_entity(m.group(1), source, allow_new=True)
        child = ex.add_entity(m.group(2), source, allow_new=True)
        if parent and child and parent != child:
            ex.entities[child].refs.add(parent)
            return [child]
    # "view field boundaries and cultivation status" / "monitor water availability" -> attributes
    m = re.match(r"^\s*(?:view|see|monitor|display|show|check)\s+(.+?)(?:[.;]|$)", low)
    if m and context and "," not in m.group(1):
        items = _split_list(m.group(1))
        attr_like = lambda w: singularize(w[-1]) in lex.ATTRIBUTE_HEADS or w[-1] in lex.ATTRIBUTE_HEADS or \
            w[-1] in ("availability", "boundaries", "boundary", "progress", "status", "usage", "levels")  # noqa: E731
        cleaned = [_clean_phrase(i) for i in items]
        if cleaned and all(c and attr_like(c) for c in cleaned):
            owner = context[0]
            for words in cleaned:
                maybe = to_snake(singularize(words[0])) if len(words) > 1 else ""
                owner = maybe if maybe in ex.entities else owner
                ex.add_field(owner, " ".join(words[1:]) if maybe in ex.entities else " ".join(words))
            return []
    # "select farm and field" -> the record references them
    m = re.match(r"^\s*(?:select|choose|pick|link(?: to)?|associate with)\s+(?:a\s+|the\s+)?(.+?)(?:[.;]|$)", low)
    if m and context:
        for item in _split_list(m.group(1)):
            ref = ex.add_entity(item, source, allow_new=False)
            if ref and ref != context[0]:
                ex.entities[context[0]].refs.add(ref)
            elif not ref:
                ex.add_field(context[0], item)
        return []
    # "assign workers to farms and activities" / "assign applications to specific fields and crops"
    m = re.search(r"\bassign\s+(.+?)\s+to\s+(?:specific\s+|the\s+|their\s+)?(.+?)(?:[.;]|$)", low)
    if m and context:
        subject = ex.add_entity(m.group(1), source, allow_new=False) or context[0]
        for item in _split_list(m.group(2)):
            target = ex.add_entity(item, source, allow_new=False)
            if not target or target == subject:
                continue
            if _event_like(target) and not _event_like(subject):
                ex.entities[target].refs.add(subject)   # an activity has its assigned worker
            else:
                ex.entities[subject].refs.add(target)   # a worker belongs to a farm; an application to a field
        return []
    # "provide crop lifecycle tracking from planting to harvesting" -> crop states planted -> harvested
    m = re.search(r"\b(?:lifecycle|life cycle|life-cycle|progress|workflow)\b.*?\bfrom\s+([a-z]+)\s+to\s+([a-z]+)", low)
    if m:
        target = None
        before = low[:m.start()]
        for word in reversed(_words(before + " " + low[m.start():m.end()])):
            target = ex.add_entity(word, source, allow_new=False)
            if target:
                break
        target = target or (context[0] if context else None)
        if target:
            ex.set_statuses(target, [_state_of(m.group(1)), _state_of(m.group(2))], source)
        return []
    return None


def _state_of(word: str) -> str:
    """'planting' -> planted, 'harvesting' -> harvested, 'admission' -> admitted."""
    verb = _nominal_to_verb(word)
    if verb in lex.VERB_STATES:
        return lex.VERB_STATES[verb]
    base = re.sub(r"ing$", "", word.lower())
    return base + ("d" if base.endswith("e") else "ed")


def _rules_from_sentence(ex: Extraction, sentence: str, context: List[str], source: str) -> None:
    low = sentence.lower()
    m = re.search(r"\b(?:prevent|avoid|no|disallow|block|stop)\s+(?:duplicate|double|overlapping|conflicting)\s+([a-z ]+?)\s+(?:for|with|on|at)\s+(?:the\s+)?same\s+(.+?)(?:[.;]|$)", low)
    if m:
        target = ex.add_entity(m.group(1), source, allow_new=False) or (context[0] if context else None)
        if target:
            for item in _split_list(m.group(2)):
                ref = ex.add_entity(item, source, allow_new=False)
                if ref and ref != target:
                    ex.entities[target].refs.add(ref)
            ex.rules.append(BusinessRule(id=f"rule_{len(ex.rules) + 1}", kind="unique_together", entity=to_pascal(target),
                                         fields=_split_list(m.group(2)), description=sentence.strip(), source=sentence.strip()))
    if re.search(r"\blow[- ]stock\b|\breorder\b|\brunning low\b|\bout of stock\b", low):
        ex.rules.append(BusinessRule(id=f"rule_{len(ex.rules) + 1}", kind="low_stock",
                                     entity=to_pascal(context[0]) if context else "", description=sentence.strip(), source=sentence.strip()))
    if re.search(r"\bexpir(?:y|ed|ing|ation)\b", low):
        ex.rules.append(BusinessRule(id=f"rule_{len(ex.rules) + 1}", kind="expiry",
                                     entity=to_pascal(context[0]) if context else "", description=sentence.strip(), source=sentence.strip()))
    if re.search(r"\boverdue\b|\bpast due\b|\blate (?:returns?|payments?)\b", low):
        if context and re.search(r"\bdue dates?\b|\bdeadlines?\b", low):
            ex.add_field(context[0], "due date")
        ex.rules.append(BusinessRule(id=f"rule_{len(ex.rules) + 1}", kind="overdue",
                                     entity=to_pascal(context[0]) if context else "", description=sentence.strip(), source=sentence.strip()))
    m = re.search(r"\bupdate\s+([a-z ]+?)\s+(?:availability|status)\s+(?:after|when|on)\s+(.+?)(?:[.;]|$)", low)
    if m:
        resource = ex.add_entity(m.group(1), source, allow_new=False)
        if resource:
            ex.rules.append(BusinessRule(id=f"rule_{len(ex.rules) + 1}", kind="allocation", entity="",
                                         params={"resource": to_pascal(resource)}, description=sentence.strip(), source=sentence.strip()))


def _workflow_states(ex: Extraction, sentence: str, context: List[str], source: str) -> None:
    """'Patient Admission and Discharge workflows' -> admission states [admitted, discharged]."""
    low = sentence.lower()
    m = re.search(r"\b([a-z ]+?)\s+(?:and|&)\s+([a-z]+)\s+workflows?\b", low)
    if not m:
        return
    first = _clean_phrase(m.group(1))
    while first and (first[0] in CREATE_VERBS or first[0] in IMPERATIVE_WORDS):
        first = first[1:]
    first = first[-2:]
    if not first:
        return
    key = ex.add_entity(" ".join(first), source, allow_new=True)
    if not key:
        return
    states = []
    for word in (first[-1], m.group(2)):
        verb = _nominal_to_verb(word)
        if verb in lex.VERB_STATES:
            states.append(lex.VERB_STATES[verb])
    if len(states) >= 2:
        ex.set_statuses(key, states, source)


def _nominal_to_verb(word: str) -> str:
    word = singularize(word.lower())
    candidates = [word, re.sub(r"ion$", "", word), re.sub(r"sion$", "t", word), re.sub(r"al$", "e", word),
                  re.sub(r"ment$", "", word), re.sub(r"ing$", "", word), re.sub(r"ing$", "e", word), re.sub(r"ance$", "", word)]
    for c in candidates:
        if c in lex.VERB_STATES:
            return c
    return word


def _roles(ex: Extraction, blocks: List[Block]) -> None:
    for b in blocks:
        if b.kind == "role" and b.is_section:  # "13. User Roles" followed by "Admin: Full access" lines
            for line in b.raw_items or b.body:
                head, _, rest = line.partition(":")
                words = _clean_phrase(head)
                if not rest or not words or len(words) > 3:
                    continue
                role = to_snake(_singular_phrase(words))
                role = "admin" if role in ("administrator", "admin") else role
                is_admin = role == "admin" or bool(re.search(r"\bfull (?:system |application )?access\b", rest, re.I))
                ex.roles[role] = {"description": rest.strip()[:200], "is_admin": is_admin, "mentions": rest}
            continue
        if b.kind != "role" or not b.title:
            continue
        words = _clean_phrase(b.title)
        if not words or len(words) > 3:
            continue
        role = to_snake(singularize(words[-1]) if len(words) == 1 else _singular_phrase(words))
        desc = " ".join(b.body)
        is_admin = role in {"admin", "administrator", "super_admin", "superadmin"} or bool(re.search(r"\bfull (?:system )?access\b|\ball (?:modules|features)\b", desc, re.I))
        if role == "administrator":
            role = "admin"
        ex.roles[role] = {"description": desc[:200], "is_admin": is_admin, "mentions": desc}
    # inline: "roles: admin, teacher and student" / "for admins, teachers and students"
    for m in re.finditer(r"\broles?\s*(?::|include|are|such as|like|for)\s*([a-z ,&]+?)(?:[.;\n]|$)", ex.lower):
        for item in _split_list(m.group(1)):
            w = _clean_phrase(item)
            if w and len(w) <= 2 and _is_person_noun(w[-1]):
                ex.roles.setdefault(to_snake(singularize(w[-1])), {"description": "", "is_admin": w[-1].startswith("admin"), "mentions": ""})
    declared = bool(ex.roles)  # a roles section or "roles: ..." list is the complete list
    if not declared:
        # people who act in sentences: "Managers approve purchase orders", "Front desk staff check guests in"
        for b in blocks:
            if b.kind in ("meta", "dashboard"):
                continue
            for sentence in b.body + ([b.title] if b.title else []):
                for part in re.split(r",|;|\band\b|\bwhere\b|\bwhile\b|:", sentence.lower()):
                    parsed = _clause(re.sub(r"^\s*(?:only|all|the|and|then)\s+", "", part))
                    if parsed and not parsed[3] and _is_person_noun(parsed[0][-1]):
                        _note_role(ex, parsed[0][-1], f"{parsed[1]} {parsed[2]}".strip())
                    by = re.search(r"\bby\s+(?:the\s+)?([a-z ]+)$", parsed[2]) if parsed and parsed[3] else None
                    if by and _clean_phrase(by.group(1)):  # "leave requests are approved by managers"
                        _note_role(ex, _clean_phrase(by.group(1))[-1], f"{parsed[1]} {' '.join(parsed[0])}")
        for name, info in ex.clause_roles.items():
            ex.roles.setdefault(name, info)
    for m in re.finditer(r"\b(?:for|used by|helps|lets|allows)\s+((?:[a-z]+\s+){0,2}?[a-z]+s)\b(?:\s+(?:to|and|who|in|with|at)\b|[.,]|$)", ex.lower):
        w = _clean_phrase(m.group(1))
        if w and _is_person_noun(w[-1]) and singularize(w[-1]) not in ex.entities and w[-1] not in {"users", "others", "items"}:
            words = [x for x in w if not _ui_word(x)][-2:] or w[-1:]
            ex.target_users.append(to_snake(_singular_phrase(words)))  # "marine biologists" -> marine_biologist
    for m in re.finditer(r"\b([a-z]+s)\s+(?:can|should be able to|may|must be able to)\s+([a-z ,]+?)(?:[.;]|$)", ex.lower):
        noun = singularize(m.group(1))
        if _is_person_noun(noun) and noun not in {"user"}:
            ex.roles.setdefault(noun, {"description": "", "is_admin": noun.startswith("admin"), "mentions": ""})
            ex.roles[noun]["mentions"] += " " + m.group(2)


def extract_spec(prompt: str) -> PMOutput:
    """Derive a complete, prompt-specific application specification without an LLM."""
    text = _strip_markup(validate_prompt(prompt))
    ex = Extraction(text)
    project_name, app_type = _domain(ex, text)
    blocks = _parse_blocks(text)

    # 1. negative mentions and current-state descriptions
    for b in blocks:
        for s in b.body + ([b.title] if b.title else []):
            if NEGATIVE_CUE.search(s) or re.search(r"\breplace\b", s, re.I):
                _negative_mentions(ex, s)

    def usable(sentence: str) -> bool:
        return not SKIP_SENTENCE.search(sentence) and not re.match(r"^\s*(?:do not|don't|never|avoid|remove)\b", sentence, re.I)

    # 2. explicit model lists anywhere ("create patient, doctor, ... models", "relationships between ...")
    for m in re.finditer(r"\b(?:create|add|build|define|implement|generate|include)\s+(?:proper\s+|the\s+|separate\s+)?([a-z ,&/-]+?)\s+(?:database\s+)?(?:models|entities|database tables)\b", ex.lower):
        if re.search(r"\b(?:with|for|that|which|app|application|system|platform|tracker)\b", m.group(1)):
            continue  # "build a ... tracker with ... nursery tables" is not a model list
        for item in _split_list(m.group(1)):
            ex.add_entity(item, m.group(0))
    for m in re.finditer(r"\brelationships?\s+between\s+([a-z ,&/-]+?)(?:[.;\n]|$)", ex.lower):
        group = re.split(r"\s+(?:are|is|should|must|will|be|correct)\b", m.group(1))[0]
        if "," not in group and " and " not in group:
            continue  # "relationships between records are correct" names no entities
        for item in _split_list(group):
            ex.add_entity(item, m.group(0), allow_new=True)

    # 3. modules (numbered/bulleted titles, "<X> Management" phrases) and their descriptions
    seen_module_keys: Set[str] = set()

    def title_words_of(title: str) -> List[str]:
        head = re.split(r"\b(?:with|for|to|that|including|so)\b", title, maxsplit=1, flags=re.I)[0]
        return [w for w in _clean_phrase(head) if w not in MODULE_SUFFIXES and w not in IMPERATIVE_WORDS]

    def add_module(title: str, module_entities: List[str], description: str, source: str) -> Optional[ModuleSpec]:
        words = title_words_of(title) if title else []
        mkey = to_snake(" ".join(words)) if words else to_snake(" ".join(module_entities))
        if not module_entities or not mkey:
            return None
        if mkey in seen_module_keys:
            return next((m for m in ex.modules if m.key == mkey), None)
        # a numbered section ("3. Farm Management") details a module the overview already listed ("manage farms, ...")
        overview = next((m for m in ex.modules if m.entities and m.entities[0] == module_entities[0]
                         and m.source and not m.description), None)
        if overview is not None:
            seen_module_keys.add(mkey)
            for key in module_entities[1:]:
                if key not in overview.entities:
                    overview.entities.append(key)
            if len(overview.entities) > 1:
                overview.label = _module_label(ex, words, overview.entities)
            overview.name = re.sub(r"^\d+[.)]\s*", "", title.strip().rstrip(".:")) or overview.name
            overview.description = description[:300]
            return overview
        seen_module_keys.add(mkey)
        if re.search(r"\bworkflows?\b", title, re.I):  # "Admission and Discharge workflows" -> Admissions
            label = " & ".join(humanize(pluralize(k)).capitalize() for k in module_entities[:3])
        else:
            label = _module_label(ex, words, module_entities)
        name = re.sub(r"^(?:implement|build|create|add|provide|include|support|develop|enable)\s+(?:(?:a|an|the|functional|proper)\s+)*",
                      "", title.strip().rstrip(".:"), flags=re.I)
        name = re.split(r"\s+(?:with|including)\s+", name, maxsplit=1, flags=re.I)[0].strip()
        ex.modules.append(ModuleSpec(key=mkey, name=(name[:1].upper() + name[1:]) or label, label=label,
                                     entities=list(module_entities), description=description[:300], source=source[:300]))
        ex.trace_item("module", title or label, [to_pascal(e) for e in module_entities], source)
        return ex.modules[-1]

    dash_ctx = False
    last_section: Optional[str] = None
    for b in blocks:
        if b.section != last_section or b.title:
            dash_ctx = False
            last_section = b.section
        if b.kind in ("meta", "role"):
            continue
        if b.kind == "dashboard":
            ex.wants_dashboard = True
            ex.metric_phrases.extend(s for s in b.body if not is_design_sentence(s))
            continue
        if b.kind == "reports":
            ex.wants_reports = True
            ex.trace_item("page", b.title, ["Reports page"], b.title + ": " + " ".join(b.body))
            continue
        title = b.title
        module_entities: List[str] = []
        current_module: Optional[ModuleSpec] = None
        title_entities: List[str] = []
        before_fields: Set[str] = set()
        before_refs: Set[str] = set()
        if title and usable(title) and not is_design_sentence(title):
            _, module_entities, status_hint = _module_title_entities(ex, title, title)
            title_entities = list(module_entities)
            if title_entities:
                before_fields = set(ex.entities[title_entities[0]].fields)
                before_refs = set(ex.entities[title_entities[0]].refs)
            current_module = add_module(title, module_entities, " ".join(b.body + [n for _, n in b.noun_items]), title)
            if status_hint and module_entities:
                for key in module_entities:
                    ex.set_statuses(key, _split_list(status_hint), title)
            _workflow_states(ex, title, module_entities, title)
            _rules_from_sentence(ex, title, module_entities, title)
        for sentence in b.body:
            if not usable(sentence) or is_design_sentence(sentence):
                continue
            # "Build X with A, B and an admin dashboard showing overdue loans": the dashboard clause lists figures,
            # not records (it would otherwise become an 'OverdueLoan' record and module)
            dm = re.search(r"(?:,\s*|\s+)(?:and\s+)?(?:an?\s+|the\s+)?(?:(?:admin|main|analytics|management|home)\s+)?"
                           r"dashboard\s+(?:showing|that shows|which shows|displaying|listing|to show|with)\s+(.+?)(?=[.;!]|$)",
                           sentence, re.I)
            if dm and re.match(r"^\s*(?:build|create|make|develop|generate|design)\b", sentence, re.I):
                ex.wants_dashboard = True
                ex.metric_phrases.append("dashboard showing " + dm.group(1))
                sentence = sentence[:dm.start()] + " and an admin dashboard" + sentence[dm.end():]
            if re.search(r"\bdashboard\b", sentence, re.I):
                ex.wants_dashboard = True
                if not re.match(r"^\s*(?:build|create|make|develop|generate|design)\b", sentence, re.I):
                    dash_ctx = True  # "Redesign the dashboard ... Display patient count, ..."
                    if re.search(r"\b(?:display|displays|show|shows|include|includes|list|lists|contain|contains|"
                                 r"highlight|highlights|present|feature)\b", sentence, re.I):
                        ex.metric_phrases.append(sentence)
                    continue
            elif dash_ctx and re.match(r"^\s*(?:display|show|include|add|list|highlight|present|feature)\b", sentence, re.I):
                ex.metric_phrases.append(sentence)
                continue
            else:
                dash_ctx = False
            # "Replace Products and Categories with proper Patient Management and Medical Records modules"
            rm = re.search(r"\breplace\s+.+?\s+with\s+(.+?)(?:[.;]|$)", sentence, re.I)
            if rm:
                for part in re.split(r"\s+(?:and|&)\s+|,\s*", rm.group(1)):
                    _, ents, _ = _module_title_entities(ex, part, sentence)
                    add_module(part, ents, "", sentence)
                sentence = re.sub(r"\s*(?:,|\band\b)?\s*$", "", sentence[:rm.start()]) + sentence[rm.end():]
                if len(_words(sentence)) < 2:
                    continue  # "also add projects and replace X with Y": the rest is processed below
            # "Build a school app where students enroll in courses, teachers grade assignments and attendance is
            # tracked": each clause names records (verbs need not be ones that create things)
            wm = None if module_entities else re.search(r"\b(?:where|in which|so that|such that)\s+(.+?)(?:[.;!]|$)",
                                                        sentence, re.I)
            previous: Optional[str] = None
            for item in _split_list(wm.group(1)) if wm else []:
                clause_keys = _clause_entities(ex, item, sentence, allow_new=True, previous=previous)
                for key in clause_keys or []:
                    previous = key
                    if key not in seen_module_keys:
                        seen_module_keys.add(key)
                        label = humanize(pluralize(key)).capitalize()
                        ex.modules.append(ModuleSpec(key=key, name=label, label=label, entities=[key],
                                                     source=sentence[:200]))
                        ex.trace_item("module", item, [to_pascal(key)], item)
            touched = _field_lists(ex, sentence, module_entities, sentence, strong=True)
            for key in touched:
                if key not in module_entities and title:
                    module_entities.append(key)
                    if current_module is not None and key not in current_module.entities:
                        current_module.entities.append(key)
                    elif current_module is None and module_entities and module_entities[0] == key:
                        current_module = add_module(title, module_entities, " ".join(b.body), title)
            _rules_from_sentence(ex, sentence, module_entities, sentence)
            _workflow_states(ex, sentence, module_entities, sentence)
            # "Include Cardiology, Neurology, ..." -> seed records of the module's entity
            sm = re.search(r"\b(?i:include|includes|including|such as|e\.?g\.?|like|predefined|default)\s*:?\s*((?:[A-Z][\w&'-]*(?:\s+[A-Z][\w&'-]*)*,\s*)+(?:and\s+)?[A-Z][\w&'-]*(?:\s+[A-Z][\w&'-]*)*)", sentence)
            if sm and module_entities:
                values = [v for v in _split_list(sm.group(1)) if v and v[0].isupper()]
                if len(values) >= 2:
                    ex.seed.setdefault(module_entities[0], []).extend(values)
            # flat enumerations: "Build X with A, B and C" / "manage A, B and C"
            # ("Car rental app: customers, cars, rental bookings, payments and damage reports" lists them after a colon)
            for lm in re.finditer(r"\b(?:with|including|includes|include|covering|such as|manage|managing|track|tracking|handles?|supports?|modules?:?|features?:?|(?:app|application|system|platform|tracker|portal|tool|software|website)\s*:)\s+((?:[a-z][a-z -]*?,\s*)+(?:and\s+|or\s+)?[a-z][a-z -]*?)(?:[.;:!]|$)", sentence.lower()):
                items = _split_list(lm.group(1))
                if len(items) < 2 or module_entities or sentence in ex.consumed:
                    continue  # inside a described module, lists are fields/statuses (handled above)
                for item in items:
                    clause_keys = _clause_entities(ex, item, sentence, allow_new=True)
                    if clause_keys is not None:  # "experiments use samples": the records it names, not the clause
                        for key in clause_keys:
                            if key not in seen_module_keys:
                                seen_module_keys.add(key)
                                label = humanize(pluralize(key)).capitalize()
                                ex.modules.append(ModuleSpec(key=key, name=label, label=label, entities=[key],
                                                             source=sentence[:200]))
                                ex.trace_item("module", item, [to_pascal(key)], item)
                        continue
                    words = _cut_at_preposition(_clean_phrase(item))
                    if not words:
                        continue
                    user_label = " ".join(w for w in words if w not in CRUD_NOUNS).capitalize()
                    if words[-1] in CRUD_NOUNS:  # "task creation" -> the Tasks module
                        user_label = pluralize(user_label)
                    if words[-1] in {"tracking", "management"} and len(words) > 1:
                        words = words[:-1]
                    phrase = " ".join(words)
                    if phrase in ATTRIBUTE_ENUMERATIONS or singularize(phrase) in ATTRIBUTE_ENUMERATIONS:
                        ex.ambiguities.append(f"'{' '.join(_clean_phrase(item))}' was interpreted as an attribute of the "
                                              f"main records, not a separate module.")
                        ex.attribute_asks.append(singularize(phrase))
                        ex.metric_phrases.append(" ".join(_clean_phrase(item)))
                        continue
                    key = ex.add_entity(phrase, sentence)
                    if not key and singularize(words[-1]) in lex.ATTRIBUTE_HEADS | {"deadline", "due"}:
                        ex.pending_attributes.append(phrase)  # "task priority", "due dates"
                        continue
                    if key and key not in seen_module_keys:
                        seen_module_keys.add(key)
                        ex.modules.append(ModuleSpec(key=key, name=user_label, label=user_label, entities=[key],
                                                     source=sentence[:200]))
                        ex.trace_item("module", item, [to_pascal(key)], item)

        if b.noun_items and b.kind == "module":
            _noun_items(ex, b, module_entities, current_module)
        siblings = [k for k in title_entities if k in ex.entities]
        if len(siblings) >= 2 and not any(_event_like(k) for k in siblings):
            first = ex.entities[siblings[0]]
            for other in siblings[1:]:
                target = ex.entities[other]
                for name, fd in first.fields.items():
                    if name not in before_fields and name not in target.fields:
                        target.fields[name] = FieldDraft(**{**fd.__dict__})
                for ref in first.refs - before_refs:
                    if ref != other:
                        target.refs.add(ref)

    # the domain noun itself can be the main record ("task management application" -> tasks)
    domain_head = ex.domain_words[-1] if ex.domain_words else ""
    if domain_head and domain_head not in ex.entities and domain_head not in ex.negative and (
            domain_head in lex.TYPICAL_ATTRIBUTES or not ex.entities) and not _ui_word(domain_head):
        ex.domain_words = [w for w in ex.domain_words if w != domain_head]
        key = ex.add_entity(domain_head, f"{domain_head} application")
        if key:
            ex.entities[key].order = -1
            ex.modules.insert(0, ModuleSpec(key=key, name=humanize(pluralize(key)).capitalize(),
                                            label=humanize(pluralize(key)).capitalize(), entities=[key]))
            ex.trace_item("module", f"{domain_head} application", [to_pascal(key)], f"{domain_head} application")
    # attributes listed beside the records ("with categories, task priority and due dates")
    for item in ex.pending_attributes:
        words = _clean_phrase(item)
        owner = next((to_snake(singularize(w)) for w in words[:-1] if to_snake(singularize(w)) in ex.entities), None)
        owner = owner or (min(ex.entities, key=lambda k: ex.entities[k].order) if ex.entities else None)
        if owner:
            ex.add_field(owner, " ".join(w for w in words if to_snake(singularize(w)) != owner) or item)

    # 4. roles and target users
    _roles(ex, blocks)
    if not ex.entities:
        raise PromptValidationError(
            "Could not identify what data the application should manage. Mention the main things users work with, "
            "e.g. 'patients, doctors and appointments' or 'vehicles, drivers and trips'.")
    return _assemble(ex, project_name, app_type)


# ----------------------------------------------------------------------------------------------
# assembly: lexicon enrichment, relations, workflows, rules, permissions, metrics
# ----------------------------------------------------------------------------------------------

def _shade(hex_color: str, modifier: Optional[str]) -> str:
    """'dark green' -> a darker green; 'light blue' -> a lighter blue (sidebar/accent colours)."""
    if not modifier:
        return hex_color
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    factor = 0.55 if modifier in ("dark", "deep") else None
    if factor:
        r, g, b = (int(c * factor) for c in (r, g, b))
    else:
        r, g, b = (int(c + (255 - c) * 0.45) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _event_like(key: str) -> bool:
    """Records of something that happened (inspection, fuel record, admission) rather than things/people."""
    head = key.split("_")[-1]
    verb = _nominal_to_verb(head)
    if head in EVENT_HEADS or (head in RECORD_HEADS and head != "item") or (verb in lex.VERB_STATES and verb != head):
        return True  # "admission" (admit) is an event; "book" is a thing even though "to book" is a verb
    return bool(re.search(r"(?:tion|sion)$", head)) and len(head) > 7 and head not in NOMINALIZATION_THINGS


CONCEPT_GROUPS = [
    {"quantity", "stock", "qty", "units", "quantity_in_stock", "stock_quantity", "available_quantity"},
    {"phone", "contact_number", "mobile", "phone_number", "telephone"},
    {"age", "date_of_birth", "dob", "birth_date"},
    {"price", "unit_price", "selling_price"},
    {"name", "full_name", "title"},
]


def _equivalent_field(name: str, ftype: str, existing) -> bool:
    """True when a typical attribute duplicates one the prompt already gave ("admitted_on" vs "admission_date")."""
    for f in existing:
        if singularize(f.name) == singularize(name):
            return True
        if any(name in g and f.name in g for g in CONCEPT_GROUPS):
            return True
        if ftype in ("date", "datetime") and f.type in ("date", "datetime"):
            a, b = name.split("_")[0], f.name.split("_")[0]
            if len(a) >= 4 and len(b) >= 4 and a[:4] == b[:4] and a not in {"date", "created"}:
                return True
            strip = lambda n: n.rsplit("_", 1)[0] if n.endswith(("_date", "_on", "_at")) else n  # noqa: E731
            if strip(name) == strip(f.name):
                return True  # due_on vs due_date
    return False


CONTAINER_HEADS = {"base", "center", "centre", "hub", "repository", "library", "portal", "directory", "desk", "area",
                   "workspace", "space", "zone", "corner", "wiki"}
SHIPPING_CONTEXT = re.compile(r"\b(?:ship|shipping|shipped|deliver|delivery|deliveries|cart|e-?commerce|checkout|"
                              r"online (?:store|shop)|storefront)\w*", re.I)


def _entity_by_head(ex: Extraction, phrase: str) -> Optional[str]:
    """'classes' -> fitness_class when that is the only record whose name ends with the noun."""
    words = _clean_phrase(phrase)
    if not words:
        return None
    head = singularize(words[0])
    matches = [k for k in ex.entities if k == head or k.endswith("_" + head)]
    return matches[0] if len(matches) == 1 else None


def _prompt_driven_adjustments(ex: Extraction) -> None:
    entities = ex.entities
    # C. a module title that only names a container ("Knowledge Base" holding articles) is not a record
    for module in ex.modules:
        if len(module.entities) < 2:
            continue
        first = module.entities[0]
        ent = entities.get(first)
        if ent is None or first.split("_")[-1] not in CONTAINER_HEADS or any(f.explicit for f in ent.fields.values())                 or any(first in o.refs for o in entities.values()):
            continue
        if ent.sources and all(src == module.source for src in ent.sources):
            del entities[first]
            module.entities = [e for e in module.entities if e != first]
            module.label = humanize(first).capitalize()
            ex.ambiguities.append(f"'{humanize(first).capitalize()}' was used as the module name for "
                                  f"{', '.join(humanize(pluralize(e)) for e in module.entities)}.")
    # M. "orders" in a restaurant are not shipped: drop shipping attributes without a shipping context
    if not SHIPPING_CONTEXT.search(ex.text):
        for key, ent in entities.items():
            if key.split("_")[-1] == "order":
                if "shipping_address" in ent.fields and not ent.fields["shipping_address"].explicit:
                    del ent.fields["shipping_address"]
                status = ent.fields.get("status")
                if status is not None and not status.explicit and {"shipped", "delivered"} & set(status.values):
                    status.values = ent.statuses = ["pending", "confirmed", "completed", "cancelled"]
    # every event record has a date ("irrigation" records, "sales")
    for key, ent in entities.items():
        if _event_like(key) and not any(f.type in ("date", "datetime") for f in ent.fields.values()):
            name = f"{key.split('_')[-1]}_date"
            ent.fields[name] = FieldDraft(name, "date", label=humanize(name).capitalize(), explicit=False)
    # I. dashboard asks that need data the records do not have yet
    asks = " ".join(ex.metric_phrases).lower()
    for phrase in ex.metric_phrases:
        words = _clean_phrase(phrase)
        if not set(words) & ACTIVE_WORDS:
            continue
        key = next((k for w in words for k in [ex.resolve([w], allow_new=False) or _entity_by_head(ex, w)] if k), None)
        ent = entities.get(key) if key else None
        if ent is not None and "status" not in ent.fields:
            ent.fields["status"] = FieldDraft("status", "enum", values=["active", "inactive"], required=True, label="Status")
            ent.statuses = ["active", "inactive"]
            ex.ambiguities.append(f"An active/inactive status was added to {humanize(key)} for the requested "
                                  f"'{' '.join(words)}' figure.")
    for m in re.finditer(r"\bactive\s+([a-z]+(?:\s+[a-z]+)?)", asks):
        key = ex.resolve(_clean_phrase(m.group(1)), allow_new=False) or _entity_by_head(ex, m.group(1))
        ent = entities.get(key) if key else None
        if ent is not None and "status" not in ent.fields:
            ent.fields["status"] = FieldDraft("status", "enum", values=["active", "inactive"], required=True, label="Status")
            ent.statuses = ["active", "inactive"]
            ex.ambiguities.append(f"An active/inactive status was added to {humanize(key)} for the requested "
                                  f"'active {m.group(1)}' figure.")
    for m in re.finditer(r"\b(?:today'?s|upcoming|scheduled)\s+([a-z]+(?:\s+[a-z]+)?)", asks):
        key = ex.resolve(_clean_phrase(m.group(1)), allow_new=False) or _entity_by_head(ex, m.group(1))
        ent = entities.get(key) if key else None
        if ent is not None and not any(f.type in ("date", "datetime") for f in ent.fields.values()):
            name = f"{key.split('_')[-1]}_date"
            ent.fields[name] = FieldDraft(name, "date", label=humanize(name).capitalize())
            ex.ambiguities.append(f"A date was added to {humanize(key)} for the requested '{m.group(0)}' figure.")


def _assemble(ex: Extraction, project_name: str, app_type: str) -> PMOutput:
    entities = ex.entities
    # drop entities explicitly rejected
    for key in list(entities):
        if key in ex.negative:
            del entities[key]
            ex.ambiguities.append(f"'{humanize(key)}' was excluded because the prompt asked not to include it.")
    # enrich attributes from general vocabulary when the prompt gave few
    for key, ent in entities.items():
        explicit = [f for f in ent.fields.values() if f.name != "status"]
        typical = lex.TYPICAL_ATTRIBUTES.get(key) or lex.TYPICAL_ATTRIBUTES.get(key.split("_")[-1])
        if typical and len(explicit) < 3:
            for spec in typical:
                name, ftype, values, flags = lex.parse_attribute(spec)
                if name == "status":
                    if not ent.statuses:
                        ent.statuses = values
                        ent.fields["status"] = FieldDraft("status", "enum", values=values, required=True, label="Status",
                                                          explicit=False)
                    continue
                explicit_dates = sum(1 for f in explicit if f.type in ("date", "datetime"))
                if ftype in ("date", "datetime") and explicit_dates >= 2:
                    continue  # the prompt already named this record's dates
                if name in ent.fields or _equivalent_field(name, ftype, ent.fields.values()):
                    continue
                fd = FieldDraft(name, ftype, values=values, required="req" in flags, unique="uniq" in flags,
                                searchable="search" in flags, label=humanize(name), explicit=False)
                for flag in flags:
                    if flag.startswith("min="):
                        fd.min_value = float(flag[4:])
                    elif flag.startswith("max="):
                        fd.max_value = float(flag[4:])
                ent.fields[name] = fd
            if not explicit:
                ex.ambiguities.append(f"No attributes were specified for {humanize(key)}; typical attributes were used.")
        elif not explicit:
            if _event_like(key):
                ent.fields.setdefault(f"{key.split('_')[-1]}_date", FieldDraft(f"{key.split('_')[-1]}_date", "date", required=True, label="Date", explicit=False))
                if key.split("_")[-1] in ("usage", "consumption", "reading"):
                    ent.fields.setdefault("quantity", FieldDraft("quantity", "float", min_value=0, label="Quantity", explicit=False))
                ent.fields.setdefault("notes", FieldDraft("notes", "text", searchable=True, label="Notes", explicit=False))
            elif _is_person_noun(key.split("_")[-1]):
                ent.fields.setdefault("name", FieldDraft("name", "string", required=True, searchable=True, label="Name", explicit=False))
                ent.fields.setdefault("email", FieldDraft("email", "email", label="Email", explicit=False))
                ent.fields.setdefault("phone", FieldDraft("phone", "string", label="Phone", explicit=False))
            else:
                ent.fields.setdefault("name", FieldDraft("name", "string", required=True, searchable=True, label="Name", explicit=False))
                ent.fields.setdefault("description", FieldDraft("description", "text", searchable=True, label="Description", explicit=False))
            ex.ambiguities.append(f"No attributes were specified for {humanize(key)} and it is not in FORGE AI's vocabulary; generic attributes were used.")
        if ent.subtypes:
            ent.fields["category"] = FieldDraft("category", "enum", values=list(dict.fromkeys(ent.subtypes)), required=True,
                                                label="Type", explicit=True)
        status = ent.fields.get("status")
        if status is not None and status.type == "enum" and not status.values:
            typical_status = next((lex.parse_attribute(a)[2] for a in (typical or []) if a.startswith("status")), None)
            status.values = typical_status or ["active", "inactive"]
            ent.statuses = status.values
            if not typical_status:
                ex.ambiguities.append(f"No status values were given for {humanize(key)}; 'active' and 'inactive' were used.")

    _prompt_driven_adjustments(ex)

    # attributes requested as list items ("projects, tasks, deadlines and progress tracking")
    ordered = sorted(entities, key=lambda k: entities[k].order)
    with_status = [k for k in ordered if entities[k].statuses]
    for ask in dict.fromkeys(ex.attribute_asks):
        if ask in {"deadline", "due date"}:
            if not any(n in ("due_date", "deadline", "end_date") for k in ordered for n in entities[k].fields):
                target = (with_status or ordered)[0]
                entities[target].fields["due_date"] = FieldDraft("due_date", "date", label="Due date")
                ex.ambiguities.append(f"A due date was added to {humanize(target)} for the requested deadlines.")
        elif ask in {"progress", "progress tracking"}:
            if not any("progress" in entities[k].fields for k in ordered):
                target = ordered[0]
                entities[target].fields["progress"] = FieldDraft("progress", "integer", min_value=0, max_value=100,
                                                                 label="Progress (%)")
                ex.ambiguities.append(f"Progress (0-100%) was added to {humanize(target)} for the requested progress tracking.")
        elif ask == "priority":
            if not any("priority" in entities[k].fields for k in ordered):
                target = (with_status or ordered)[0]
                entities[target].fields["priority"] = FieldDraft("priority", "enum", values=["low", "medium", "high"],
                                                                 label="Priority")

    # typical relations between requested entities
    keys = set(entities)
    for key, ent in entities.items():
        for parent in lex.TYPICAL_RELATIONS.get(key, []) + lex.TYPICAL_RELATIONS.get(key.split("_")[-1], []):
            if parent in keys and parent != key and key not in entities[parent].refs:
                ent.refs.add(parent)
    # unrelated event-like records attach to the anchor (main managed thing) of the app
    # "pet owners": the pet belongs to its owner
    for key in entities:
        parts = key.split("_")
        base = "_".join(parts[:-1])
        if len(parts) > 1 and base in entities and _is_person_noun(parts[-1]) and key not in entities[base].refs:
            entities[base].refs.add(key)
    ordered_keys = sorted(entities, key=lambda k: entities[k].order)
    things = [k for k in ordered_keys if not _event_like(k) and k not in CLASSIFIER_HEADS]
    # events are about the main managed thing (pets, hives, vehicles) rather than about people
    anchor = next((k for k in things if not _is_person_noun(k.split("_")[-1])), things[0] if things else None)
    for key, ent in entities.items():
        if key == anchor or ent.refs or not anchor:
            continue
        if _event_like(key) and key not in lex.PERSONAL_RECORDS and not any(key in other.refs for other in entities.values()):
            ent.refs.add(anchor)
            ex.ambiguities.append(f"{humanize(key).capitalize()} records were linked to {humanize(anchor)} (inferred relation).")
    # a listed classifier ("categories", "tags") classifies the main records when nothing else uses it
    for key in entities:
        if key in CLASSIFIER_HEADS | PLURAL_CLASSIFIERS and anchor and anchor != key and not any(
                key in other.refs for other in entities.values()):
            entities[anchor].refs.add(key)
            ex.ambiguities.append(f"{humanize(pluralize(anchor)).capitalize()} were linked to "
                                  f"{humanize(pluralize(key))} (inferred relation).")
    # break reference cycles (keep the first-declared direction)
    for key, ent in entities.items():
        for ref in list(ent.refs):
            if ref in entities and key in entities[ref].refs:
                if entities[key].order < entities[ref].order:
                    ent.refs.discard(ref)
                else:
                    entities[ref].refs.discard(key)
    # every record needs something to show in lists and dropdowns; people have names
    for key, ent in entities.items():
        identifying = any(n in {"name", "full_name", "first_name", "title", "code", "sku"} or n.endswith("_number")
                          or n.endswith("_name") or n.endswith("_title") for n in ent.fields)
        line_record = key.split("_")[-1] in {"item", "line", "assignment", "enrollment", "membership", "allocation", "comment"}
        thing = not _event_like(key) and not line_record and (not ent.refs or len(ent.fields) >= 2)
        if not identifying and (_is_person_noun(key.split("_")[-1]) or thing):
            ent.fields = {"name": FieldDraft("name", "string", required=True, searchable=True, label="Name", explicit=False),
                          **ent.fields}
        if not any(f.type in ("string", "email", "text", "date", "datetime") for f in ent.fields.values()) and not ent.refs:
            ent.fields["name"] = FieldDraft("name", "string", required=True, searchable=True, label="Name", explicit=False)

    # roles and permissions
    roles: List[UserRole] = [UserRole(name="admin", description="Full access to all modules and users", is_admin=True)]
    for name, info in ex.roles.items():
        if name == "admin":
            roles[0].description = info["description"] or roles[0].description
            continue
        roles.append(UserRole(name=name, description=info["description"] or f"{humanize(name).capitalize()} access",
                              is_admin=info["is_admin"]))
    for t in ex.target_users:
        if t not in {r.name for r in roles}:
            roles.append(UserRole(name=t, description=f"{humanize(t).capitalize()} using the application"))
    if not any(not r.is_admin for r in roles):
        roles.append(UserRole(name="user", description="Registered user"))
    staff_app = any(r.name not in {"user", "customer", "member", "student", "guest", "patient", "client", "buyer", "shopper"}
                    and not r.is_admin for r in roles)

    access: Dict[str, str] = {}
    for key in entities:
        if not staff_app and key in lex.PERSONAL_RECORDS:
            access[key] = "owner"
        elif not staff_app and key in lex.CATALOGUE_RECORDS:
            access[key] = "admin_managed"
        elif re.search(rf"\b(?:my|own|their own|personal|private)\s+(?:\w+\s+)?{re.escape(humanize(key).lower())}(?:s|es)?\b",
                       ex.lower):
            access[key] = "owner"  # "track my houseplants": each user sees only their own records
        else:
            access[key] = "shared"
    if not staff_app and any(a == "shared" for a in access.values()):
        ex.ambiguities.append("Records without an owner hint are shared by all signed-in users (admins delete); "
                              "say 'my <records>' or 'personal' to make them private to each user.")

    permissions: List[RolePermission] = []
    for role in roles:
        info = ex.roles.get(role.name, {})
        mentions = info.get("mentions", "").lower()
        mentioned: Dict[str, Set[str]] = {}
        if mentions and not role.is_admin:
            carried: Set[str] = set()
            for sentence_part in re.split(r"[.;]", mentions):
                carried = set()
                for clause in re.split(r",|\band\b", sentence_part):
                    actions: Set[str] = set()
                    for pattern, acts in ROLE_ACTION_WORDS:
                        if pattern.search(clause):
                            actions |= acts
                    actions = actions or carried  # "Manage farms, crops, workers, and activities"
                    carried = actions
                    rest = clause
                    for key in sorted(entities, key=lambda k: -len(humanize(k))):
                        names = sorted({humanize(key).lower(), humanize(pluralize(key)).lower(), key.split("_")[-1],
                                        pluralize(key.split("_")[-1])}, key=len, reverse=True)
                        alias = {v[0] for k, v in lex.MODULE_RECORDS.items() if re.search(rf"\b{re.escape(k.replace('_', ' '))}\b", rest)}
                        hit = next((n for n in names if re.search(rf"\b{re.escape(n)}\b", rest)), None)
                        if key in alias or hit:
                            mentioned.setdefault(key, set()).update(actions or {"read", "update"})
                            if hit:
                                rest = re.sub(rf"\b{re.escape(hit)}\b", " ", rest)  # "field activities" is not "field"
                        # verbs of a different word form: "admission" -> admissions
                for word in _words(clause):
                    verb = _nominal_to_verb(word)
                    if singularize(word.lower()) == verb:
                        continue  # "view books": the noun itself, not a nominalised action like "admission"
                    for key in entities:
                        if _nominal_to_verb(key.split("_")[-1]) == verb and verb in lex.VERB_STATES:
                            mentioned.setdefault(key, set()).update({"read", "create", "update"})
        for key in entities:
            if role.is_admin:
                acts = ["read", "create", "update", "delete"]
            elif mentioned:
                acts = sorted(mentioned.get(key, {"read"}))
            elif access[key] == "owner":
                acts = ["read", "create", "update", "delete"]
            elif access[key] == "admin_managed":
                acts = ["read"]
            else:
                acts = ["read", "create", "update"]
            permissions.append(RolePermission(role=role.name, entity=to_pascal(key), actions=acts))
        if mentioned:
            ex.trace_item("role", f"{role.name}: {info.get('description', '')}",
                          [f"{to_pascal(k)}:{'/'.join(sorted(v))}" for k, v in mentioned.items()], info.get("description", ""))
        elif role.name in ex.roles:
            ex.trace_item("role", role.name, [role.name], role.name)

    # build entity models
    db_entities: List[DatabaseEntity] = []
    for key in sorted(entities, key=lambda k: entities[k].order):
        ent = entities[key]
        fields: List[EntityField] = []
        for fd in ent.fields.values():
            fields.append(EntityField(name=fd.name, type=fd.type, nullable=not fd.required, unique=fd.unique,
                                      searchable=fd.searchable, enum_values=fd.values, label=fd.label or humanize(fd.name),
                                      min_value=fd.min_value, max_value=fd.max_value,
                                      default=(fd.values[0] if fd.values else None)))
        for ref in sorted(ent.refs):
            if ref in entities:
                fields.append(EntityField(name=f"{ref}_id", type="reference", references=to_pascal(ref),
                                          nullable=True, label=humanize(ref).capitalize()))
        display = next((f.name for f in fields if f.name in {"name", "title", "full_name"}), None) or next(
            (f.name for f in fields if f.type == "string"), None)
        db_entities.append(DatabaseEntity(name=to_pascal(key), description=f"{humanize(pluralize(key)).capitalize()}",
                                          fields=fields, access=access[key], display_field=display))

    # modules: every entity appears in exactly one module, in prompt order
    modules: List[ModuleSpec] = []
    covered: Set[str] = set()
    for m in ex.modules:
        ents = [to_pascal(e) for e in m.entities if e in entities and e not in covered]
        if not ents:
            continue
        covered.update(e for e in m.entities)
        own = [to_pascal(e) for e in m.entities if e in entities]
        if ents == own[:len(ents)] and m.label:
            label = m.label  # the user's terminology for the module
        elif len(ents) == 1:
            label = humanize(pluralize(to_snake(ents[0]))).capitalize()
        else:
            label = " & ".join(humanize(pluralize(to_snake(e))).capitalize() for e in ents[:3])
        modules.append(ModuleSpec(key=to_snake(m.name)[:40] or to_snake(ents[0]), name=m.name, label=label[:40],
                                  kind="entities", entities=ents, description=m.description, source=m.source))
    for key in sorted(entities, key=lambda k: entities[k].order):
        if key not in covered:
            label = humanize(pluralize(key)).capitalize()
            modules.append(ModuleSpec(key=key, name=label, label=label, kind="entities", entities=[to_pascal(key)],
                                      source=", ".join(entities[key].sources)[:200]))
    unentity_text = ex.lower
    for key in entities:  # "swarm reports" is an entity, not a request for a reports page
        unentity_text = re.sub(rf"\b{re.escape(humanize(key))}s?\b", " ", unentity_text)
    if ex.wants_reports or re.search(r"\breports?\b|\breporting\b", unentity_text):
        modules.append(ModuleSpec(key="reports", name="Reports", label="Reports", kind="reports",
                                  description="Counts, status breakdowns and monthly trends with date filters"))

    unsupported = [label for pattern, label in UNSUPPORTED if re.search(pattern, ex.lower)]
    for label in unsupported:
        ex.trace_item("feature", label, [], label, status="unsupported")

    theme = {}
    colors = "|".join(lex.COLOR_WORDS)
    if re.search(rf"\b({colors})\b", ex.lower) and re.search(r"\b(theme|colou?rs?|accent|palette|sidebar|branding)\b", ex.lower):
        side = re.search(rf"\b(dark|deep|light)?\s*({colors})(?:[- ]and[- ]\w+)?\s+(?:side\s?bar|navigation|menu)\b", ex.lower)
        if side:
            theme["sidebar_color"] = _shade(lex.COLOR_WORDS[side.group(2)], side.group(1))
        accent = re.search(rf"\b(dark|deep|light)?\s*({colors})\s+(?:accent|primary|buttons?|highlights?)\b", ex.lower)
        others = [m for m in re.finditer(rf"\b(dark|deep|light)?\s*({colors})\b", ex.lower)
                  if not side or m.start() != side.start()]
        chosen = accent or (others[0] if others else None)  # the sidebar colour is not also the accent
        if chosen:
            theme["primary_color"] = _shade(lex.COLOR_WORDS[chosen.group(2)], chosen.group(1))

    pm = PMOutput(
        project_name=project_name or f"{humanize(next(iter(entities))).capitalize()} Manager",
        description=ex.text[:2000],
        app_type=app_type,
        database_entities=db_entities,
        user_roles=roles,
        source_prompt=ex.text,
        generation_mode="deterministic",
        purpose="",
        target_users=sorted({r.name for r in roles if not r.is_admin}),
        module_specs=modules,
        business_rules=ex.rules,
        role_permissions=permissions,
        ambiguities=list(dict.fromkeys(ex.ambiguities)),
        unsupported_requests=unsupported,
        theme=theme,
        seed_records={to_pascal(k): [{"_display": v} for v in dict.fromkeys(vals)] for k, vals in ex.seed.items() if k in entities},
        demo_data=bool(DEMO_DATA.search(ex.text)),
        requirement_trace=ex.trace,
        has_admin_dashboard=True,
        requires_auth=True,
    )
    pm.dashboard_metrics = _metric_drafts(ex)
    return pm


def _metric_drafts(ex: Extraction) -> List[DashboardMetric]:
    """Dashboard asks as raw phrases; resolved against the final schema in finalize_spec()."""
    phrases: List[str] = []
    for s in ex.metric_phrases:
        body = re.sub(r"^.*?\b(?:display|displays|show|shows|include|includes|with|showing|displaying|list|lists|highlight|highlights|contain|contains)\s+",
                      "", s, count=1, flags=re.I | re.S)
        body = re.sub(r"\bprofit and loss\b", "profit-loss", body, flags=re.I)
        body = re.sub(r"\s+(?:the\s+)?dashboard\b.*$", "", body, flags=re.I) if re.match(r"^.*\bdashboard\b", s, re.I) and \
            not re.search(r"\b(?:on|in)\s+the\s+dashboard\b", body, re.I) else body
        phrases.extend(_split_list(re.sub(r"\b(?:on|in)\s+the\s+dashboard\b", "", body, flags=re.I)))
    return [DashboardMetric(id=f"ask_{i}", label=p.strip()[:80], kind="ask") for i, p in enumerate(phrases) if p.strip()]
