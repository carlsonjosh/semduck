from __future__ import annotations

from semduck.api import get_semantic_view, list_semantic_views

from .models import SchemaIndex, ViewCoverage


def build_schema_index(conn) -> SchemaIndex:
    view_coverages: list[ViewCoverage] = []
    all_dimensions: set[str] = set()
    all_metrics: set[str] = set()

    for view_name in list_semantic_views(conn):
        registry = get_semantic_view(conn, view_name)
        dimensions: set[str] = set()
        metrics: set[str] = set()
        time_dimensions: set[str] = set()

        for table in registry.tables.values():
            for name, dimension in table.dimensions.items():
                dimensions.add(name)
                if dimension.object_type == "time_dimension":
                    time_dimensions.add(name)
            metrics.update(table.metrics.keys())

        view_coverages.append(
            ViewCoverage(
                view_name=view_name,
                dimensions=sorted(dimensions),
                metrics=sorted(metrics),
                time_dimensions=sorted(time_dimensions),
            )
        )
        all_dimensions.update(dimensions)
        all_metrics.update(metrics)

    return SchemaIndex(
        views=view_coverages,
        all_dimensions=sorted(all_dimensions),
        all_metrics=sorted(all_metrics),
    )


def views_covering(index: SchemaIndex, *, dimensions: list[str], metrics: list[str]) -> list[str]:
    required_dimensions = set(dimensions)
    required_metrics = set(metrics)
    candidates: list[str] = []
    for view in index.views:
        if required_dimensions.issubset(view.dimensions) and required_metrics.issubset(view.metrics):
            candidates.append(view.view_name)
    return candidates
