import os
import unittest

from linkml_runtime.dumpers import json_dumper, rdf_dumper
from linkml_runtime.loaders import yaml_loader
from linkml.generators.yamlgen import YAMLGenerator
from tests.test_models.kitchen_sink import Dataset, EmploymentEvent, Person

from tests import INPUT_DIR, MODEL_DIR

from linkml_sparql import QueryEngine, SparqlEndpoint
from SPARQLWrapper import SPARQLWrapper, N3
from rdflib import Graph

DATA = os.path.join(INPUT_DIR, 'kitchen_sink_inst_01.yaml')
CONTEXT = os.path.join(MODEL_DIR, 'kitchen_sink.context.jsonld')
SCHEMA = os.path.join(MODEL_DIR, 'kitchen_sink.yaml')

class QueryTestCase(unittest.TestCase):

    def test_query(self):
        """ sparql """
        schema = YAMLGenerator(SCHEMA).schema
        #print(schema)
        inst = yaml_loader.load(DATA, target_class=Dataset)
        for p in inst.persons:
            for a in p.addresses:
                print(f'{p.id} address = {a.street}')
        #print(json_dumper.dumps(element=inst, contexts=CONTEXT))
        g = rdf_dumper.as_rdf_graph(element=inst, contexts=CONTEXT)
        print(g)
        #for row in g.query("DESCRIBE ?x WHERE {?x ?r ?y}"):
        for row in g.query("SELECT * WHERE {?x ?r ?y}"):
            #print(f'ROW: {row["x"]} {row["r"]} {row["y"]}')
            print(f'ROW: {row}')
        qe = QueryEngine(schema=schema,
                         endpoint=SparqlEndpoint(graph=g),
                         lang='en')
        sq = qe.generate_query(name='fred bloggs')
        print(sq)
        print(sq.as_sparql())
        found = False
        for row in qe.execute(sq):
            obj = qe.fetch_object(row['subject'], original_query=sq, target_class=Person)
            print(f'New Obj={obj}')
            if obj.name == 'fred bloggs':
                found = True
        assert found

        objs = qe.query(has_employment_history=EmploymentEvent(employed_at='ROR:1'), target_class=Person)
        found = False
        for obj in objs:
            print(f'xxObjs = {obj}')
            if obj.name == 'joe schmoe':
                found = True

        assert found




if __name__ == '__main__':
    unittest.main()
