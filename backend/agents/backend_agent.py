"""Backend Agent for FORGE AI platform."""

import json
from typing import Dict, Any, Optional
from pathlib import Path

from backend.agents.base_agent import BaseAgent
from backend.schemas.pm_schema import PMOutput
from backend.schemas.backend_schema import BackendOutput
from backend.exceptions import MissingInputError, ValidationError, GenerationError


class BackendAgent(BaseAgent[BackendOutput]):
    """Agent responsible for generating backend FastAPI specifications from PM specifications."""

    def __init__(self, pm_output_path: str = "outputs/pm_output.json",
                 ui_output_path: Optional[str] = "outputs/ui_output.json",
                 output_filepath: str = "outputs/backend_output.json"):
        super().__init__(output_schema_cls=BackendOutput, output_filepath=output_filepath)
        self.pm_output_path = pm_output_path
        self.ui_output_path = ui_output_path
        self.pm_data: Optional[PMOutput] = None
        self.ui_data: Optional[Dict[str, Any]] = None

    def load_inputs(self) -> None:
        """Load and validate inputs from PM and optional UI agent."""
        raw_pm = self.read_json_file(self.pm_output_path)
        try:
            self.pm_data = PMOutput.model_validate(raw_pm)
        except Exception as e:
            raise ValidationError(f"Invalid pm_output.json format: {e}")

        # Optional UI agent output
        if self.ui_output_path and Path(self.ui_output_path).is_file():
            try:
                self.ui_data = self.read_json_file(self.ui_output_path)
            except Exception as e:
                self.logger.warning(f"Failed to parse optional ui_output.json: {e}")

    def generate(self) -> Dict[str, Any]:
        """Generate backend specification using LLM or rule-based fallback."""
        if not self.pm_data:
            raise GenerationError("Inputs not loaded. Call load_inputs() first.")

        model = self.get_gemini_model()
        if model:
            try:
                prompt = self._build_prompt()
                response = model.generate_content(prompt)
                text = response.text.strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
                parsed = json.loads(text)
                # Verify parseable by BackendOutput schema
                BackendOutput.model_validate(parsed)
                return parsed
            except Exception as e:
                self.logger.warning(f"LLM generation failed or returned invalid schema ({e}). Falling back to dynamic rule generator.")

        return self._generate_fallback()

    def _build_prompt(self) -> str:
        """Build structured LLM prompt for backend spec generation."""
        return f"""
You are a Senior Backend Architect AI.
Generate a comprehensive FastAPI backend specification JSON for the following project.

PROJECT SPECIFICATION:
{self.pm_data.model_dump_json(indent=2)}

STRICT RULES:
- Return ONLY valid raw JSON. No markdown code blocks, no explanations.
- Output MUST conform to BackendOutput schema.

Schema shape:
{{
  "project_name": "{self.pm_data.project_name}",
  "architecture": "Clean Architecture (Controller-Service-Repository)",
  "endpoints": [],
  "service_layer": [],
  "repository_layer": [],
  "global_dependencies": ["get_db", "get_current_user", "get_pagination_params"],
  "error_handlers": [
    {{"status_code": 404, "exception_type": "HTTPException", "detail": "Resource not found"}},
    {{"status_code": 400, "exception_type": "HTTPException", "detail": "Bad Request / Validation error"}},
    {{"status_code": 401, "exception_type": "HTTPException", "detail": "Unauthorized access"}},
    {{"status_code": 403, "exception_type": "HTTPException", "detail": "Forbidden operation"}},
    {{"status_code": 500, "exception_type": "HTTPException", "detail": "Internal server error"}}
  ]
}}
"""

    def _generate_fallback(self) -> Dict[str, Any]:
        """Dynamic rule-based generator for ANY domain specified in PM output."""
        project_name = self.pm_data.project_name
        entities = self.pm_data.database_entities

        endpoints = []
        service_layer = []
        repository_layer = []

        for entity in entities:
            entity_name = entity.name
            plural_name = f"{entity_name.lower()}s" if not entity_name.lower().endswith("s") else entity_name.lower()
            base_path = f"/api/{plural_name}"
            tag = entity_name

            # Build Request/Response Fields
            request_fields = []
            response_fields = [
                {"name": "id", "type": "int", "required": True, "default": None, "validation_rules": {}}
            ]

            for field in entity.fields:
                if field.name in ["id", "created_at", "updated_at"]:
                    if field.name != "id":
                        response_fields.append({
                            "name": field.name,
                            "type": "str",
                            "required": False,
                            "default": None,
                            "validation_rules": {}
                        })
                    continue

                py_type = "int" if "INT" in field.type.upper() else ("bool" if "BOOL" in field.type.upper() else "str")
                request_fields.append({
                    "name": field.name,
                    "type": py_type,
                    "required": not field.nullable,
                    "default": None,
                    "validation_rules": {}
                })
                response_fields.append({
                    "name": field.name,
                    "type": py_type,
                    "required": True,
                    "default": None,
                    "validation_rules": {}
                })

            req_schema = {
                "name": f"{entity_name}Create",
                "fields": request_fields
            }
            resp_schema = {
                "name": f"{entity_name}Response",
                "status_code": 200,
                "fields": response_fields
            }
            update_req_schema = {
                "name": f"{entity_name}Update",
                "fields": [{**f, "required": False} for f in request_fields]
            }

            # Check if auth required
            requires_auth = entity_name.lower() != "user"

            # 1. LIST Endpoint (with Pagination, Filtering, Sorting)
            endpoints.append({
                "path": base_path,
                "method": "GET",
                "summary": f"List all {plural_name}",
                "description": f"Retrieve paginated list of {plural_name} with optional filtering and sorting.",
                "operation_id": f"list_{plural_name}",
                "tags": [tag],
                "requires_auth": requires_auth,
                "required_roles": ["user", "admin"] if requires_auth else [],
                "request_schema": None,
                "response_schema": resp_schema,
                "parameters": [
                    {"name": "page", "in_location": "query", "param_type": "int", "required": False, "default": 1, "description": "Page number"},
                    {"name": "limit", "in_location": "query", "param_type": "int", "required": False, "default": 20, "description": "Items per page"},
                    {"name": "search", "in_location": "query", "param_type": "str", "required": False, "default": None, "description": "Search keyword"},
                    {"name": "sort_by", "in_location": "query", "param_type": "str", "required": False, "default": "id", "description": "Sort column"},
                    {"name": "order", "in_location": "query", "param_type": "str", "required": False, "default": "asc", "description": "Sort order (asc/desc)"}
                ],
                "business_logic_summary": f"Fetch paginated {plural_name} matching query parameters.",
                "is_file_upload": False
            })

            # 2. GET by ID Endpoint
            endpoints.append({
                "path": f"{base_path}/{{id}}",
                "method": "GET",
                "summary": f"Get {entity_name} by ID",
                "description": f"Retrieve single {entity_name} detail by identifier.",
                "operation_id": f"get_{entity_name.lower()}_by_id",
                "tags": [tag],
                "requires_auth": requires_auth,
                "required_roles": ["user", "admin"] if requires_auth else [],
                "request_schema": None,
                "response_schema": resp_schema,
                "parameters": [
                    {"name": "id", "in_location": "path", "param_type": "int", "required": True, "default": None, "description": f"{entity_name} ID"}
                ],
                "business_logic_summary": f"Fetch {entity_name} record from database or raise 404 if not found.",
                "is_file_upload": False
            })

            # 3. CREATE Endpoint
            endpoints.append({
                "path": base_path,
                "method": "POST",
                "summary": f"Create new {entity_name}",
                "description": f"Create a new {entity_name} record.",
                "operation_id": f"create_{entity_name.lower()}",
                "tags": [tag],
                "requires_auth": requires_auth,
                "required_roles": ["user", "admin"] if requires_auth else [],
                "request_schema": req_schema,
                "response_schema": {**resp_schema, "status_code": 201},
                "parameters": [],
                "business_logic_summary": f"Validate request body, construct {entity_name} entity, and persist to database.",
                "is_file_upload": False
            })

            # 4. UPDATE Endpoint
            endpoints.append({
                "path": f"{base_path}/{{id}}",
                "method": "PUT",
                "summary": f"Update {entity_name}",
                "description": f"Update an existing {entity_name} record by ID.",
                "operation_id": f"update_{entity_name.lower()}",
                "tags": [tag],
                "requires_auth": requires_auth,
                "required_roles": ["user", "admin"] if requires_auth else [],
                "request_schema": update_req_schema,
                "response_schema": resp_schema,
                "parameters": [
                    {"name": "id", "in_location": "path", "param_type": "int", "required": True, "default": None, "description": f"{entity_name} ID"}
                ],
                "business_logic_summary": f"Verify {entity_name} exists, update provided fields, and save changes.",
                "is_file_upload": False
            })

            # 5. DELETE Endpoint
            endpoints.append({
                "path": f"{base_path}/{{id}}",
                "method": "DELETE",
                "summary": f"Delete {entity_name}",
                "description": f"Remove a {entity_name} record from database.",
                "operation_id": f"delete_{entity_name.lower()}",
                "tags": [tag],
                "requires_auth": requires_auth,
                "required_roles": ["admin"],
                "request_schema": None,
                "response_schema": {"name": "MessageResponse", "status_code": 200, "fields": [{"name": "message", "type": "str", "required": True, "default": None, "validation_rules": {}}]},
                "parameters": [
                    {"name": "id", "in_location": "path", "param_type": "int", "required": True, "default": None, "description": f"{entity_name} ID"}
                ],
                "business_logic_summary": f"Delete {entity_name} record from database or raise 404.",
                "is_file_upload": False
            })

            # Service Layer Specs
            service_layer.append({
                "name": f"{entity_name}Service",
                "entity": entity_name,
                "methods": [
                    {"name": f"get_all_{plural_name}", "params": ["page: int", "limit: int", "search: Optional[str]"], "return_type": f"List[{entity_name}]", "description": f"Fetch paginated {plural_name} with filters."},
                    {"name": f"get_{entity_name.lower()}_by_id", "params": ["id: int"], "return_type": f"Optional[{entity_name}]", "description": f"Get single {entity_name} by ID."},
                    {"name": f"create_{entity_name.lower()}", "params": [f"data: {entity_name}Create"], "return_type": entity_name, "description": f"Validate and save new {entity_name}."},
                    {"name": f"update_{entity_name.lower()}", "params": ["id: int", f"data: {entity_name}Update"], "return_type": entity_name, "description": f"Update fields of existing {entity_name}."},
                    {"name": f"delete_{entity_name.lower()}", "params": ["id: int"], "return_type": "bool", "description": f"Delete {entity_name} record."}
                ]
            })

            # Repository Layer Specs
            repository_layer.append({
                "name": f"{entity_name}Repository",
                "entity": entity_name,
                "methods": [
                    {"name": "find_all", "query_description": f"SELECT * FROM {plural_name} OFFSET :offset LIMIT :limit", "return_type": f"List[{entity_name}]"},
                    {"name": "find_by_id", "query_description": f"SELECT * FROM {plural_name} WHERE id = :id", "return_type": f"Optional[{entity_name}]"},
                    {"name": "save", "query_description": f"INSERT INTO {plural_name} ... VALUES ...", "return_type": entity_name},
                    {"name": "update", "query_description": f"UPDATE {plural_name} SET ... WHERE id = :id", "return_type": entity_name},
                    {"name": "delete", "query_description": f"DELETE FROM {plural_name} WHERE id = :id", "return_type": "bool"}
                ]
            })

        return {
            "project_name": project_name,
            "architecture": "Clean Architecture (Controller-Service-Repository)",
            "endpoints": endpoints,
            "service_layer": service_layer,
            "repository_layer": repository_layer,
            "global_dependencies": [
                "get_db",
                "get_current_user",
                "get_pagination_params"
            ],
            "error_handlers": [
                {"status_code": 404, "exception_type": "HTTPException", "detail": "Resource not found"},
                {"status_code": 400, "exception_type": "HTTPException", "detail": "Bad Request / Validation error"},
                {"status_code": 401, "exception_type": "HTTPException", "detail": "Unauthorized access"},
                {"status_code": 403, "exception_type": "HTTPException", "detail": "Forbidden operation"},
                {"status_code": 500, "exception_type": "HTTPException", "detail": "Internal server error"}
            ]
        }


if __name__ == "__main__":
    agent = BackendAgent()
    agent.run()
