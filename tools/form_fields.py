"""Single source of truth for the issue form: the generator writes it, the parser reads it.

Because both import this table, a label can never drift between the form a user fills in
and the parser that reads it. Every value still goes through request.v1.schema.json afterwards.
"""

# (request field, form label, kind, required)
#   kind: input | dropdown | checkbox
FIELDS = [
    ("name", "Application name", "input", True),
    ("environment", "Environment", "dropdown", True),
    ("sizing", "Size", "dropdown", True),
    ("image", "OS image", "dropdown", True),
    ("network_profile", "Network profile", "dropdown", True),
    ("middleware", "Middleware", "dropdown", True),
    ("data_disk_gb", "Data disk size (GB)", "input", False),
    ("owner", "Owner (team or user id)", "input", False),
    ("ttl_days", "Lifetime in days", "input", False),
    ("_confirm", "Confirmation", "checkbox", True),
]

CONFIRM_TEXT = "I confirm this request contains no passwords, keys or other secrets"
INT_FIELDS = {"data_disk_gb", "ttl_days"}
LABEL_TO_FIELD = {label: field for field, label, _kind, _req in FIELDS}
NO_RESPONSE = "_No response_"
TITLE_PREFIX = "[platform] "

# GitHub reserves the dropdown option "None", so the form offers a different word and the
# parser maps it back to the value request.v1 expects.
FORM_TO_REQUEST_VALUE = {"middleware": {"no-middleware": "none"}}
