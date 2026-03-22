from __future__ import annotations

from typing import Any

import yaml

from semduck.authoring.validators import validate_semantic_spec
from semduck.errors import SemanticValidationError


def load_yaml_spec(yaml_text: str) -> dict[str, Any]:
    spec = yaml.safe_load(yaml_text)
    if not isinstance(spec, dict):
        raise SemanticValidationError("YAML must define a mapping at the top level")
    validate_semantic_spec(spec)
    return spec
