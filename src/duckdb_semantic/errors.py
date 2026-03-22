class SemanticViewError(Exception):
    pass


class SemanticValidationError(SemanticViewError):
    pass


class SemanticParseError(SemanticViewError):
    pass


class SemanticRegistryError(SemanticViewError):
    pass


class SemanticResolutionError(SemanticViewError):
    pass


class SemanticJoinError(SemanticViewError):
    pass


class SemanticCompileError(SemanticViewError):
    pass


class SemanticUnsupportedError(SemanticViewError):
    pass

