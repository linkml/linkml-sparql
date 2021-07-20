import logging

from linkml_runtime.utils.formatutils import underscore
from linkml_model.meta import SchemaDefinition, ClassDefinition, YAMLRoot, ElementName, SlotDefinition
from rdflib import BNode, URIRef, Literal
from rdflib.term import Node

from linkml_sparql.sparqlmodel import *

ASSERTED_TYPE_FIELD = '_type'


@dataclass
class Mapper(object):
    """
    Maps between URIs and RDF/SPARQL entities and Python datamodel entities
    """
    None

@dataclass
class LinkMLMapper(Mapper):
    """
    LinkML Mapper
    """

    schema: SchemaDefinition

    def _get_slot(self, sn: str) -> Optional[SlotDefinition]:
        for slot in self.schema.slots.values():
            if underscore(slot.name) == sn:
                return slot

    def _slot_to_uri_term(self, slot: SlotDefinition, prefixmap: PREFIXMAP = {}) -> Optional[IRI]:
        if slot is not None:
            return self._curie_to_uri_term(slot.slot_uri)
        else:
            return None

    def _predicate_iri_to_slot(self, iri: IRI, prefixmap: PREFIXMAP = {}) -> SlotDefinition:
        for slot in self.schema.slots.values():
            ut = self._curie_to_uri_term(slot.slot_uri)
            if str(ut.val) == str(iri):
                return slot
        return None

    def _get_python_field_for_slot(self, slot: SlotDefinition) -> str:
        return underscore(slot.name) # TODO: map to pythongen

    def pyval_to_sparql_atom(self, v: Any, range: ElementName = None, query: SparqlQuery = None) -> Atom:
        if range in self.schema.classes:
            return self._curie_to_uri_term(v)
        else:
            logging.error(f'Using literal for v={v} range={range}')
            # TODO: may be CURIE
            return Ground(Literal(v))

    def node_to_python_value(self, v: Node, range: ElementName=None):
        if isinstance(v, Literal):
            return str(v)
        if isinstance(v, URIRef):
            return str(v)  # TODO - curieify
        return v

    # DONE
    def _to_object(self, in_obj: Any, target_class: Type[YAMLRoot]=None) -> YAMLRoot:
        """
        Converts a nested python/json object to a LinkML instance

        :param in_obj:
        :return:
        """
        if isinstance(in_obj, dict):
            cls = self._get_linkml_class(in_obj)
            if cls is None:
                cls = target_class
            if cls is None:
                raise Exception(f'Cannot create class for {in_obj} // {type(in_obj)}, no type info')
            obj2 = {k: self._to_object(v) for k, v in in_obj.items()}
            obj2 = {k: v for k, v in obj2.items() if not isinstance(v, BNode)} ## TODO
            logging.debug(f'Instantiating: {cls} for {obj2}')
            return cls(**obj2)
        elif isinstance(in_obj, list):
            return [self._to_object(x, target_class=target_class) for x in in_obj]
        elif isinstance(in_obj, URIRef):
            return str(in_obj) ## TODO: curieify
        elif isinstance(in_obj, Literal):
            return str(in_obj) ## TODO: pythonify
        else:
            logging.warning(f'Pass thru: {in_obj} {type(in_obj)}')
            return in_obj

    # DONE
    def _get_linkml_class(self, in_obj: Dict) -> str:
        if ASSERTED_TYPE_FIELD in in_obj:
            cn = in_obj[ASSERTED_TYPE_FIELD]
            return self.schema.classes[cn]
        else:
            return None

    def _curie_to_uri_term(self, id: str) -> str:
        if id.startswith('http'):
            return Ground(URIRef(id))
        parts = id.split(':')
        if len(parts) == 2:
            [pfx, local] = parts
            if pfx in self.schema.prefixes:
                return Ground(URIRef(f'{self.schema.prefixes[pfx].prefix_reference}{local}'))
            else:
                logging.debug(f'Undeclared: {pfx} -- just using {id}')
        return Ground(URIRef(id))

    def _instance_of_linkml_class(self, v) -> bool:
        try:
            type(v).class_name
            return True
        except:
            return False

    def _lookup_slot(self, cls: ClassDefinition, field: str):
        for sn in cls.slots:
            s: SlotDefinition
            s = self.schema.slots[sn]
            if underscore(s.name) == field:
                return s
            if s.alias and underscore(s.alias) == field:
                return s
        logging.error(f'Did not find {field} in {cls.name} slots =  {cls.slots}')