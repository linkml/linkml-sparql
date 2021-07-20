
from dataclasses import dataclass
from typing import Dict, Union, List, Any, Optional, Type
from rdflib import URIRef, Graph, Literal, BNode

PREFIXMAP = Dict[str, str]
IRI = Union[URIRef, str]

@dataclass
class SparqlEndpoint(object):
    url: Optional[str] = None
    graph: Optional[Graph] = None
    named_graph_iri: Optional[IRI] = None
    type_property: IRI = 'rdf:type'

@dataclass
class Term:
    val: Any
    def __str__(self):
        return str(self.val)

@dataclass
class Expression(Term):
    # TODO
    def __str__(self):
        return str(self.val)

@dataclass
class Atom(Term):
    None

@dataclass
class Variable(Atom):
    def __str__(self):
        return f'?{self.val}'
    def name(self) -> str:
        return str(self.val)

@dataclass
class Ground(Atom):
    def __str__(self):
        return self.val.n3()

@dataclass
class SparqlSelect:
    vars: List[Term]

    def as_sparql(self) -> str:
        return ' '.join([str(v) for v in self.vars])

@dataclass
class SparqlWhereClause:
    subject: Atom
    predicate: Atom
    object: Atom

    def as_sparql(self) -> str:
        return f"{self.subject} {self.predicate} {self.object}"


@dataclass
class SparqlQuery:
    prefixmap: PREFIXMAP = None
    select: SparqlSelect = None
    wheres: List[SparqlWhereClause] = None
    graphs: List[IRI] = None
    last_id: int = 0
    lang: str = 'en'

    def add_triple(self, s: Atom, p: Atom, v: Atom):
        wc = SparqlWhereClause(s, p, v)
        if self.wheres is None:
            self.wheres = []
        self.wheres.append(wc)

    def as_sparql(self) -> str:
        wheres = [w.as_sparql() for w in self.wheres]
        filters = []
        whereclause = ' .\n  '.join(wheres + filters)
        return f"SELECT {self.select.as_sparql()} WHERE {{\n  {whereclause}\n }}"

    def add_select_var(self, subj_var):
        if self.select is None:
            self.select = SparqlSelect([])
        self.select.vars.append(subj_var)

    def get_fresh_var(self) -> str:
        self.last_id += 1
        return Variable(f'v{self.last_id}')
