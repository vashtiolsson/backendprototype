"""
Ontology loader — parses the Turtle file and exposes
helpers to inspect classes, properties, and individuals.
"""

from rdflib import Graph, RDF, RDFS, OWL, Namespace
from pathlib import Path

# This must match the @prefix : line in your .ttl file exactly.
ONTOLOGY_NAMESPACE = "http://www.semanticweb.org/vashti.ow/ontologies/2026/4/untitled-ontology-2/"
INC = Namespace(ONTOLOGY_NAMESPACE)

ONTOLOGY_PATH = Path(__file__).parent.parent / "ontology" / "income_ontology.ttl"


def load_graph() -> Graph:
    """Load the ontology .ttl into an rdflib Graph."""
    g = Graph()
    g.parse(ONTOLOGY_PATH, format="turtle")
    g.bind("", INC)  # bind ":" prefix for SPARQL
    return g


def list_classes(g: Graph) -> list[dict]:
    """Return all classes in the income namespace."""
    classes = []
    for cls in g.subjects(RDF.type, OWL.Class):
        if str(cls).startswith(ONTOLOGY_NAMESPACE):
            classes.append({
                "iri": str(cls),
                "name": str(cls).rsplit("/", 1)[-1],
                "label": str(g.value(cls, RDFS.label) or ""),
                "comment": str(g.value(cls, RDFS.comment) or ""),
            })
    return sorted(classes, key=lambda c: c["name"])


def list_individuals(g: Graph) -> list[dict]:
    """Return all named individuals with their parent class(es)."""
    individuals = []
    for ind in g.subjects(RDF.type, OWL.NamedIndividual):
        if not str(ind).startswith(ONTOLOGY_NAMESPACE):
            continue
        types = [
            str(t).rsplit("/", 1)[-1]
            for t in g.objects(ind, RDF.type)
            if t != OWL.NamedIndividual and str(t).startswith(ONTOLOGY_NAMESPACE)
        ]
        individuals.append({
            "iri": str(ind),
            "name": str(ind).rsplit("/", 1)[-1],
            "types": types,
            "label": str(g.value(ind, RDFS.label) or ""),
        })
    return sorted(individuals, key=lambda i: i["name"])


def get_concepts_for_mapping(g: Graph) -> list[dict]:
    """
    Return the concepts (object + data properties) that source fields
    will be mapped to. This is what the AI mapping pipeline consumes.
    """
    concepts = []
    for prop_type in [OWL.ObjectProperty, OWL.DatatypeProperty]:
        for prop in g.subjects(RDF.type, prop_type):
            if not str(prop).startswith(ONTOLOGY_NAMESPACE):
                continue
            domain = g.value(prop, RDFS.domain)
            range_ = g.value(prop, RDFS.range)
            concepts.append({
                "iri": str(prop),
                "name": str(prop).rsplit("/", 1)[-1],
                "label": str(g.value(prop, RDFS.label) or ""),
                "comment": str(g.value(prop, RDFS.comment) or ""),
                "domain": str(domain).rsplit("/", 1)[-1] if domain else None,
                "range": str(range_).rsplit("/", 1)[-1] if range_ else None,
                "kind": "object" if prop_type == OWL.ObjectProperty else "data",
            })
    return sorted(concepts, key=lambda c: c["name"])


if __name__ == "__main__":
    g = load_graph()
    print(f"Loaded {len(g)} triples\n")

    print(f"=== {len(list_classes(g))} Classes ===")
    for c in list_classes(g):
        print(f"  {c['name']:20s} → {c['label']}")

    print(f"\n=== {len(list_individuals(g))} Individuals ===")
    for ind in list_individuals(g):
        print(f"  {ind['name']:25s} ({', '.join(ind['types'])})")

    print(f"\n=== {len(get_concepts_for_mapping(g))} Concepts ===")
    for c in get_concepts_for_mapping(g):
        print(f"  {c['name']:15s} [{c['kind']:6s}] {c['domain']} → {c['range']}")