import logging
from typing import Union, Dict, Tuple

from rdflib.query import ResultRow
from rdflib.term import Node
from SPARQLWrapper import SPARQLWrapper, N3, SPARQLWrapper2
import SPARQLWrapper.SmartWrapper as sw

from linkml_runtime.utils.formatutils import underscore
from linkml_model.meta import SchemaDefinition, ClassDefinition, YAMLRoot, ElementName, SlotDefinition

from linkml_sparql.sparqlmodel import *

from linkml_sparql.mapper import LinkMLMapper

IRI = Union[URIRef, str]
LANGSTR = str

subj_var = Variable('subject')
pred_var = Variable('predicate')
obj_var = Variable('object')

# https://stackoverflow.com/questions/1176136/convert-string-to-python-class-object
def class_for_name(module_name, class_name):
    # load the module, will raise ImportError if module cannot be loaded
    m = __import__(module_name, globals(), locals(), class_name)
    # get the class, will raise AttributeError if class cannot be found
    c = getattr(m, class_name)
    return c

@dataclass
class QueryEngine(object):
    """
    ORM wrapper for SPARQL endpoint
    """

    endpoint: SparqlEndpoint
    schema: SchemaDefinition
    mapper: LinkMLMapper = None
    lang: LANGSTR = None

    def __post_init__(self):
        if self.mapper is None:
            self.mapper = LinkMLMapper(schema=self.schema)
        if self.mapper.schema is None:
            self.mapper.schema = self.schema

    def query(self, target_class: Type[YAMLRoot] = None, **params) -> List[YAMLRoot]:
        """
        Query a SPARQL endpoint for a list of objects

        :param params: key-value parameters. Keys should be in the schema
        :return:
        """
        sq = self.generate_query(**params)
        for row in self.execute(sq):
            yield self.fetch_object(row[subj_var.name()], sq, target_class=target_class)

    def generate_query(self, **params) -> SparqlQuery:
        """
        Generate a sparql query given query parameters

        :param prefixmap:
        :param params:
        :return:
        """
        sq = SparqlQuery(prefixmap={})
        sq.add_select_var(subj_var)
        self._generate_query_for_params(sq, subj_var, params)
        return sq

    def _generate_query_for_params(self, sq: SparqlQuery, focus_var: Variable, params: Dict) -> None:
        schema = self.schema
        mapper = self.mapper
        for sn, v in params.items():
            slot = mapper._get_slot(sn)
            if slot is not None:
                slot_range = slot.range
            else:
                slot_range = None
                logging.error(f'Unknown slot name: {sn}')
            prop_iri = mapper._slot_to_uri_term(slot, sq.prefixmap)
            if self.mapper._instance_of_linkml_class(v):
                subq_focus_var = sq.get_fresh_var()
                subq_params = { k: v2 for k, v2 in v.__dict__.items() if v2 is not None and v2 != []}
                self._generate_query_for_params(sq, subq_focus_var, subq_params)
                rdf_v = subq_focus_var
            else:
                rdf_v = mapper.pyval_to_sparql_atom(v, range=slot_range, query=sq)
            sq.add_triple(focus_var, prop_iri, rdf_v)

    def fetch_object(self, id: str,
                     original_query: SparqlQuery = None,
                     target_class: Type[YAMLRoot] = None) -> YAMLRoot:
        """
        Given an ID, query out other fields and populate object
        :param row:
        :param original_query:
        :param target_class:
        :return:
        """
        mapper = self.mapper
        g = self.describe(id)
        uri = mapper._curie_to_uri_term(id).val
        return self._graph_to_pyobj(uri, g, target_class)

    def _graph_to_pyobj(self, node, g: Graph, target_class:  Type[YAMLRoot]):
        mapper = self.mapper
        new_obj = {}
        if not isinstance(node, BNode):
            new_obj['id'] = mapper.node_to_python_value(node)
        for _, p, o in g.triples((node, None, None)):
            if self.lang is not None and isinstance(o, Literal) and o.language is not None and o.language != self.lang:
                logging.debug(f'Ignoring: {p} {o} as lang != {self.lang}')
                continue
            slot = mapper._predicate_iri_to_slot(p)
            if slot is None:
                logging.warning(f'No slot name for {p}')
            else:
                slot_name = mapper._get_python_field_for_slot(slot)
                range = slot.range
                if isinstance(o, BNode):
                    range_class = class_for_name(target_class.__module__, range)
                    v = self._graph_to_pyobj(o, g, range_class)
                else:
                    v = mapper.node_to_python_value(o, range=range)
                if range in self.schema.enums or True:
                    # workaround until https://github.com/linkml/linkml-runtime/pull/17 is released
                    if str(v).endswith(': '):
                        logging.info(f' TEMP CODE:: REPLACING: {v} for range {range}')
                        v = v.replace(': ', '')
                new_obj[slot_name] = v # TODO multivalued
        cls = mapper._get_linkml_class(new_obj)
        if cls is None:
            cls = target_class
        logging.debug(f'Creating {cls} for {new_obj} seeded from {node}')
        return cls(**new_obj)

    def describe(self, id: str) -> Graph:
        uri = self.mapper._curie_to_uri_term(id)
        endpoint = self.endpoint
        if endpoint.graph:
            g = self._walk_graph(uri.val, endpoint.graph)
        else:
            uriref = uri.val.n3()
            sparql = f"DESCRIBE {uriref}"
            logging.info(f'Q: {sparql} on {endpoint.url}')
            sw = SPARQLWrapper(endpoint.url)
            sw.setQuery(sparql)
            sw.setReturnFormat(N3)
            results = sw.query().convert()
            g = Graph()
            g.parse(data=results, format="n3")
        return g



    def _walk_graph(self, uri, g: Graph) -> Graph:
        """
        Walk graph expanding on blank nodes
        :param uri:
        :param g:
        :return:
        """
        nodes = [uri]
        edges = []
        visited = []
        subgraph = Graph()
        while len(nodes) > 0:
            node = nodes.pop()
            print(f'NNN={node} {type(node)}')
            if node in visited:
                continue
            visited.append(node)
            for _, p, o in g.triples((node, None, None)):
                logging.debug(f' E={p} {o}')
                edges.append((node, p, o))
                subgraph.add((node,p,o))
                if isinstance(o, BNode) and o not in nodes:
                    nodes.append(o)
        return subgraph

    def execute(self, query: SparqlQuery) -> List[ResultRow]:
        """
        Execute a sparql query on endpoint

        Endpoint can be an in-memory graph or remote endpoint

        :param query:
        :return:
        """
        sparql = query.as_sparql()
        g = self.endpoint.graph
        logging.info(f'SPARQL = {sparql}')
        if g is not None:
            for row in g.query(sparql):
                yield row
        else:
            url = self.endpoint.url
            logging.info(f'ENDPOINT = {url}')
            sw = SPARQLWrapper2(url)
            sw.setQuery(sparql)
            for result in sw.query().bindings:
                row = {k: _unwrap(v) for k, v in result.items()}
                yield row

def _unwrap(v: sw.Value) -> Node:
    if v.type == sw.Value.URI:
        return URIRef(v.value)
    elif v.type == sw.Value.Literal:
        if v.lang is not None:
            return Literal(v.value, lang=v.lang)
        else:
            return Literal(v.value)
    elif v.type == sw.Value.TypedLiteral:
        return Literal(v.value, datatype=v.datatype)
    elif v.type == sw.Value.BNODE:
        return BNode(v.value)
    else:
        raise Exception(f'Unknown type {v.type} for {v}')
